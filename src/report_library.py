"""Report discovery and authenticated interrupted-capture recovery."""
from pathlib import Path
import threading
import json
import os
from explorer import open_folder
from battle_names import validate_name,unique_capture_path,LEGACY_NAME
from viewer_preferences import ViewerPreferences
from logfile import load_key
from report import convert
from settings import load_report_options


class ReportLibrary:
    def __init__(self, root):
        self.root=Path(root)
        self.lock=threading.Lock()
        self.status=''
        self.active_paths=set()

    def entries(self,include_exports=False):
        folder=self.root/'captures'
        paths={p.stem:dict(log=p,html=None) for p in folder.glob('*.wh3log')}
        for p in (*folder.glob('*.html'),*(self.root/'shareables').glob('*.html'),*(folder/'shareables').glob('*.html')):
            if include_exports or p.stem in paths:paths.setdefault(p.stem,dict(log=None,html=None))['html']=p
        return [dict(name=name,recording=bool(paths[name]['log'] and paths[name]['log'].resolve() in self.active_paths),**paths[name]) for name in sorted(paths,reverse=True)]

    def export_html(self,source):
        """Optional legacy export; never part of recording or opening a log."""
        if not self.lock.acquire(blocking=False):return
        try:
            source=Path(source)
            directory=self.root/'captures/shareables';directory.mkdir(parents=True,exist_ok=True)
            output=directory/(source.stem+'.html')
            self.status='Building HTML…'
            convert(source,load_key(self.root/'captures/logger.key'),output,recover_tail=True,report_options=load_report_options(self.root))
            self.status='Built HTML: '+output.name
        except Exception as error:self.status='Could not build HTML: '+(str(error) or type(error).__name__)
        finally:self.lock.release()

    def rename(self,source,name,busy=()):
        """Move a closed battle and its name-keyed companion data together."""
        if not self.lock.acquire(blocking=False):raise ValueError('Wait for the current export to finish.')
        moved=[];corrections=None;original=None
        try:
            source=Path(source).resolve();folder=(self.root/'captures').resolve()
            if source.parent!=folder or source.suffix.lower()!='.wh3log' or source.is_symlink() or not source.is_file():raise ValueError('This recording is unavailable.')
            if source in self.active_paths or source in busy:raise ValueError('Close this report or wait for recording/export to finish before renaming it.')
            validate_name(name)
            if source.stem==name:return source
            destination=unique_capture_path(self.root,name,exclude=source).resolve()
            pairs=[(source,destination)]
            for directory in (folder,self.root/'shareables',folder/'shareables'):
                old=directory/(source.stem+'.html')
                if old.is_file():pairs.append((old,directory/(destination.stem+'.html')))
            old_store=ViewerPreferences(self.root,source);new_store=ViewerPreferences(self.root,destination)
            old=old_store.root/old_store.files['unit_values'];new=new_store.root/new_store.files['unit_values']
            if old.is_file():pairs.append((old,new))
            corrections=self.root/'report-corrections.json'
            if corrections.is_file():
                original=corrections.read_bytes();data=json.loads(original)
                if source.name in data:
                    if destination.name in data:raise ValueError('That battle name already has saved corrections.')
                    data[destination.name]=data.pop(source.name)
                else:original=None
            for old,new in pairs:
                if new.exists() and old.resolve()!=new.resolve():raise ValueError('A file with this name already exists.')
                old.rename(new);moved.append((old,new))
            if original is not None:
                temporary=corrections.with_suffix('.rename.tmp')
                try:temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');temporary.replace(corrections)
                finally:temporary.unlink(missing_ok=True)
            self.status='Renamed battle: '+destination.stem
            return destination
        except Exception:
            for old,new in reversed(moved):new.rename(old)
            raise
        finally:self.lock.release()

    def clean_legacy_names(self,busy=()):
        changes=[]
        for path in sorted((self.root/'captures').glob('*.wh3log')):
            match=LEGACY_NAME.fullmatch(path.stem)
            if match and path.resolve() not in busy and path.resolve() not in self.active_paths:
                try:changes.append((path,self.rename(path,match[1],busy)))
                except (OSError,ValueError):continue
        return changes

    def move_shareables(self):
        old=self.root/'shareables';new=self.root/'captures/shareables';moved=[]
        if old.is_symlink() or old.is_junction():return moved
        for path in old.glob('*.html'):
            if path.is_symlink() or not path.is_file():continue
            new.mkdir(parents=True,exist_ok=True);target=new/path.name;number=1
            while target.exists():
                target=new/(path.stem+f' (export {number}).html');number+=1
            path.rename(target);moved.append((path,target))
        if old.is_dir() and not any(old.iterdir()):old.rmdir()
        return moved

    def build_missing(self, active=(), candidates=None):
        """Never read open captures, rewrite logs, or replace an existing HTML."""
        if not self.lock.acquire(blocking=False):return
        try:
            self.status='Checking for missing reports…'
            excluded={Path(p).resolve() for p in active}
            selected=None if candidates is None else {Path(p).resolve() for p in candidates}
            entries=[entry for entry in self.entries() if entry['log'] and not entry['html']
                and entry['log'].resolve() not in excluded
                and (selected is None or entry['log'].resolve() in selected)]
            if not entries:
                self.status='No missing reports.'
                return
            key=load_key(self.root/'captures/logger.key')
            built=0;errors=[]
            for entry in entries:
                try:
                    directory=self.root/'captures/shareables';directory.mkdir(parents=True,exist_ok=True)
                    convert(entry['log'],key,directory/(entry['name']+'.html'),recover_tail=True,report_options=load_report_options(self.root))
                    built+=1
                except Exception as error:
                    errors.append(entry['name']+': '+(str(error) or type(error).__name__))
            self.status=f'Built {built} missing report'+('s.' if built!=1 else '.')
            if errors:
                self.status+=f' {len(errors)} could not be recovered. '+errors[0]
        except Exception as error:
            self.status='Could not build reports: '+str(error)
        finally:self.lock.release()
