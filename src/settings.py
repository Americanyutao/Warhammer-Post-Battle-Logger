"""Local report preferences, separate from replaceable application files."""
import json
from pathlib import Path
import os
import threading
from paths import DATA_ROOT

ICONS_TIP='Show bundled icons in the app viewer. Icons also increase HTML export sizes significantly. Turn off for easier sharing of HTML exports.'


def load_report_options(root=DATA_ROOT):
    try:
        path=Path(root)/'settings.json'
        if path.stat().st_size>65536:return dict(icons=True)
        data=json.loads(path.read_text(encoding='utf-8'))
        icons=data.get('report_options',{}).get('icons',True)
        return dict(icons=icons if isinstance(icons,bool) else True)
    except (OSError,ValueError,AttributeError):return dict(icons=True)


class Settings:
    def __init__(self,root=DATA_ROOT):
        self.root=Path(root)
        self.lock=threading.Lock()

    def report_options(self):
        with self.lock:return load_report_options(self.root)

    def save(self,*,icons):
        if not isinstance(icons,bool):raise ValueError('Icons must be checked or unchecked.')
        with self.lock:
            self.root.mkdir(parents=True,exist_ok=True)
            path=self.root/'settings.json'
            try:
                data=json.loads(path.read_text(encoding='utf-8'))
                if not isinstance(data,dict):data={}
            except (OSError,ValueError):data={}
            options=data.get('report_options')
            if not isinstance(options,dict):options={}
            data['report_options']=dict(options,icons=icons)
            temp=self.root/'settings.json.tmp'
            try:
                temp.write_bytes((json.dumps(data,indent=2)+'\n').encode('utf-8'))
                os.replace(temp,path)
            finally:
                if temp.exists():temp.unlink()
