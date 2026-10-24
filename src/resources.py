"""Process resource sampling and bounded JSON helpers."""
from __future__ import annotations
from collections import deque
import ctypes
import datetime as dt
import json
import math
import os
from pathlib import Path
import time

_MEMORY_API = None


def process_resources():
    global _MEMORY_API
    if os.name != 'nt':
        return dict(working_set_mib=None, private_mib=None)
    if _MEMORY_API is None:
        from ctypes import wintypes as w
        class Counters(ctypes.Structure):
            _fields_ = [('cb', w.DWORD), ('PageFaultCount', w.DWORD)] + [(name, ctypes.c_size_t) for name in
                ('PeakWorkingSetSize', 'WorkingSetSize', 'QuotaPeakPagedPoolUsage', 'QuotaPagedPoolUsage',
                 'QuotaPeakNonPagedPoolUsage', 'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage', 'PrivateUsage')]
        api = ctypes.WinDLL('psapi', use_last_error=True)
        api.GetProcessMemoryInfo.argtypes = [w.HANDLE, ctypes.POINTER(Counters), w.DWORD]
        api.GetProcessMemoryInfo.restype = w.BOOL
        _MEMORY_API = api, Counters, w.HANDLE
    api, Counters, Handle = _MEMORY_API
    data = Counters()
    data.cb = ctypes.sizeof(data)
    if not api.GetProcessMemoryInfo(Handle(-1), ctypes.byref(data), data.cb):
        return dict(working_set_mib=None, private_mib=None)
    return dict(working_set_mib=data.WorkingSetSize / 1048576,
                private_mib=data.PrivateUsage / 1048576)


def finite(value):
    return isinstance(value, (int, float)) and math.isfinite(value)


class ResourceMonitor:
    def __init__(self):
        self.recent = deque(maxlen=32)
        self.previous = None

    def sample(self, memory=None, wall=None, cpu=None):
        wall = time.monotonic() if wall is None else wall
        cpu = time.process_time() if cpu is None else cpu
        if self.previous is not None and (wall < self.previous[0] or cpu < self.previous[1]):
            self.recent.clear()
            self.previous = None
        instant = None
        if self.previous is not None and wall > self.previous[0]:
            instant = 100 * (cpu - self.previous[1]) / (wall - self.previous[0])
        self.previous = wall, cpu
        self.recent.append((wall, cpu))
        while len(self.recent) > 2 and self.recent[1][0] <= wall - 5:
            self.recent.popleft()
        oldest = self.recent[0]
        span = wall - oldest[0]
        window = 100 * (cpu - oldest[1]) / span if span > 0 else None
        return dict(monotonic_s=wall, process_cpu_s=cpu, cpu_one_core_percent=instant,
                    cpu_window_percent=window, cpu_window_s=span,
                    **(process_resources() if memory is None else memory))


def pacific(utc):
    march = dt.datetime(utc.year, 3, 8, 10, tzinfo=dt.timezone.utc)
    november = dt.datetime(utc.year, 11, 1, 9, tzinfo=dt.timezone.utc)
    start = march + dt.timedelta(days=(6 - march.weekday()) % 7)
    end = november + dt.timedelta(days=(6 - november.weekday()) % 7)
    summer = start <= utc < end
    return utc.astimezone(dt.timezone(dt.timedelta(hours=-7 if summer else -8), 'PDT' if summer else 'PST'))


def atomic_json(file, payload):
    file = Path(file)
    file.parent.mkdir(parents=True, exist_ok=True)
    temp = file.with_suffix(file.suffix + '.tmp')
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    temp.write_text(text, encoding='utf-8')
    temp.replace(file)


def prune_managed(directory, pattern, keep=12, max_bytes=8 * 1048576):
    directory = Path(directory).resolve()
    files = sorted((file for file in directory.glob(pattern)
                    if file.is_file() and file.name != 'battle-performance-latest.json'),
                   key=lambda file: (file.stat().st_mtime_ns, file.name), reverse=True)
    total = 0
    for index, file in enumerate(files):
        size = file.stat().st_size
        if index < keep and total + size <= max_bytes:
            total += size
        elif file.resolve().parent == directory:
            file.unlink()


