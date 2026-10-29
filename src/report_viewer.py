"""Embedded report window. Shared renderer/assets; no standalone HTML output."""
import json
from pathlib import Path
import threading
import time
import sys
import webbrowser
from paths import FROZEN
from icons import ICON_PATH,set_app_identity
from logfile import load_key
from viewer_cache import ViewerCache
from viewer_server import ViewerSession

COMMUNITY_LINKS=frozenset(('https://www.youtube.com/@Americanyutao','https://discord.com/invite/v27y7AW7Kz'))


class NativePopouts:
    """Keep existing synchronous window.open graph controls inside WebView2."""
    def __init__(self,window,session):
        self.window=window;self.session=session;self.forms=[];self.handlers=[]
        self.ready=threading.Event();self.errors=[]

    def install(self,*args):
        from System import Action
        def attach():
            if self.ready.is_set():return
            browser=self.window.native.browser
            core=browser.webview.CoreWebView2
            if core is None:
                def initialized(sender,event):
                    if event.IsSuccess:attach()
                    else:self.errors.append(str(event.InitializationException))
                browser.webview.CoreWebView2InitializationCompleted+=initialized
                self.handlers.append(initialized)
                return
            core.NewWindowRequested-=browser.on_new_window_request
            core.NewWindowRequested+=self.open
            core.NavigationStarting+=self.guard
            core.Settings.AreDefaultScriptDialogsEnabled=False
            self.window.native.FormClosing+=self.close_all
            self.ready.set()
        self.window.native.Invoke(Action(attach))

    def guard(self,sender,args):
        uri=str(args.Uri)
        if uri!='about:blank' and not uri.startswith(self.session.origin+self.session.prefix):args.Cancel=True

    def evaluate(self,script):
        from System import Func,Object
        native=self.window.native
        task=native.Invoke(Func[Object](lambda:native.browser.webview.CoreWebView2.ExecuteScriptAsync(script)))
        deadline=time.monotonic()+15
        while not task.IsCompleted:
            if time.monotonic()>deadline:raise RuntimeError('Embedded renderer did not respond to the script check.')
            time.sleep(.02)
        if task.IsFaulted:raise RuntimeError(str(task.Exception))
        return json.loads(str(task.Result))

    def capture(self,path):
        from System import Func,Object
        from System.IO import FileStream,FileMode
        from Microsoft.Web.WebView2.Core import CoreWebView2CapturePreviewImageFormat
        stream=FileStream(str(path),FileMode.Create)
        try:
            native=self.window.native
            task=native.Invoke(Func[Object](lambda:native.browser.webview.CoreWebView2.CapturePreviewAsync(CoreWebView2CapturePreviewImageFormat.Png,stream)))
            deadline=time.monotonic()+15
            while not task.IsCompleted:
                if time.monotonic()>deadline:raise RuntimeError('Report screenshot did not finish.')
                time.sleep(.02)
            if task.IsFaulted:raise RuntimeError(str(task.Exception))
        finally:stream.Dispose()

    def close_all(self,*args):
        for form in list(self.forms):form.Close()

    def open(self,sender,args):
        args.Handled=True
        if str(args.Uri) in COMMUNITY_LINKS:
            webbrowser.open(str(args.Uri));return
        if str(args.Uri) not in ('','about:blank') or len(self.forms)>=4:return
        from System.Windows.Forms import Form,DockStyle,FormStartPosition
        from Microsoft.Web.WebView2.WinForms import WebView2,CoreWebView2CreationProperties
        from System.Drawing import Color
        deferral=args.GetDeferral()
        form=Form();form.Text='Battle graph';form.Width=760;form.Height=470
        form.Icon=self.window.native.Icon;form.BackColor=Color.FromArgb(13,17,26)
        form.StartPosition=FormStartPosition.CenterParent
        control=WebView2();control.Dock=DockStyle.Fill
        properties=CoreWebView2CreationProperties()
        properties.UserDataFolder=self.window.native.browser.webview.CreationProperties.UserDataFolder
        properties.set_IsInPrivateModeEnabled(True)
        control.CreationProperties=properties
        control.DefaultBackgroundColor=form.BackColor;form.Controls.Add(control)
        self.forms.append(form)
        def closed(*unused):
            control.Dispose()
            if form in self.forms:self.forms.remove(form)
        def initialized(sender,event):
            try:
                if not event.IsSuccess:raise RuntimeError(str(event.InitializationException))
                core=control.CoreWebView2
                core.NavigationStarting+=self.guard
                core.NewWindowRequested+=self.block_popout
                core.Settings.AreDefaultContextMenusEnabled=False
                core.Settings.AreDefaultScriptDialogsEnabled=False
                core.Settings.AreDevToolsEnabled=False
                def title(*unused):form.Text=str(core.DocumentTitle) or 'Battle graph'
                def close_requested(*unused):form.Close()
                core.DocumentTitleChanged+=title
                core.WindowCloseRequested+=close_requested
                self.handlers.extend((title,close_requested))
                args.NewWindow=core
            except Exception as error:
                self.errors.append(str(error));form.Close()
            finally:deferral.Complete()
        form.FormClosed+=closed
        control.CoreWebView2InitializationCompleted+=initialized
        self.handlers.extend((closed,initialized))
        try:
            control.EnsureCoreWebView2Async(sender.Environment)
            form.Show(self.window.native)
        except Exception:
            form.Close();deferral.Complete();raise

    def block_popout(self,sender,args):args.Handled=True


def run_viewer(source,root,key_path=None,check_output=None):
    # Imported only in a viewer process; the recorder/tray never load this runtime.
    if not FROZEN:sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'build/embedded-viewer-deps'))
    import webview
    source=Path(source).resolve();root=Path(root).resolve()
    key=load_key(key_path or root/'captures/logger.key')
    set_app_identity('report')
    result={}
    with ViewerCache(root) as cache:
        cache_path=cache.path
        with ViewerSession(source,key,root,autoload=False) as session:
            webview.settings['OPEN_EXTERNAL_LINKS_IN_BROWSER']=False
            webview.settings['ALLOW_FILE_URLS']=False
            webview.settings['ALLOW_DOWNLOADS']=False
            window=webview.create_window('Battle overview: '+source.stem,session.url,
                width=1380,height=900,min_size=(960,640),background_color='#0D111A',text_select=True)
            popouts=NativePopouts(window,session)
            def shown(*args):
                session.timing['window_shown']=time.monotonic()
                session.start_loading()
            window.events.shown+=shown
            window.events.shown+=popouts.install
            window.events.loaded+=popouts.install
            def validate():
                try:
                    deadline=time.monotonic()+30
                    while not popouts.ready.wait(.1):
                        if popouts.errors:raise RuntimeError(popouts.errors[-1])
                        if time.monotonic()>deadline:raise RuntimeError('Embedded renderer did not initialize.')
                    deadline=time.monotonic()+30
                    while time.monotonic()<deadline:
                        error=popouts.evaluate('document.documentElement.dataset.viewerError||null')
                        if error:raise RuntimeError(error)
                        if popouts.evaluate('document.documentElement.dataset.viewerReady==="true"'):break
                        time.sleep(.1)
                    else:raise RuntimeError('Report data did not finish loading: '+str(popouts.evaluate('({url:location.href,text:document.body.innerText})')))
                    result.update(popouts.evaluate('({units:D.units.length,samples:D.samples,rows:document.querySelectorAll("#rows tr").length,images:Object.values(A.images),title:document.title,warnings:D.recording_warnings})'))
                    if not result['units'] or not result['rows']:raise RuntimeError('No battle rows rendered.')
                    if not all(value.startswith(session.prefix+'assets/game/') for value in result['images']):raise RuntimeError('Viewer images were embedded instead of shared.')
                    deadline=time.monotonic()+10
                    while time.monotonic()<deadline:
                        if popouts.evaluate('Array.from(document.images).every(i=>i.complete&&i.naturalWidth>0)'):break
                        time.sleep(.1)
                    else:raise RuntimeError('A bundled report image failed to load.')
                    result['shared_images_loaded']=True
                    result['effect_definitions']=popouts.evaluate('Object.keys(A.effect_texts||{}).length')
                    result['diagnostics_absent']=popouts.evaluate('!D.performance&&!Object.keys(D.capture||{}).some(k=>["process_cpu_seconds","wall_seconds","io_seconds"].includes(k))')
                    if not result['diagnostics_absent']:raise RuntimeError('Release report contains debug performance data.')
                    popouts.evaluate('showView("unit");publishTime(D.start_s||0)')
                    result['map_all_units']=popouts.evaluate('movementUnits(D.units[0]).length===D.units.length&&document.querySelectorAll("#movement-positions .movement-position").length===D.units.length')
                    popouts.evaluate('document.getElementById("movement-time").onclick();window.__mapLockedTime=movementState().time;publishTime(D.end_s)')
                    result['map_lock_isolated']=popouts.evaluate('movementState().locked&&movementState().time===window.__mapLockedTime&&sharedTime===D.end_s')
                    popouts.evaluate('document.getElementById("movement-time").onclick();publishTime(D.end_s);document.getElementById("movement").scrollIntoView({block:"center"})')
                    popouts.capture(Path(check_output).with_suffix('.map.png'))
                    if not result['map_all_units'] or not result['map_lock_isolated']:raise RuntimeError('All-unit map or isolated sample lock failed.')
                    popouts.evaluate('showView("main");window.scrollTo(0,0)')
                    popouts.capture(Path(check_output).with_suffix('.main.png'))
                    popouts.evaluate('showView("unit");openMini(0)')
                    deadline=time.monotonic()+15
                    while time.monotonic()<deadline:
                        if popouts.evaluate('minis.length===1&&!!minis[0].win.document.getElementById("mini-chart")'):break
                        time.sleep(.1)
                    else:raise RuntimeError('Native graph popout did not render: '+str(popouts.errors))
                    result['native_popout']=True
                    popouts.capture(Path(check_output).with_suffix('.unit.png'))
                    popouts.evaluate('minis[0].win.close()')
                    deadline=time.monotonic()+10
                    while time.monotonic()<deadline:
                        if popouts.evaluate('minis.length===0'):break
                        time.sleep(.1)
                    else:raise RuntimeError('Native graph popout did not close.')
                    result['success']=True
                    result['window_shown_before_decode']=session.timing['window_shown']<=session.timing['load_started']<=session.timing['core_ready']<=session.timing['ready']
                    if not result['window_shown_before_decode']:raise RuntimeError('Report decoding started before the window appeared.')
                except Exception as error:result.update(success=False,error=str(error))
                finally:window.destroy()
            webview.start(validate if check_output else None,gui='edgechromium',private_mode=True,
                storage_path=str(cache.path/'browser'),icon=str(ICON_PATH),debug=False)
    if check_output:
        result['cache_removed']=not cache_path.exists()
        result['cache_path']=str(cache_path)
        Path(check_output).write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        if not result.get('success') or not result['cache_removed']:raise RuntimeError(result.get('error') or 'Viewer cache was not released.')
