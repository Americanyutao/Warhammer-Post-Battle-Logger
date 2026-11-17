"""Bounded, read-only Windows process access. No injection, hooks, or game writes."""
from __future__ import annotations
import ctypes
import hashlib
import json
import os
import struct
import time
from pathlib import Path
from relocate import RelocationError, adapt_profile


class ReadError(RuntimeError):
    pass


class UnsupportedBuild(ReadError):
    pass


def valid_pointer(value):
    return isinstance(value, int) and 0x10000 <= value < 0x800000000000 and value % 8 == 0


def pe_identity(read, base):
    if read(base, 2) != b'MZ':
        raise UnsupportedBuild('The game module has no MZ header.')
    offset = struct.unpack('<I', read(base + 0x3c, 4))[0]
    if not 0x40 <= offset <= 0x100000:
        raise UnsupportedBuild('The game module has an invalid PE header.')
    header = read(base + offset, 88)
    if header[:4] != b'PE\0\0' or struct.unpack_from('<H', header, 4)[0] != 0x8664 or struct.unpack_from('<H', header, 24)[0] != 0x20b:
        raise UnsupportedBuild('64-bit Windows and 64-bit WARHAMMER III are required.')
    return struct.unpack_from('<I', header, 8)[0], struct.unpack_from('<I', header, 80)[0]


def relocated(module, profile, address):
    rva = int(address, 0) - int(profile['image_base'], 0)
    if not 0 <= rva < module['size']:
        raise UnsupportedBuild('A profile address is outside the game module.')
    return module['base'] + rva


def verify_build(memory, module, profile):
    stamp, size = pe_identity(memory.read, module['base'])
    if stamp != profile['pe_timestamp'] or size != profile['image_size'] or size != module['size']:
        raise UnsupportedBuild('Unsupported game build. This prototype needs the executable used for the saved exports.')
    for anchor in profile['anchors']:
        expected = bytes.fromhex(anchor['hex'])
        address = relocated(module, profile, anchor['address'])
        if memory.read(address, len(expected)) != expected:
            raise UnsupportedBuild('Game code differs at ' + anchor['address'] + '. No battle offsets were used.')
    digest = hashlib.sha256()
    with Path(module['path']).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    if digest.hexdigest() != profile['source_sha256']:
        raise UnsupportedBuild('Unsupported executable fingerprint. No battle offsets were used.')


def load_profiles(directory):
    profiles = []
    for file in sorted(Path(directory).glob('*.json')):
        profile = json.loads(file.read_text(encoding='utf-8'))
        if profile.get('schema') != 1 or not all(key in profile for key in ('pe_timestamp', 'image_size', 'source_sha256', 'anchors', 'globals', 'offsets')):
            raise UnsupportedBuild('Invalid game build profile: ' + file.name)
        profiles.append(profile)
    if not profiles:
        raise UnsupportedBuild('No game build profiles were found.')
    return profiles


_adapt_failures = {}


def _cached_profiles(cache_dir):
    if not cache_dir or not Path(cache_dir).is_dir():
        return []
    try:
        return load_profiles(cache_dir)
    except (UnsupportedBuild, OSError, ValueError):
        return []


def adapt_to_build(module, profiles, stamp, size, cache_dir=None):
    """Relocate the newest compatible verified profile into a patched executable.

    Returns the adapted profile or raises UnsupportedBuild when the battle code really changed.
    The result is cached by executable fingerprint so later launches skip the search."""
    if not module.get('path'):
        raise UnsupportedBuild('Unsupported game build ' + str(stamp) + ': the game executable path is unknown.')
    path = Path(module['path'])
    try:
        key = (str(path), stamp, size, path.stat().st_mtime_ns)
    except OSError as error:
        raise UnsupportedBuild('Unsupported game build: the game executable could not be read (' + str(error) + ').')
    if key in _adapt_failures:
        raise UnsupportedBuild(_adapt_failures[key])
    image = path.read_bytes()
    failures = []
    for profile in sorted(profiles, key=lambda p: p['pe_timestamp'], reverse=True):
        try:
            adapted = adapt_profile(profile, image)
        except RelocationError as error:
            failures.append(str(error))
            continue
        if (adapted['pe_timestamp'], adapted['image_size']) != (stamp, size):
            failures.append('The executable on disk differs from the running game.')
            continue
        if cache_dir:
            try:
                Path(cache_dir).mkdir(parents=True, exist_ok=True)
                target = Path(cache_dir) / ('adapted_' + str(stamp) + '_' + adapted['source_sha256'][:12] + '.json')
                temporary = target.with_suffix('.tmp')
                temporary.write_text(json.dumps(adapted, indent=1), encoding='utf-8')
                os.replace(temporary, target)
            except OSError:
                pass
        return adapted
    message = ('Unsupported game build ' + str(stamp) + ': this game update changed the battle data the logger reads ('
               + (failures[0] if failures else 'no profile') + '). Check for a Battle Logger update.')
    _adapt_failures[key] = message
    raise UnsupportedBuild(message)


def select_profile(memory, module, profiles, identity=None, cache_dir=None):
    stamp, size = identity if identity is not None else pe_identity(memory.read, module['base'])
    match = lambda items: [p for p in items if p['pe_timestamp'] == stamp and p['image_size'] == size]
    candidates = match(profiles) or match(_cached_profiles(cache_dir))
    if not candidates:
        candidates = [adapt_to_build(module, profiles, stamp, size, cache_dir)]
    failures = []
    for profile in candidates:
        try:
            verify_build(memory, module, profile)
            return profile
        except UnsupportedBuild as error:
            failures.append(str(error))
    raise UnsupportedBuild(failures[-1])


class WindowsAPI:
    def __init__(self):
        if os.name != 'nt' or struct.calcsize('P') != 8:
            raise ReadError('Run with 64-bit Python on Windows.')
        from ctypes import wintypes as w
        self.w = w
        class ProcessEntry(ctypes.Structure):
            _fields_ = [('dwSize', w.DWORD), ('cntUsage', w.DWORD), ('th32ProcessID', w.DWORD),
                        ('th32DefaultHeapID', ctypes.c_size_t), ('th32ModuleID', w.DWORD),
                        ('cntThreads', w.DWORD), ('th32ParentProcessID', w.DWORD),
                        ('pcPriClassBase', w.LONG), ('dwFlags', w.DWORD), ('szExeFile', w.WCHAR * 260)]
        class ModuleEntry(ctypes.Structure):
            _fields_ = [('dwSize', w.DWORD), ('th32ModuleID', w.DWORD), ('th32ProcessID', w.DWORD),
                        ('GlblcntUsage', w.DWORD), ('ProccntUsage', w.DWORD),
                        ('modBaseAddr', ctypes.c_void_p), ('modBaseSize', w.DWORD),
                        ('hModule', w.HMODULE), ('szModule', w.WCHAR * 256), ('szExePath', w.WCHAR * 260)]
        self.ProcessEntry, self.ModuleEntry = ProcessEntry, ModuleEntry
        self.k = ctypes.WinDLL('kernel32', use_last_error=True)
        signatures = {
            'CreateToolhelp32Snapshot': ([w.DWORD, w.DWORD], w.HANDLE),
            'Process32FirstW': ([w.HANDLE, ctypes.POINTER(ProcessEntry)], w.BOOL),
            'Process32NextW': ([w.HANDLE, ctypes.POINTER(ProcessEntry)], w.BOOL),
            'Module32FirstW': ([w.HANDLE, ctypes.POINTER(ModuleEntry)], w.BOOL),
            'Module32NextW': ([w.HANDLE, ctypes.POINTER(ModuleEntry)], w.BOOL),
            'OpenProcess': ([w.DWORD, w.BOOL, w.DWORD], w.HANDLE),
            'ReadProcessMemory': ([w.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)], w.BOOL),
            'GetExitCodeProcess': ([w.HANDLE, ctypes.POINTER(w.DWORD)], w.BOOL),
            'CloseHandle': ([w.HANDLE], w.BOOL),
        }
        for name, (args, result) in signatures.items():
            function = getattr(self.k, name)
            function.argtypes, function.restype = args, result

    def failure(self, label):
        code = ctypes.get_last_error()
        return ReadError(label + ': Windows error ' + str(code) + ' (' + ctypes.FormatError(code).strip() + ')')

    def snapshot(self, flags, pid=0):
        for _ in range(4):
            handle = self.k.CreateToolhelp32Snapshot(flags, pid)
            if handle not in (None, ctypes.c_void_p(-1).value):
                return handle
            if ctypes.get_last_error() != 24:
                break
            time.sleep(0.03)
        raise self.failure('Cannot inspect the game process')

    def game_pids(self):
        handle = self.snapshot(2)
        try:
            entry = self.ProcessEntry()
            entry.dwSize = ctypes.sizeof(entry)
            if not self.k.Process32FirstW(handle, ctypes.byref(entry)):
                raise self.failure('Cannot list processes')
            result = []
            while True:
                if entry.szExeFile.lower() == 'warhammer3.exe':
                    result.append(int(entry.th32ProcessID))
                if not self.k.Process32NextW(handle, ctypes.byref(entry)):
                    if ctypes.get_last_error() != 18:
                        raise self.failure('Process listing changed')
                    return result
        finally:
            self.k.CloseHandle(handle)

    def game_module(self, pid):
        handle = self.snapshot(0x18, pid)
        try:
            entry = self.ModuleEntry()
            entry.dwSize = ctypes.sizeof(entry)
            if not self.k.Module32FirstW(handle, ctypes.byref(entry)):
                raise self.failure('Cannot inspect game modules')
            while True:
                if entry.szModule.lower() == 'warhammer3.exe':
                    return dict(name=entry.szModule, path=entry.szExePath,
                                base=int(entry.modBaseAddr), size=int(entry.modBaseSize))
                if not self.k.Module32NextW(handle, ctypes.byref(entry)):
                    if ctypes.get_last_error() != 18:
                        raise self.failure('Module listing changed')
                    raise ReadError('WARHAMMER III module was not found.')
        finally:
            self.k.CloseHandle(handle)


class ProcessMemory:
    def __init__(self, api, pid):
        self.api, self.pid = api, pid
        self.handle = api.k.OpenProcess(0x1010, False, pid)  # VM_READ | QUERY_LIMITED_INFORMATION
        if not self.handle:
            raise api.failure('Cannot read WARHAMMER III; launch the game and meter at the same privilege level')
        self.calls = self.bytes_read = 0
        self.last_error = None

    def close(self):
        if self.handle:
            self.api.k.CloseHandle(self.handle)
            self.handle = None

    def read(self, address, size):
        if not self.handle:
            raise ReadError('The game handle is closed.')
        if not 0x10000 <= address < 0x800000000000 or not 0 < size <= 65536 or address + size > 0x800000000000:
            raise ReadError('Invalid or oversized memory read.')
        buffer = ctypes.create_string_buffer(size)
        received = ctypes.c_size_t()
        self.calls += 1
        if not self.api.k.ReadProcessMemory(self.handle, ctypes.c_void_p(address), buffer, size, ctypes.byref(received)):
            self.last_error = dict(address=hex(address), size=size, windows_error=ctypes.get_last_error())
            raise self.api.failure('A game memory read was unavailable')
        if received.value != size:
            raise ReadError('A game memory read was incomplete.')
        self.bytes_read += size
        return buffer.raw

    def alive(self):
        code = self.api.w.DWORD()
        return bool(self.handle and self.api.k.GetExitCodeProcess(self.handle, ctypes.byref(code)) and code.value == 259)
