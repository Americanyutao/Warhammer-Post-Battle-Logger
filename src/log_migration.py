"""Verified atomic legacy-log migration and explicitly requested HTML cleanup."""
import ctypes
from ctypes import wintypes as w
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import threading
import time
import uuid
from logfile import LogWriter,read_log,load_key,log_version
from viewer_cache import process_stamp
from capture_precision import release_record,POLICY


class MigrationCancelled(Exception):pass


def record_hash(hasher,record):
    raw=json.dumps(record,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode('utf-8')
    hasher.update(struct.pack('<I',len(raw)));hasher.update(raw)


def fingerprint(path):
    stat=path.stat()
    return stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns


def migrate_log(path,key,*,stop=None,busy=lambda:set(),precision=False):
    path=Path(path)
    if path.is_symlink() or path.is_junction():raise ValueError('Linked recordings are not migrated.')
    if log_version(path)!=2 and not precision:return None
    if precision:
        iterator=read_log(path,key)
        try:header=next(iterator)
        finally:iterator.close()
        if header.get('metadata',{}).get('storage_precision_policy')==POLICY:return None
        if header.get('metadata',{}).get('diagnostics') is True:return None
    before=fingerprint(path)
    temporary=path.with_name('.'+path.name+f'.{os.getpid()}.{process_stamp(os.getpid())}.{uuid.uuid4().hex}.migrating')
    writer=None;count=0;source_hash=hashlib.sha256()
    try:
        for record in read_log(path,key):
            if stop and stop.is_set():raise MigrationCancelled()
            if precision:record=release_record(record)
            record_hash(source_hash,record)
            if writer is None:writer=LogWriter(temporary,key,{},header_record=record)
            else:writer.write(record)
            count+=1
            if stop and count%8==0 and stop.wait(.001):raise MigrationCancelled()
        if writer is None:raise ValueError('Empty recording.')
        writer.close({})
        verified=hashlib.sha256();verified_count=0
        for record in read_log(temporary,key):
            if stop and stop.is_set():raise MigrationCancelled()
            record_hash(verified,record);verified_count+=1
        if count!=verified_count or source_hash.digest()!=verified.digest():raise ValueError('Migrated recording verification failed.')
        if stop and stop.is_set():raise MigrationCancelled()
        if fingerprint(path)!=before or path.resolve() in busy():raise ValueError('Recording changed or is in use; migration deferred.')
        shutil.copystat(path,temporary)
        result=dict(file=path.name,before_bytes=before[2],after_bytes=temporary.stat().st_size,records=count,verified=True)
        temporary.replace(path)
        return result
    finally:
        if writer and not writer.closed:writer.stream.close()
        temporary.unlink(missing_ok=True)


def capture_folder(root):
    root=Path(root).resolve();folder=root/'captures'
    if folder.is_symlink() or folder.is_junction() or folder.resolve().parent!=root:
        raise ValueError('Capture maintenance cannot follow linked directories.')
    return folder


def delete_capture_html(root):
    folder=capture_folder(root);deleted=[]
    for path in folder.glob('*.html'):
        if path.is_symlink() or path.is_junction() or path.resolve().parent!=folder.resolve():continue
        path.unlink();deleted.append(path.name)
    return deleted


def cleanup_migration_temps(folder):
    for path in folder.glob('.*.migrating'):
        try:
            parts=path.name.rsplit('.',4)
            if len(parts)!=5 or len(parts[3])!=32 or any(c not in '0123456789abcdef' for c in parts[3]):continue
            pid=int(parts[1]);stamp=int(parts[2])
            if not 0<pid<2**32 or path.is_symlink() or path.resolve().parent!=folder.resolve():continue
            current=process_stamp(pid)
            if current is False or (current is not None and current!=stamp):path.unlink()
        except (OSError,ValueError):continue


def optimize_captures(root,*,stop=None,busy=lambda:set(),progress=lambda text:None,delete_html=False,precision=False):
    folder=capture_folder(root)
    result=dict(migrated=[],skipped=[],deleted_html=[])
    if delete_html:result['deleted_html']=delete_capture_html(root)
    cleanup_migration_temps(folder)
    paths=[]
    for path in folder.glob('*.wh3log'):
        if path.resolve() in busy():continue
        try:
            if log_version(path)==2 or precision:paths.append(path)
        except OSError:continue
    if not paths:return result
    key=load_key(folder/'logger.key')
    for index,path in enumerate(paths):
        if stop and stop.is_set():break
        if path.resolve() in busy():continue
        progress(f'Compressing saved recordings · {index+1} of {len(paths)}')
        try:
            change=migrate_log(path,key,stop=stop,busy=busy,precision=precision)
            if change:result['migrated'].append(change)
        except MigrationCancelled:break
        except Exception as error:result['skipped'].append(dict(file=path.name,error=str(error) or type(error).__name__))
    return result


class CaptureMaintenance:
    def __init__(self,root,busy=lambda:set(),progress=lambda text:None):
        self.root=Path(root);self.busy=busy;self.progress=progress
        self.lock=threading.Lock();self.stop_event=threading.Event();self.thread=None;self.pending=0
        self.last_result=None

    def start(self,*,delete_html=False):
        with self.lock:
            self.pending|=3 if delete_html else 1
            if self.thread is not None:return
            self.stop_event.clear()
            self.thread=threading.Thread(target=self.run,name='battle-log-maintenance',daemon=False)
            self.thread.start()

    def run(self):
        try:
            kernel=ctypes.WinDLL('kernel32',use_last_error=True)
            kernel.GetCurrentThread.restype=w.HANDLE
            kernel.SetThreadPriority.argtypes=[w.HANDLE,ctypes.c_int]
            kernel.SetThreadPriority(kernel.GetCurrentThread(),-1)
            while not self.stop_event.is_set():
                with self.lock:
                    flags=self.pending;self.pending=0
                    if not flags:
                        self.thread=None
                        return
                self.last_result=optimize_captures(self.root,stop=self.stop_event,busy=self.busy,
                    progress=self.progress,delete_html=bool(flags&2),precision=True)
                count=len(self.last_result['migrated']);skipped=len(self.last_result['skipped'])
                if count or skipped or flags&2:
                    self.progress(f'Saved recordings compressed: {count}'+(f' · {skipped} left unchanged (incomplete, unreadable or in use)' if skipped else ''))
        except Exception as error:self.progress('Recording maintenance: '+str(error))
        finally:
            with self.lock:
                if self.thread is threading.current_thread():self.thread=None

    def stop(self):
        self.stop_event.set()
        with self.lock:thread=self.thread;pending=self.pending;self.pending=0
        if thread:thread.join()
        # A fast update/restart must still honor a queued cleanup request.
        if pending&2:
            try:delete_capture_html(self.root)
            except OSError as error:self.progress('Could not remove an old HTML export: '+str(error))
