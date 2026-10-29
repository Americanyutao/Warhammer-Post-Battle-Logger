"""One authenticated recording, in-memory data, and whitelisted shared assets."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import threading
import time
from urllib.parse import unquote,urlsplit
from paths import resource_path
from report_data import read_summary
from report_assets import assets_for
from settings import load_report_options
from viewer_preferences import ViewerPreferences


class ViewerSession:
    def __init__(self,source,key,root,*,autoload=True):
        self.source=Path(source)
        self.key=key;self.root=Path(root);self.autoload=autoload
        self.token=secrets.token_urlsafe(32)
        self.prefix='/'+self.token+'/'
        self.preferences=ViewerPreferences(root,source)
        self.payload=None;self.assets_payload=None;self.images=set()
        self.lock=threading.Lock();self.cancel=threading.Event();self.ready=threading.Event();self.core_ready=threading.Event()
        self.loader=None;self.error=None;self.timing={}
        self.status=dict(stage='waiting',message='Opening recording…',percent=0,core_ready=False,ready=False,error=None)
        self.server=None;self.thread=None

    @staticmethod
    def encode(value):return json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode('utf-8')

    def update(self,**values):
        with self.lock:self.status.update(values)

    def start_loading(self,*args):
        with self.lock:
            if self.loader is not None or self.cancel.is_set():return
            self.timing['load_started']=time.monotonic()
            self.loader=threading.Thread(target=self.load,name='battle-report-data',daemon=False)
            self.loader.start()

    def load_now(self):
        """Synchronous data-only entry point for checks and explicit callers."""
        self.start_loading();self.loader.join()
        if self.error:raise self.error
        return self

    def load(self):
        try:
            self.update(stage='reading',message='Reading battle data…')
            def progress(current,total):
                if self.cancel.is_set():raise InterruptedError('Report closed.')
                self.update(percent=int(100*current/max(total,1)))
            summary=read_summary(self.source,self.key,recover_tail=True,corrections_root=self.root,progress=progress,cancel=self.cancel)
            if self.cancel.is_set():return
            summary.update(report_filename=self.source.stem,assets=dict(stats={},units={},images={},provenance={}))
            self.payload=self.encode(summary)
            self.timing['core_ready']=time.monotonic();self.core_ready.set()
            self.update(stage='assets',message='Loading icons and skill details…',percent=100,core_ready=True)
            assets=assets_for(summary['units'],icons=load_report_options(self.root)['icons'],embed_images=False,
                image_prefix=self.prefix+'assets/game/')
            if self.cancel.is_set():return
            self.images=set(assets['images']);self.assets_payload=self.encode(assets)
            self.timing['ready']=time.monotonic()
            self.update(stage='ready',message='',ready=True)
        except Exception as error:
            self.error=error
            if not self.cancel.is_set():self.update(stage='error',message='Cannot open this recording.',error=str(error) or type(error).__name__)
        finally:self.ready.set()

    def __enter__(self):
        session=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def handle(self):
                try:super().handle()
                except (ConnectionResetError,BrokenPipeError):pass
            def do_POST(self):
                if self.headers.get('Host')!=session.host or self.headers.get('Origin')!=session.origin or self.headers.get('X-WH3-Viewer')!=session.token or self.path!=session.prefix+'preferences.json':
                    self.send_error(403);return
                try:
                    size=int(self.headers.get('Content-Length','0'))
                    if not 0<size<131072:raise ValueError('Invalid preference size.')
                    data=json.loads(self.rfile.read(size))
                    session.preferences.save(data['name'],data['value'])
                except (OSError,ValueError,KeyError,TypeError):self.send_error(400);return
                self.send_response(204);self.send_header('Cache-Control','no-store');self.end_headers()
            def do_GET(self):
                if self.headers.get('Host')!=session.host:
                    self.send_error(403);return
                try:path=unquote(urlsplit(self.path).path,errors='strict')
                except (ValueError,UnicodeError):self.send_error(400);return
                if not path.startswith(session.prefix):self.send_error(404);return
                relative=path[len(session.prefix):]
                if relative in ('summary.json','assets.json','loading.json'):
                    if relative=='loading.json':
                        with session.lock:data=session.encode(session.status)
                    else:data=session.payload if relative=='summary.json' else session.assets_payload
                    if data is None:
                        self.send_response(202);self.send_header('Cache-Control','no-store');self.send_header('Content-Length','0');self.end_headers();return
                    content='application/json; charset=utf-8';cached=False
                elif relative=='preferences.json':data=json.dumps(session.preferences.load()).encode('utf-8');content='application/json; charset=utf-8';cached=False
                elif relative in ('index.html','viewer_boot.js','report_view.js','report.css'):
                    filename='viewer_shell.html' if relative=='index.html' else relative
                    data=(resource_path('src')/filename).read_bytes()
                    content='text/html; charset=utf-8' if relative=='index.html' else 'text/css; charset=utf-8' if relative.endswith('.css') else 'text/javascript; charset=utf-8'
                    cached=False
                elif relative.startswith('assets/game/'):
                    name=relative[len('assets/game/'):]
                    path=(resource_path('assets/game')/name).resolve()
                    if name not in session.images or not path.is_relative_to(resource_path('assets/game').resolve()) or path.suffix.lower()!='.png':
                        self.send_error(404);return
                    try:data=path.read_bytes()
                    except OSError:self.send_error(404);return
                    content='image/png';cached=True
                else:self.send_error(404);return
                self.send_response(200)
                self.send_header('Content-Type',content)
                self.send_header('Content-Length',str(len(data)))
                self.send_header('Cache-Control','private, max-age=31536000' if cached else 'no-store')
                self.send_header('X-Content-Type-Options','nosniff')
                self.send_header('Referrer-Policy','no-referrer')
                self.send_header('Content-Security-Policy',"default-src 'none'; script-src 'self' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self'; connect-src 'self'; base-uri 'self'; frame-ancestors 'none'")
                self.end_headers()
                try:self.wfile.write(data)
                except (BrokenPipeError,ConnectionResetError):pass
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.host='127.0.0.1:'+str(self.server.server_port)
        self.origin='http://'+self.host
        self.url=self.origin+self.prefix+'index.html'
        self.thread=threading.Thread(target=self.server.serve_forever,kwargs=dict(poll_interval=.1),daemon=True,name='battle-report-assets')
        self.thread.start()
        if self.autoload:self.start_loading()
        return self

    def __exit__(self,*args):
        self.cancel.set()
        if self.loader:self.loader.join()
        if self.server:self.server.shutdown();self.server.server_close()
        if self.thread:self.thread.join()
        self.payload=None;self.assets_payload=None;self.images.clear();self.key=None
