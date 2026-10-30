"""Local report preferences, separate from replaceable application files."""
import json
from pathlib import Path
import os
import threading
from paths import DATA_ROOT
from meter_preferences import clean_layout

ICONS_TIP='Show bundled icons in the app viewer. Icons also increase HTML export sizes significantly. Turn off for easier sharing of HTML exports.'


def load_report_options(root=DATA_ROOT):
    try:
        path=Path(root)/'settings.json'
        if path.stat().st_size>65536:return dict(icons=True)
        data=json.loads(path.read_text(encoding='utf-8'))
        icons=data.get('report_options',{}).get('icons',True)
        return dict(icons=icons if isinstance(icons,bool) else True)
    except (OSError,ValueError,AttributeError):return dict(icons=True)


def load_logger_options(root=DATA_ROOT):
    defaults=dict(logging_interval_seconds=1,show_live_meter=True)
    try:
        path=Path(root)/'settings.json'
        if path.stat().st_size>65536:return defaults
        data=json.loads(path.read_text(encoding='utf-8')).get('logger_options',{})
        seconds=data.get('logging_interval_seconds',1);show=data.get('show_live_meter',True)
        return dict(logging_interval_seconds=seconds if type(seconds) is int and 1<=seconds<=5 else 1,
                    show_live_meter=show if isinstance(show,bool) else True)
    except (OSError,ValueError,AttributeError):return defaults


def load_live_meter_options(root=DATA_ROOT):
    options={}
    try:
        path=Path(root)/'settings.json'
        if path.stat().st_size<=65536:
            options=json.loads(path.read_text(encoding='utf-8')).get('live_meter_options',{})
    except (OSError,ValueError,AttributeError):pass
    if not isinstance(options,dict):options={}
    return dict(layout=clean_layout(options.get('layout')))


def load_meter_lifecycle(root):
    defaults=dict(open_meter_on_battle=False,close_meter_on_end=False)
    try:
        path=Path(root)/'settings.json'
        if path.stat().st_size>65536:return defaults
        options=json.loads(path.read_text(encoding='utf-8')).get('logger_options',{})
        return {key:options.get(key) if type(options.get(key)) is bool else value for key,value in defaults.items()}
    except (OSError,ValueError,AttributeError):return defaults


class Settings:
    def __init__(self,root=DATA_ROOT):
        self.root=Path(root)
        self.lock=threading.Lock()

    def report_options(self):
        with self.lock:return load_report_options(self.root)

    def logger_options(self):
        with self.lock:return load_logger_options(self.root)

    def meter_lifecycle(self):
        with self.lock:return load_meter_lifecycle(self.root)

    def live_meter_options(self):
        with self.lock:return load_live_meter_options(self.root)

    def save(self,*,icons=None,logging_interval_seconds=None,show_live_meter=None,live_meter_layout=None,open_meter_on_battle=None,close_meter_on_end=None):
        for value in (open_meter_on_battle,close_meter_on_end):
            if value is not None and type(value) is not bool:raise ValueError('Meter options must be checked or unchecked.')
        if icons is not None and not isinstance(icons,bool):raise ValueError('Icons must be checked or unchecked.')
        if logging_interval_seconds is not None and (type(logging_interval_seconds) is not int or not 1<=logging_interval_seconds<=5):
            raise ValueError('Choose a logging interval from 1 to 5 seconds.')
        if show_live_meter is not None and not isinstance(show_live_meter,bool):raise ValueError('Live meter must be checked or unchecked.')
        if live_meter_layout is not None and (not isinstance(live_meter_layout,dict) or clean_layout(live_meter_layout)!=live_meter_layout):raise ValueError('Invalid meter layout.')
        with self.lock:
            self.root.mkdir(parents=True,exist_ok=True)
            path=self.root/'settings.json'
            try:
                data=json.loads(path.read_text(encoding='utf-8'))
                if not isinstance(data,dict):data={}
            except (OSError,ValueError):data={}
            if icons is not None:
                options=data.get('report_options')
                data['report_options']=dict(options if isinstance(options,dict) else {},icons=icons)
            if any(value is not None for value in (logging_interval_seconds,show_live_meter,open_meter_on_battle,close_meter_on_end)):
                options=data.get('logger_options')
                options=dict(options) if isinstance(options,dict) else {}
                if logging_interval_seconds is not None:options['logging_interval_seconds']=logging_interval_seconds
                if show_live_meter is not None:options['show_live_meter']=show_live_meter
                for key,value in [('open_meter_on_battle',open_meter_on_battle),('close_meter_on_end',close_meter_on_end)]:
                    if value is not None:options[key]=value
                data['logger_options']=options
            if live_meter_layout is not None:data['live_meter_options']=dict(layout=live_meter_layout)
            temp=self.root/'settings.json.tmp'
            try:
                temp.write_bytes((json.dumps(data,indent=2)+'\n').encode('utf-8'))
                os.replace(temp,path)
            finally:
                if temp.exists():temp.unlink()
