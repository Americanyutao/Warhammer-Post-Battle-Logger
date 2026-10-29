"""Bounded disk queue with latest-state coalescing for paused battle timestamps."""
import math
import queue
import threading
import time
from logfile import LogWriter
from capture_precision import release_record


class Recorder(threading.Thread):
    def __init__(self, path, key, metadata, max_bytes=512*1024*1024,*,diagnostics=False):
        super().__init__(name='logger-disk', daemon=False)
        self.path, self.key, self.metadata, self.max_bytes = path, key, metadata, max_bytes
        self.diagnostics=diagnostics
        self.queue = queue.Queue(maxsize=32)
        self.done = threading.Event()
        self.finish_requested = threading.Event()
        self.footer = None
        self.dropped = self.written = 0
        self.pending_drops = 0
        self.paused_samples_coalesced = 0
        self.error = None
        self.report_path = None
        self.limit_reached = False
        self.io_seconds = 0.
        self.start()

    def submit(self, record):
        if self.error or self.finish_requested.is_set(): return False
        try:
            item = dict(record, gap_before=dict(dropped_records=self.pending_drops)) if self.pending_drops else record
            self.queue.put_nowait(item)
            self.pending_drops = 0
            return True
        except queue.Full:
            self.dropped += 1
            self.pending_drops += 1
            return False

    def finish(self, footer):
        self.footer = footer
        self.finish_requested.set()

    def run(self):
        writer = None
        try:
            metadata=dict(self.metadata,diagnostics=True) if self.diagnostics else release_record(dict(kind='header',metadata=self.metadata))['metadata']
            writer = LogWriter(self.path, self.key, metadata)
            writer.flush(durable=True)
            flushed = time.monotonic()
            pending = None
            def write(record):
                nonlocal flushed
                started=time.perf_counter() if self.diagnostics else None
                if not self.limit_reached:
                    writer.write(record if self.diagnostics else release_record(record))
                    self.written+=1
                    self.limit_reached=writer.stream.tell()>=self.max_bytes
                else:self.dropped+=1
                if time.monotonic()-flushed>=2:
                    writer.flush(durable=True);flushed=time.monotonic()
                if self.diagnostics:self.io_seconds+=time.perf_counter()-started
            def sample(record):
                t=record.get('sim_s')
                return record.get('kind')=='sample' and isinstance(t,(int,float)) and not isinstance(t,bool) and math.isfinite(t)
            while not self.finish_requested.is_set() or not self.queue.empty():
                # Checkpoint even a long paused first sample for crash recovery.
                if time.monotonic()-flushed>=2:
                    if pending is not None:write(pending);pending=None
                    writer.flush(durable=True);flushed=time.monotonic()
                try:record=self.queue.get(timeout=.1)
                except queue.Empty:continue
                if pending is not None:
                    if sample(record) and sample(pending) and record['sim_s']==pending['sim_s'] and not record.get('gap_before'):
                        # Keep the latest paused state, retaining the one-time deployment baseline.
                        previous=pending;pending=dict(record)
                        for field in ('deployment_baseline','gap_before'):
                            if field in previous and field not in pending:pending[field]=previous[field]
                        result=previous.get('battle_result') or {};latest=pending.get('battle_result') or {}
                        if result.get('result_type_confirmed') and not latest.get('result_type_confirmed') and latest.get('outcome')==result.get('outcome'):pending['battle_result']=result
                        self.paused_samples_coalesced+=1
                        continue
                    write(pending);pending=None
                if sample(record):pending=record
                else:write(record)
            if pending is not None:write(pending)
            writer.flush()
            footer=dict(self.footer or {}, dropped_records=self.dropped, written_records=self.written,
                bytes_before_footer=self.path.stat().st_size,
                size_limit_reached=self.limit_reached,paused_samples_coalesced=self.paused_samples_coalesced)
            if self.diagnostics:footer['io_seconds']=self.io_seconds
            else:footer=release_record(dict(kind='footer',summary=footer))['summary']
            writer.close(footer)
            # Reports are decoded on demand by the app viewer. HTML export is separate.
        except Exception as error:
            self.error = str(error)
        finally:
            if writer and not writer.closed:
                writer.stream.close()
            self.done.set()
