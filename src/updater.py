"""Verified, per-file GitHub updates with native progress and transient staging."""
import base64
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
import time
import urllib.request
import zlib
from version import VERSION
from update_manifest import MANIFEST, ARCHIVE, app_path, app_files, file_hash, validate_manifest, MAX_TOTAL
from update_ui import ProgressWindow, Cancelled

REPOSITORY='Americanyutao/Warhammer-Post-Battle-Logger'
API=f'https://api.github.com/repos/{REPOSITORY}/releases/latest'
ASSET=ARCHIVE
MAX_DOWNLOAD=600*1024*1024
MAX_MANIFEST=8*1024*1024


def version_tuple(value):
    match=re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)',value)
    if not match:raise ValueError('Release version must use vMAJOR.MINOR.PATCH.')
    return tuple(map(int,match.groups()))


def request(url, **headers):
    return urllib.request.Request(url,headers={'User-Agent':f'WH3BattleLogger/{VERSION}',**headers})


def validate_asset(asset, maximum=MAX_DOWNLOAD):
    if not asset['browser_download_url'].startswith(f'https://github.com/{REPOSITORY}/releases/download/'):
        raise ValueError('Unexpected update download address.')
    if not re.fullmatch(r'sha256:[0-9a-f]{64}',asset.get('digest') or ''):
        raise ValueError('GitHub has not supplied a SHA-256 checksum for this package.')
    if type(asset.get('size')) is not int or not 0<asset['size']<=maximum:
        raise ValueError('Unexpected update package size.')
    return asset


def latest_release():
    with urllib.request.urlopen(request(API,Accept='application/vnd.github+json'),timeout=20) as response:
        release=json.loads(response.read(MAX_MANIFEST))
    if release.get('draft') or release.get('prerelease'):
        raise ValueError('The latest release is not a stable public release.')
    if version_tuple(release['tag_name'])<=version_tuple(VERSION):return None
    assets=[a for a in release['assets'] if a['name']==ASSET]
    if len(assets)!=1:raise ValueError(f'This release needs an asset named {ASSET}.')
    asset=dict(validate_asset(assets[0]))
    manifests=[a for a in release['assets'] if a['name']==MANIFEST]
    if len(manifests)!=1:
        raise ValueError(f'This release is missing {MANIFEST}. The publisher must attach the generated update manifest.')
    asset['manifest']=validate_asset(manifests[0],MAX_MANIFEST)
    return release['tag_name'],asset


def read_verified(asset, maximum=MAX_MANIFEST):
    validate_asset(asset,maximum)
    with urllib.request.urlopen(request(asset['browser_download_url']),timeout=30) as response:
        data=response.read(asset['size']+1)
    if len(data)!=asset['size'] or 'sha256:'+hashlib.sha256(data).hexdigest()!=asset['digest']:
        raise ValueError('The update metadata failed its integrity check.')
    return data



def read_manifest(asset):
    compressed=read_verified(asset)
    decoder=zlib.decompressobj(31)
    raw=decoder.decompress(compressed,MAX_MANIFEST+1)
    if len(raw)>MAX_MANIFEST or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
        raise ValueError('Invalid or oversized compressed update inventory.')
    return json.loads(raw)


def safe_target(root,name):
    parts=app_path(name).parts
    root=Path(root).resolve();target=root.joinpath(*parts)
    if not target.resolve().is_relative_to(root):raise ValueError('Update path leaves the application folder.')
    for path in (target,*target.parents):
        if path==root:break
        if path.is_symlink() or path.is_junction():raise ValueError('Update paths must not contain links.')
    return target


def plan_update(files, destination, progress=lambda *a:None):
    changed=[]
    for i,item in enumerate(files):
        progress('Checking installed files…',i,len(files))
        path=safe_target(destination,item['path'])
        if not path.is_file() or path.stat().st_size!=item['size'] or file_hash(path)!=item['sha256']:
            changed.append(item)
    expected={item['path'].casefold() for item in files}
    removed=[p.relative_to(destination).as_posix() for p in app_files(destination) if p.relative_to(destination).as_posix().casefold() not in expected]
    return changed,removed


def range_groups(files):
    groups=[]
    for item in sorted(files,key=lambda f:f['offset']):
        start=item['offset'];end=start+item['compressed']
        if groups and start-groups[-1][1]<=512 and end-groups[-1][0]<=16*1024*1024:
            groups[-1][1]=end;groups[-1][2].append(item)
        else:groups.append([start,end,[item]])
    return groups


def download_ranges(asset, changed, stage, progress=lambda *a:None):
    groups=range_groups(changed);total=sum(end-start for start,end,_ in groups);done=0
    for start,end,items in groups:
        if end==start:blob=b''
        else:
            with urllib.request.urlopen(request(asset['browser_download_url'],Range=f'bytes={start}-{end-1}',**{'Accept-Encoding':'identity'}),timeout=30) as response:
                if response.status!=206 or response.headers.get('Content-Range')!=f'bytes {start}-{end-1}/{asset["size"]}':
                    raise ValueError('The download server did not honor partial downloads. No full download was attempted.')
                chunks=[];received=0
                while chunk:=response.read(min(256*1024,end-start-received+1)):
                    received+=len(chunk)
                    if received>end-start:raise ValueError('Update range exceeded its expected size.')
                    chunks.append(chunk)
                    progress('Downloading changes',done+received,total,'bytes')
                if received!=end-start:raise ValueError('Incomplete update download. Please try again.')
                blob=b''.join(chunks)
        for item in items:
            compressed=blob[item['offset']-start:item['offset']-start+item['compressed']]
            if item['method']==8:
                decoder=zlib.decompressobj(-15)
                raw=decoder.decompress(compressed,item['size']+1)
                if not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
                    raise ValueError('Invalid compressed update file.')
            else:raw=compressed
            if len(raw)!=item['size'] or hashlib.sha256(raw).hexdigest()!=item['sha256']:
                raise ValueError('An update file failed its integrity check.')
            target=safe_target(stage,item['path']);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
        done+=end-start
    return total


def stage_update(asset, files, changed, removed, destination, progress=lambda *a:None):
    directory=Path(tempfile.mkdtemp(prefix='wh3-logger-update-',dir=destination))
    stage=directory/'app';stage.mkdir()
    try:
        download_ranges(asset,changed,stage,progress)
        changed_names={item['path'] for item in changed}
        for i,item in enumerate(files):
            progress('Preparing and verifying the new version…',i,len(files))
            if item['path'] in changed_names:continue
            source=safe_target(destination,item['path']);target=safe_target(stage,item['path'])
            target.parent.mkdir(parents=True,exist_ok=True)
            # Windows locks every hard link to a loaded image. Keep the helper's
            # runtime separate so the restarted app cannot lock staging cleanup.
            if source.suffix.lower() in ('.dll','.pyd','.exe','.zip'):
                shutil.copy2(source,target)
            else:
                try:os.link(source,target)
                except OSError:shutil.copy2(source,target)
            if file_hash(target)!=item['sha256']:raise ValueError('Installed files changed during preparation. Please retry.')
        (directory/'plan.json').write_text(json.dumps(dict(schema=1,files=files,changed=sorted(changed_names),removed=removed)),encoding='utf-8')
        return stage
    except Exception:
        shutil.rmtree(directory,ignore_errors=True);raise


def message(text,question=False):
    user=ctypes.WinDLL('user32',use_last_error=True)
    user.MessageBoxW.argtypes=[w.HWND,w.LPCWSTR,w.LPCWSTR,w.UINT]
    return user.MessageBoxW(None,text,'Battle Logger updates',0x10000|(0x24 if question else 0x40))==6


class UpdateChecker:
    def __init__(self,actions):
        self.actions=actions;self.thread=None;self.pending=None
    def start(self):
        if self.pending or (self.thread and self.thread.is_alive()):return
        self.thread=threading.Thread(target=self.run,name='battle-logger-update',daemon=True);self.thread.start()
    def run(self):
        stage=window=None
        try:
            window=ProgressWindow().start()
            release=latest_release()
            window.update('Checking release information…')
            if release is None:
                window.close();message(f'You are up to date (version {VERSION}).');return
            tag,asset=release
            if not getattr(sys,'frozen',False):
                window.close();message(f'{tag} is available. Run the packaged app to install updates.');return
            destination=Path(sys.executable).resolve().parent
            manifest=read_manifest(asset['manifest'])
            files=validate_manifest(manifest,tag,asset['size'])
            changed,removed=plan_update(files,destination,window.update)
            size=sum(end-start for start,end,_ in range_groups(changed))
            window.close();window=None
            if not message(f'Version {tag} is available (installed: {VERSION}).\n\nDownload {size/1048576:.1f} MB of changes ({len(changed)} files)? Unchanged files will be kept. The logger will keep recording.',True):return
            window=ProgressWindow().start()
            stage=stage_update(asset,files,changed,removed,destination,window.update)
            window.update('Testing the new application…',0,1)
            check=stage.parent/'install-check.json'
            subprocess.run([str(stage/'WH3BattleLogger.exe'),'--check-install',str(check)],cwd=stage,timeout=90,check=True)
            window.update('Application checks complete',1,1)
            if version_tuple(json.loads(check.read_text(encoding='utf-8'))['version'])!=version_tuple(tag):
                raise ValueError('The package version does not match its release tag.')
            window.close();window=None
            if message(f'{tag} is ready. Save, install and restart now?\n\nUpdate between battles. Recordings and your private key stay in place. No backup copy will be kept after a successful update.',True):
                self.pending=stage;self.actions.put('install_update');stage=None
        except Cancelled:pass
        except Exception as error:
            if window:window.close();window=None
            message(f'Could not update the logger. Your installed app has not changed.\n\n{error}')
        finally:
            if window:window.close()
            if stage:shutil.rmtree(stage.parent,ignore_errors=True)



def copy_install_file(source,target,progress,done,total,remaining):
    size=source.stat().st_size;written=0
    with source.open('rb') as reader,target.open('wb') as writer:
        while chunk:=reader.read(256*1024):
            writer.write(chunk);done+=len(chunk);written+=len(chunk)
            progress('Installing changes',done,total,'bytes',source.name,remaining+(written<size))
    shutil.copystat(source,target)
    return done


def install_files(stage,destination,progress=lambda *a:None):
    """Replace changed files only; transient rollback data is deleted on success."""
    stage,destination=Path(stage).resolve(),Path(destination).resolve()
    plan_path=stage.parent/'plan.json'
    if plan_path.exists():
        plan=json.loads(plan_path.read_text(encoding='utf-8'))
        expected={item['path']:item for item in plan['files']}
        changed=plan['changed'];removed=plan['removed']
        for name in changed:
            app_path(name)
            if name not in expected or file_hash(safe_target(stage,name))!=expected[name]['sha256']:
                raise ValueError('Staged files no longer match the verified update.')
        for name in removed:
            app_path(name)
            if name in expected:raise ValueError('Invalid obsolete file in update plan.')
    else:
        # Compatibility: v1.1.0/v1.1.1 launch this helper from a full ZIP.
        changed=[p.relative_to(stage).as_posix() for p in app_files(stage)]
        expected=set(changed)
        removed=[p.relative_to(destination).as_posix() for p in app_files(destination) if p.relative_to(destination).as_posix() not in expected]
    total=sum(safe_target(stage,name).stat().st_size for name in changed)
    done=0
    journal=stage.parent/'rollback';journal.mkdir(exist_ok=True)
    moved=[];written=[]
    try:
        for i,name in enumerate(changed+removed):
            progress('Installing changes',done,total,'bytes')
            target=safe_target(destination,name)
            if target.exists():
                saved=safe_target(journal,name);saved.parent.mkdir(parents=True,exist_ok=True)
                target.rename(saved);moved.append(name)
            if name in changed:
                target.parent.mkdir(parents=True,exist_ok=True);written.append(name)
                done=copy_install_file(safe_target(stage,name),target,progress,done,total,max(0,len(changed)-i-1))
        progress('Installation complete',done,total,'bytes')
    except Exception:
        for name in reversed(written):
            path=safe_target(destination,name)
            if path.exists():path.unlink()
        for name in reversed(moved):
            target=safe_target(destination,name);target.parent.mkdir(parents=True,exist_ok=True)
            safe_target(journal,name).rename(target)
        shutil.rmtree(journal)
        raise
    shutil.rmtree(journal)


def wait_for_exit(pid):
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD];kernel.OpenProcess.restype=w.HANDLE
    kernel.WaitForSingleObject.argtypes=[w.HANDLE,w.DWORD];kernel.WaitForSingleObject.restype=w.DWORD
    kernel.CloseHandle.argtypes=[w.HANDLE]
    process=kernel.OpenProcess(0x100000,False,pid)
    if process:
        try:
            if kernel.WaitForSingleObject(process,120000)!=0:raise RuntimeError('The logger did not finish exiting. Update cancelled.')
        finally:kernel.CloseHandle(process)
    elif ctypes.get_last_error()!=87:raise ctypes.WinError(ctypes.get_last_error())


def apply_update(destination,pid):
    stage=Path(sys.executable).resolve().parent;destination=Path(destination).resolve()
    if stage==destination or not (destination/'WH3BattleLogger.exe').is_file():raise ValueError('Invalid update destination.')
    window=ProgressWindow().start()
    try:
        window.update('Finishing saving and closing the logger…')
        wait_for_exit(pid)
        install_files(stage,destination,window.update)
        subprocess.Popen([str(destination/'WH3BattleLogger.exe'),'--cleanup-update',str(stage.parent),'--wait-pid',str(os.getpid())],cwd=destination)
    except Cancelled:
        # install_files has restored every original file before this branch.
        window.update('Update cancelled. Restarting the previous version…',check_cancel=False)
        subprocess.Popen([str(destination/'WH3BattleLogger.exe')],cwd=destination)
        cleanup_after_cancel(stage.parent,destination)
    finally:window.close()



def cleanup_after_cancel(directory,installation):
    # Older versions do not accept --cleanup-update. A hidden OS helper waits
    # for this staged executable to exit before deleting only its staging folder.
    directory=Path(directory).absolute();installation=Path(installation).resolve()
    if directory.is_symlink() or directory.is_junction():raise ValueError('Unsafe cleanup directory.')
    directory=directory.resolve()
    if directory.parent not in {installation,Path(tempfile.gettempdir()).resolve()} or not re.fullmatch(r'wh3-logger-update-[a-zA-Z0-9_-]+',directory.name):
        raise ValueError('Invalid cleanup directory.')
    encoded_path=base64.b64encode(str(directory).encode('utf-8')).decode('ascii')
    script=("$updateDirectory=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('"+encoded_path+"')); "
            +f"Wait-Process -Id {os.getpid()} -ErrorAction SilentlyContinue; "
            +"for($updateAttempt=0;$updateAttempt -lt 20;$updateAttempt++){try{Remove-Item -LiteralPath $updateDirectory -Recurse -Force -ErrorAction Stop;break}catch{Start-Sleep -Milliseconds 500}}")
    command=base64.b64encode(script.encode('utf-16-le')).decode('ascii')
    shell=Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
    subprocess.Popen([str(shell),'-NoProfile','-NonInteractive','-WindowStyle','Hidden','-EncodedCommand',command],creationflags=0x08000000,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)


def launch_installer(stage,destination):
    subprocess.Popen([str(Path(stage)/'WH3BattleLogger.exe'),'--apply-update',str(destination),'--wait-pid',str(os.getpid())],cwd=stage)


def cleanup_update(directory,pid):
    """New installed process removes its exited helper's own temporary directory."""
    directory=Path(directory).absolute()
    if directory.is_symlink() or directory.is_junction():raise ValueError('Unsafe update cleanup directory.')
    directory=directory.resolve()
    allowed_parents={Path(sys.executable).resolve().parent,Path(tempfile.gettempdir()).resolve()}
    if directory.parent not in allowed_parents or not re.fullmatch(r'wh3-logger-update-[a-zA-Z0-9_-]+',directory.name):
        raise ValueError('Invalid update cleanup directory.')
    if directory.is_symlink() or directory.is_junction():raise ValueError('Unsafe update cleanup directory.')
    wait_for_exit(pid)
    for attempt in range(5):
        try:shutil.rmtree(directory);return
        except FileNotFoundError:return
        except OSError:
            if attempt==4:raise
            time.sleep(.5)


def cleanup_legacy_backups(root):
    root=Path(root).resolve()
    for directory in root.glob('.update-backup-*'):
        if not re.fullmatch(r'\.update-backup-[0-9a-f]{32}',directory.name):continue
        if directory.is_symlink() or directory.is_junction() or not directory.is_dir():continue
        # Only folders created by our earlier updater, never arbitrary user files.
        if directory.resolve().parent!=root:continue
        if {p.name for p in directory.iterdir()}-{'WH3BattleLogger.exe','_internal','README.txt'}:continue
        if any(p.is_symlink() or p.is_junction() for p in directory.rglob('*')):continue
        shutil.rmtree(directory)
