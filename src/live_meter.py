"""Small live-only display, sharing the safe meter's ranked rows and animation.

The recorder owns the only game reader. A loopback, token-protected snapshot
feeds this separate UI process; no extra readings or live cache files are made.
"""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import math
from pathlib import Path
import queue
import secrets
import subprocess
import sys
import threading
from types import SimpleNamespace
from urllib.parse import urlsplit
from urllib.request import urlopen,Request
from paths import FROZEN,DATA_ROOT
from settings import Settings

COLUMNS=(('DAMAGE DEALT','damage'),('HEALING BUDGET REMAINING','healing_budget_remaining_hp'))


def entries_for(snapshot,side=None,sort='damage'):
    entries=[]
    for row in snapshot.get('units',[]):
        if side is not None and row.get('side')!=side:continue
        if sort=='healing_budget_remaining_hp' and row.get('departed') is True:continue
        values={key:row.get(key) if type(row.get(key)) in (int,float) and math.isfinite(row[key]) and row[key]>=0 else None
                for key in ('damage','healing_budget_remaining_hp')}
        entries.append(SimpleNamespace(sample=SimpleNamespace(uid=str(row['id']),address=0,result=0,name=row.get('name') or 'Unknown unit',side=row.get('side')),
            **values,healing_budget_unlimited=row.get('healing_budget_unlimited') is True,
            dimmed=(not row['final_detectable'] if not snapshot.get('active',True) and row.get('final_detectable') is not None else row.get('departed') is True or not row.get('present',True) or not row.get('fresh',True))))
    return sorted(entries,key=lambda entry:(getattr(entry,sort) is None,-(getattr(entry,sort) or 0),entry.sample.name))


class LiveMeterManager:
    def __init__(self,root=DATA_ROOT,settings=None):
        self.root=Path(root)
        self.enabled=False;self.server=None;self.thread=None;self.child=None
        self.snapshot=dict(generation=0,active=False,units=[],status='Waiting for battle')
        self.dismissed_generation=None;self.closing=False;self.settings=settings or Settings(root)
        self.display=self.settings.live_meter_options();self.display_revision=0;self.show_revision=0

    def start_server(self):
        if self.server:return
        manager=self;token=secrets.token_urlsafe(32);path='/'+token+'/state.json'
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                if self.headers.get('Host')!=manager.host or self.path!=path or self.headers.get('X-WH3-Meter')!='1' or self.headers.get('Origin'):
                    self.send_error(403);return
                try:
                    size=int(self.headers.get('Content-Length','0'))
                    if not 0<size<=4096:raise ValueError('Invalid preference size.')
                    data=json.loads(self.rfile.read(size))
                    if not isinstance(data,dict) or set(data)-{'layout'}:raise ValueError('Invalid preferences.')
                    manager.settings.save(live_meter_layout=data.get('layout'))
                    manager.display=manager.settings.live_meter_options();manager.display_revision+=1
                except (OSError,ValueError,TypeError):self.send_error(400);return
                self.send_response(204);self.end_headers()
            def do_GET(self):
                if self.headers.get('Host')!=manager.host or self.path!=path:self.send_error(404);return
                raw=json.dumps(dict(manager.snapshot,closing=manager.closing,show_revision=manager.show_revision,display=dict(manager.display,revision=manager.display_revision)),ensure_ascii=False,allow_nan=False).encode('utf-8')
                self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store')
                self.send_header('Content-Length',str(len(raw)));self.end_headers()
                try:self.wfile.write(raw)
                except (BrokenPipeError,ConnectionResetError):pass
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.host='127.0.0.1:'+str(self.server.server_port);self.url='http://'+self.host+path
        self.thread=threading.Thread(target=self.server.serve_forever,kwargs=dict(poll_interval=.1),daemon=True,name='live-meter-snapshots');self.thread.start()

    @property
    def is_open(self):
        if self.child and self.child.poll() is not None:self.child=None
        return self.child is not None

    def set_enabled(self,enabled,*,show_now=False):
        # Kept for callers, but incoming data and preference saves never open UI.
        if not enabled:self.close()
        elif show_now:self.open_window()

    def update(self,snapshot):
        self.snapshot=snapshot
        self.is_open

    def open_window(self):
        if self.is_open:self.show_revision+=1;return
        self.enabled=True;self.start_server();self.closing=False
        command=[sys.executable]
        if not FROZEN:command+=['-B',str(Path(__file__).with_name('release_app.py'))]
        command+=['--data-dir',str(self.root),'--live-meter-url',self.url]
        self.child=subprocess.Popen(command,creationflags=0x08000000 if sys.platform=='win32' else 0)

    def close_window(self):
        self.closing=True
        if self.child:
            try:self.child.wait(timeout=3)
            except subprocess.TimeoutExpired:self.child.terminate();self.child.wait(timeout=3)
        self.child=None

    def close(self):
        self.enabled=False;self.close_window()
        if self.server:self.server.shutdown();self.server.server_close();self.server=None
        if self.thread:self.thread.join(timeout=2);self.thread=None


def run_live_meter(url,check_output=None,data_root=DATA_ROOT):
    if urlsplit(url).scheme!='http' or urlsplit(url).hostname!='127.0.0.1':raise ValueError('Invalid live meter connection.')
    import tkinter as tk
    from live_meter_window import LiveMeterWindow
    from icons import set_app_identity,set_window_icon
    set_app_identity('release');root=tk.Tk();root.withdraw();set_window_icon(root)
    preferences=queue.Queue(maxsize=1)
    def save_preferences(value):
        try:previous=preferences.get_nowait()
        except queue.Empty:previous={}
        preferences.put_nowait(dict(previous,**value))
    window=LiveMeterWindow(root,check_output,Settings(data_root).live_meter_options(),save_preferences)
    channel=queue.Queue(maxsize=1);stop=threading.Event();current=None;pending_changes={}
    def fetch():
        nonlocal pending_changes
        failures=0
        while not stop.is_set():
            try:
                try:pending_changes.update(preferences.get_nowait())
                except queue.Empty:pass
                if pending_changes:
                    request=Request(url,data=json.dumps(pending_changes).encode('utf-8'),headers={'Content-Type':'application/json','X-WH3-Meter':'1'},method='POST')
                    with urlopen(request,timeout=2):pass
                    pending_changes={}
                with urlopen(url,timeout=2) as response:data=json.load(response)
                failures=0
            except (OSError,ValueError):
                failures+=1;data=dict(closing=failures>=5)
            try:channel.get_nowait()
            except queue.Empty:pass
            channel.put_nowait(data)
            if data.get('closing'):return
            stop.wait(.2)
    def poll():
        nonlocal current
        if not window.process_native_input():return
        try:data=channel.get_nowait()
        except queue.Empty:pass
        else:
            if data.get('closing'):root.destroy();return
            if data.get('units') is not None and data!=current:
                current=data;window.apply_snapshot(data)
        root.after(100,poll)
    thread=threading.Thread(target=fetch,daemon=True,name='live-meter-data');thread.start()
    root.after(100,poll);window.show()
    try:root.mainloop()
    finally:
        window.flush_preferences();stop.set();thread.join(timeout=3)
        # The normal debounce saves before closing; the final geometry/scope is
        # also flushed through the same authenticated parent writer.
        try:pending_changes.update(preferences.get_nowait())
        except queue.Empty:pass
        if pending_changes:
            try:
                with urlopen(Request(url,data=json.dumps(pending_changes).encode('utf-8'),headers={'Content-Type':'application/json','X-WH3-Meter':'1'},method='POST'),timeout=1):pass
            except OSError:pass
