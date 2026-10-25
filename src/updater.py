"""User-requested GitHub updates, staged outside the installation."""
import ctypes
from ctypes import wintypes as w
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.request
import uuid
import zipfile
from version import VERSION

REPOSITORY = 'Americanyutao/Warhammer-Post-Battle-Logger'
API = f'https://api.github.com/repos/{REPOSITORY}/releases/latest'
ASSET = 'WH3BattleLogger-Windows-x64.zip'
MAX_DOWNLOAD = 600 * 1024 * 1024
MAX_UNPACKED = 1500 * 1024 * 1024

def version_tuple(value):
    match = re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)', value)
    if not match:
        raise ValueError('Release version must use vMAJOR.MINOR.PATCH.')
    return tuple(map(int, match.groups()))

def latest_release():
    request = urllib.request.Request(API, headers={'Accept':'application/vnd.github+json', 'User-Agent':f'WH3BattleLogger/{VERSION}'})
    with urllib.request.urlopen(request, timeout=20) as response:
        release = json.loads(response.read(1024 * 1024))
    if release.get('draft') or release.get('prerelease'):
        raise ValueError('The latest release is not a stable public release.')
    if version_tuple(release['tag_name']) <= version_tuple(VERSION):
        return None
    assets = [a for a in release['assets'] if a['name'] == ASSET]
    if len(assets) != 1:
        raise ValueError('This release has no compatible Windows update package.')
    asset = assets[0]
    prefix = f'https://github.com/{REPOSITORY}/releases/download/'
    if not asset['browser_download_url'].startswith(prefix):
        raise ValueError('Unexpected update download address.')
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', asset.get('digest') or ''):
        raise ValueError('GitHub has not supplied a SHA-256 checksum for this package.')
    if not 0 < asset['size'] <= MAX_DOWNLOAD:
        raise ValueError('Unexpected update package size.')
    return release['tag_name'], asset

def unpack_package(archive, destination):
    destination = Path(destination)
    with zipfile.ZipFile(archive) as package:
        members = package.infolist()
        if sum(m.file_size for m in members) > MAX_UNPACKED:
            raise ValueError('Update package is too large.')
        for member in members:
            path = PurePosixPath(member.filename)
            if path.is_absolute() or '..' in path.parts or '\\' in member.filename or ':' in member.filename:
                raise ValueError('Unsafe update package path.')
            if (member.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError('Update package contains a symbolic link.')
        executables = [m for m in members if PurePosixPath(m.filename).name == 'WH3BattleLogger.exe']
        if len(executables) != 1:
            raise ValueError('Update package must contain exactly one application.')
        prefix = PurePosixPath(executables[0].filename).parent
        # Only application files are accepted; never install captures, keys or logs.
        for member in members:
            path = PurePosixPath(member.filename)
            if not path.is_relative_to(prefix):
                continue
            relative = path.relative_to(prefix)
            if not relative.parts or relative.parts[0] not in ('WH3BattleLogger.exe', '_internal', 'README.txt'):
                continue
            target = destination.joinpath(*relative.parts)
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with package.open(member) as source, target.open('wb') as output:
                    shutil.copyfileobj(source, output)
    if not (destination/'_internal/python313.dll').is_file():
        raise ValueError('Update package is missing the application runtime.')
    return destination

def download_update(asset):
    directory = Path(tempfile.mkdtemp(prefix='wh3-logger-update-'))
    try:
        archive = directory/'download.zip'
        digest = hashlib.sha256(); size = 0
        request = urllib.request.Request(asset['browser_download_url'], headers={'User-Agent':f'WH3BattleLogger/{VERSION}'})
        with urllib.request.urlopen(request, timeout=30) as response, archive.open('wb') as output:
            while chunk := response.read(1024 * 1024):
                size += len(chunk)
                if size > asset['size'] or size > MAX_DOWNLOAD:
                    raise ValueError('Update download exceeded its expected size.')
                digest.update(chunk); output.write(chunk)
        if size != asset['size'] or 'sha256:'+digest.hexdigest() != asset['digest']:
            raise ValueError('Update download failed its integrity check. Please try again.')
        return unpack_package(archive, directory/'app')
    except Exception:
        shutil.rmtree(directory, ignore_errors=True)
        raise

def message(text, question=False):
    user = ctypes.WinDLL('user32', use_last_error=True)
    user.MessageBoxW.argtypes = [w.HWND,w.LPCWSTR,w.LPCWSTR,w.UINT]
    return user.MessageBoxW(None, text, 'Battle Logger updates', 0x10000 | (0x24 if question else 0x40)) == 6

class UpdateChecker:
    def __init__(self, actions):
        self.actions = actions
        self.thread = None
        self.pending = None
    def start(self):
        if self.pending or (self.thread and self.thread.is_alive()):
            return
        self.thread = threading.Thread(target=self.run, name='battle-logger-update', daemon=True)
        self.thread.start()
    def run(self):
        stage = None
        try:
            release = latest_release()
            if release is None:
                message(f'You are up to date (version {VERSION}).'); return
            tag, asset = release
            if not getattr(sys, 'frozen', False):
                message(f'{tag} is available. In-app installation is available in the packaged application.'); return
            if not message(f'Version {tag} is available (installed: {VERSION}).\n\nDownload {asset["size"] / 1024 / 1024:.0f} MB now? The logger will keep recording during the download.', True):
                return
            stage = download_update(asset)
            check = stage.parent/'install-check.json'
            subprocess.run([str(stage/'WH3BattleLogger.exe'),'--check-install',str(check)],
                           cwd=stage,timeout=90,check=True)
            if version_tuple(json.loads(check.read_text(encoding='utf-8'))['version']) != version_tuple(tag):
                raise ValueError('The package version does not match its release tag.')
            if message(f'Version {tag} is ready. Save the current recording, close the logger, install and restart now?\n\nIf a battle is in progress, choose No and update after it ends. Your recordings and private key will be kept.', True):
                self.pending = stage
                self.actions.put('install_update')
                stage = None
        except Exception as error:
            message(f'Could not update the logger. Your installed app has not changed.\n\n{error}')
        finally:
            if stage: shutil.rmtree(stage.parent, ignore_errors=True)

def install_files(stage, destination):
    """Replace only app-owned files, rolling back if copying fails."""
    stage, destination = Path(stage), Path(destination)
    backup = destination/('.update-backup-'+uuid.uuid4().hex)
    backup.mkdir()
    moved = []; copied = []
    try:
        for name in ('WH3BattleLogger.exe', '_internal', 'README.txt'):
            if not (stage/name).exists(): continue
            if (destination/name).exists():
                (destination/name).rename(backup/name); moved.append(name)
            copied.append(name)
            if (stage/name).is_dir(): shutil.copytree(stage/name, destination/name)
            else: shutil.copy2(stage/name, destination/name)
    except Exception:
        for name in reversed(copied):
            path = destination/name
            if path.is_dir(): shutil.rmtree(path)
            elif path.exists(): path.unlink()
        for name in moved: (backup/name).rename(destination/name)
        raise
    # Retain the previous app for recovery; never touch user data.
    return backup

def apply_update(destination, pid):
    """Runs from the staged app after the original process has completely exited."""
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [w.DWORD,w.BOOL,w.DWORD]; kernel.OpenProcess.restype = w.HANDLE
    kernel.WaitForSingleObject.argtypes = [w.HANDLE,w.DWORD]; kernel.WaitForSingleObject.restype = w.DWORD
    kernel.CloseHandle.argtypes = [w.HANDLE]
    process = kernel.OpenProcess(0x100000,False,pid)
    if process:
        try:
            if kernel.WaitForSingleObject(process,120000) != 0:
                raise RuntimeError('The logger did not finish exiting. Update cancelled.')
        finally: kernel.CloseHandle(process)
    elif ctypes.get_last_error() != 87:
        raise ctypes.WinError(ctypes.get_last_error())
    stage = Path(sys.executable).resolve().parent
    destination = Path(destination).resolve()
    if stage == destination or not (destination/'WH3BattleLogger.exe').is_file():
        raise ValueError('Invalid update destination.')
    install_files(stage, destination)
    subprocess.Popen([str(destination/'WH3BattleLogger.exe')], cwd=destination)

def launch_installer(stage, destination):
    subprocess.Popen([str(Path(stage)/'WH3BattleLogger.exe'), '--apply-update',str(destination),'--wait-pid',str(os.getpid())], cwd=stage)
