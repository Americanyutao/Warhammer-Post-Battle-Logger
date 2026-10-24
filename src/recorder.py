"""Bounded disk queue: UI coalescing never drops collected log samples."""
import queue
import threading
import time
from logfile import LogWriter
from report import convert


class Recorder(threading.Thread):
    def __init__(self, path, key, metadata, max_bytes=512*1024*1024):
        super().__init__(name='logger-disk', daemon=False)
        self.path, self.key, self.metadata, self.max_bytes = path, key, metadata, max_bytes
        self.queue = queue.Queue(maxsize=32)
        self.done = threading.Event()
        self.finish_requested = threading.Event()
        self.footer = None
        self.dropped = self.written = 0
        self.pending_drops = 0
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
            writer = LogWriter(self.path, self.key, self.metadata)
            flushed = time.monotonic()
            while not self.finish_requested.is_set() or not self.queue.empty():
                try: record = self.queue.get(timeout=.1)
                except queue.Empty: continue
                started = time.perf_counter()
                if not self.limit_reached:
                    writer.write(record)
                    self.written += 1
                    self.limit_reached = writer.stream.tell() >= self.max_bytes
                else: self.dropped += 1
                if time.monotonic() - flushed >= 2:
                    writer.flush()
                    flushed = time.monotonic()
                self.io_seconds += time.perf_counter() - started
            writer.flush()
            writer.close(dict(self.footer or {}, dropped_records=self.dropped, written_records=self.written,
                bytes_before_footer=self.path.stat().st_size, io_seconds=self.io_seconds,
                size_limit_reached=self.limit_reached))
            self.report_path = convert(self.path, self.key)
        except Exception as error:
            self.error = str(error)
        finally:
            if writer and not writer.closed:
                writer.stream.close()
            self.done.set()
