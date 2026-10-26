"""Small native Windows update/about windows; no additional UI runtime."""
import ctypes
from ctypes import wintypes as w
import os
import math
import threading
import time
from collections import deque
import webbrowser
from version import VERSION
from icons import load_tray_icon
from settings import ICONS_TIP

RELEASE_NOTES='https://github.com/Americanyutao/Warhammer-Post-Battle-Logger/releases'


class Cancelled(Exception):
    pass


class ProgressWindow:
    def __init__(self, title='Battle Logger update', cancellable=True, about=False, settings=None):
        self.title=title; self.cancellable=cancellable; self.about=about
        self.settings=settings
        self.cancelled=threading.Event();self.ready=threading.Event()
        self.hwnd=None;self.error=None;self.text='Checking for updates…';self.percent=0
        self.done=0;self.total=0;self.unit='files'
        self.current_file='Application files';self.items_remaining=None
        self.paused=threading.Event();self.phase=None;self.speed=0
        self.samples=deque(maxlen=80);self.history=deque(maxlen=60);self.reset_rate=False;self.last_paint=0
        self.thread=threading.Thread(target=self.run,name='battle-logger-update-window',daemon=True)
    def start(self):
        self.thread.start()
        if not self.ready.wait(5) or self.error:
            raise RuntimeError(self.error or 'Could not open the update window.')
        return self
    @property
    def headline(self):
        return 'Cancelling update…' if self.cancelled.is_set() and self.cancellable else f'{self.percent}% '+('paused' if self.paused.is_set() else 'complete')
    @property
    def details(self):
        if not self.total:return 'Please wait…'
        if self.unit=='bytes':
            action='installed' if self.text.startswith(('Installing','Installation')) else 'downloaded'
            return f'{self.done/1048576:.2f} MB / {self.total/1048576:.2f} MB {action}'
        return f'{self.done:,} / {self.total:,} files checked'
    @property
    def time_remaining(self):
        if self.total and self.done>=self.total:return 'Complete'
        if self.unit!='bytes' or self.speed<=0 or self.paused.is_set():return 'Calculating…'
        seconds=max(1,math.ceil((self.total-self.done)/self.speed))
        return ('About 1 second' if seconds==1 else f'About {seconds} seconds') if seconds<60 else ('About 1 minute' if seconds<=60 else f'About {math.ceil(seconds/60)} minutes')
    @property
    def item_details(self):
        count=self.items_remaining if self.items_remaining is not None else (max(0,self.total-self.done) if self.unit=='files' else None)
        return 'Calculating…' if count is None else f'{count:,}'
    def update(self, text, done=0, total=0, unit='files', current_file='', items_remaining=None, check_cancel=True):
        while check_cancel and self.paused.is_set() and not self.cancelled.is_set():time.sleep(.05)
        if check_cancel and self.cancelled.is_set():raise Cancelled()
        now=time.monotonic()
        previous=(self.phase,self.percent,self.current_file)
        phase=(unit,'install' if text.startswith(('Installing','Installation')) else 'download' if text.startswith('Downloading') else text)
        if phase!=self.phase or self.reset_rate or done<self.done:
            self.samples.clear();self.history.clear();self.speed=0;self.phase=phase;self.reset_rate=False
        if unit=='bytes':
            self.samples.append((now,done))
            while len(self.samples)>2 and now-self.samples[1][0]>5:self.samples.popleft()
            first,baseline=self.samples[0]
            self.speed=max(0,(done-baseline)/(now-first)) if now-first>.05 else 0
            if self.speed:self.history.append(self.speed)
        self.text=text;self.done=max(0,done);self.total=max(0,total);self.unit=unit
        if current_file:self.current_file=current_file
        self.items_remaining=items_remaining
        self.percent=max(0,min(100,math.floor(done/total*100))) if total else 0
        if text=='Installation complete':self.cancellable=False;self.items_remaining=0
        if self.hwnd and (now-self.last_paint>=.05 or previous!=(self.phase,self.percent,self.current_file) or text=='Installation complete'):
            self.last_paint=now;self.user.PostMessageW(self.hwnd,0x8003,0,0)
    def close(self):
        if self.hwnd:self.user.PostMessageW(self.hwnd,0x8004,0,0)
        if self.thread.is_alive():self.thread.join(timeout=3)
    def focus(self):
        if self.hwnd:self.user.PostMessageW(self.hwnd,0x8005,0,0)
    def run(self):
        try:self.loop()
        except Exception as error:self.error=str(error)
        finally:self.ready.set()
    def loop(self):
        user=self.user=ctypes.WinDLL('user32',use_last_error=True)
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        common=ctypes.WinDLL('comctl32',use_last_error=True)
        common.InitCommonControls()
        gdi=ctypes.WinDLL('gdi32',use_last_error=True)
        gdi.CreateFontW.argtypes=[ctypes.c_int]*5+[w.DWORD]*8+[w.LPCWSTR];gdi.CreateFontW.restype=w.HANDLE
        gdi.DeleteObject.argtypes=[w.HANDLE]
        gdi.GetStockObject.argtypes=[ctypes.c_int];gdi.GetStockObject.restype=w.HBRUSH
        gdi.SetBkColor.argtypes=[w.HDC,w.DWORD]
        gdi.SetTextColor.argtypes=[w.HDC,w.DWORD]
        white=gdi.GetStockObject(0)
        fonts=[]
        Proc=ctypes.WINFUNCTYPE(ctypes.c_ssize_t,w.HWND,w.UINT,w.WPARAM,w.LPARAM)
        class WC(ctypes.Structure):
            _fields_=[('style',w.UINT),('proc',Proc),('clsExtra',ctypes.c_int),('wndExtra',ctypes.c_int),
                      ('instance',w.HINSTANCE),('icon',w.HICON),('cursor',w.HANDLE),('background',w.HBRUSH),
                      ('menu',w.LPCWSTR),('name',w.LPCWSTR)]
        kernel.GetModuleHandleW.argtypes=[w.LPCWSTR];kernel.GetModuleHandleW.restype=w.HMODULE
        user.RegisterClassW.argtypes=[ctypes.POINTER(WC)];user.RegisterClassW.restype=w.ATOM
        user.UnregisterClassW.argtypes=[w.LPCWSTR,w.HINSTANCE]
        user.CreateWindowExW.argtypes=[w.DWORD,w.LPCWSTR,w.LPCWSTR,w.DWORD,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,w.HWND,w.HMENU,w.HINSTANCE,ctypes.c_void_p];user.CreateWindowExW.restype=w.HWND
        user.DefWindowProcW.argtypes=[w.HWND,w.UINT,w.WPARAM,w.LPARAM];user.DefWindowProcW.restype=ctypes.c_ssize_t
        user.PostMessageW.argtypes=[w.HWND,w.UINT,w.WPARAM,w.LPARAM]
        user.SendMessageW.argtypes=[w.HWND,w.UINT,w.WPARAM,w.LPARAM];user.SendMessageW.restype=ctypes.c_ssize_t
        user.DestroyWindow.argtypes=[w.HWND]
        user.DestroyIcon.argtypes=[w.HICON]
        user.SetWindowTextW.argtypes=[w.HWND,w.LPCWSTR]
        user.MessageBoxW.argtypes=[w.HWND,w.LPCWSTR,w.LPCWSTR,w.UINT]
        user.EnableWindow.argtypes=[w.HWND,w.BOOL]
        user.AdjustWindowRect.argtypes=[ctypes.POINTER(w.RECT),w.DWORD,w.BOOL]
        user.GetMessageW.argtypes=[ctypes.POINTER(w.MSG),w.HWND,w.UINT,w.UINT]
        user.TranslateMessage.argtypes=[ctypes.POINTER(w.MSG)];user.DispatchMessageW.argtypes=[ctypes.POINTER(w.MSG)];user.DispatchMessageW.restype=ctypes.c_ssize_t
        user.IsDialogMessageW.argtypes=[w.HWND,ctypes.POINTER(w.MSG)];user.IsDialogMessageW.restype=w.BOOL
        user.ShowWindow.argtypes=[w.HWND,ctypes.c_int];user.SetForegroundWindow.argtypes=[w.HWND]
        instance=kernel.GetModuleHandleW(None)
        name=f'WH3LoggerUpdate_{os.getpid()}_{id(self)}'
        label=bar=heading=details=cancel=pause=filename=remaining=items=toggle=None
        icons_checkbox=None
        expanded=True
        class DrawItem(ctypes.Structure):
            _fields_=[('kind',w.UINT),('ident',w.UINT),('item',w.UINT),('action',w.UINT),('state',w.UINT),('hwnd',w.HWND),('dc',w.HDC),('rect',w.RECT),('data',ctypes.c_size_t)]
        gdi.CreateSolidBrush.argtypes=[w.DWORD];gdi.CreateSolidBrush.restype=w.HBRUSH
        gdi.CreatePen.argtypes=[ctypes.c_int,ctypes.c_int,w.DWORD];gdi.CreatePen.restype=w.HANDLE
        gdi.SelectObject.argtypes=[w.HDC,w.HANDLE];gdi.SelectObject.restype=w.HANDLE
        gdi.MoveToEx.argtypes=[w.HDC,ctypes.c_int,ctypes.c_int,ctypes.c_void_p]
        gdi.LineTo.argtypes=[w.HDC,ctypes.c_int,ctypes.c_int]
        gdi.Polygon.argtypes=[w.HDC,ctypes.POINTER(w.POINT),ctypes.c_int]
        user.FillRect.argtypes=[w.HDC,ctypes.POINTER(w.RECT),w.HBRUSH]
        user.FrameRect.argtypes=[w.HDC,ctypes.POINTER(w.RECT),w.HBRUSH]
        user.InvalidateRect.argtypes=[w.HWND,ctypes.c_void_p,w.BOOL]
        user.DrawTextW.argtypes=[w.HDC,w.LPCWSTR,ctypes.c_int,ctypes.POINTER(w.RECT),w.UINT]
        user.SetWindowPos.argtypes=[w.HWND,w.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,w.UINT]
        def draw_graph(draw):
            r=draw.rect;width=r.right-r.left;height=r.bottom-r.top
            dc=draw.dc;objects=[]
            def brush(color):
                obj=gdi.CreateSolidBrush(color);objects.append(obj);return obj
            user.FillRect(dc,ctypes.byref(r),brush(0xffffff))
            filled=w.RECT(r.left,r.top,r.left+int(width*self.percent/100),r.bottom)
            user.FillRect(dc,ctypes.byref(filled),brush(0x9fe68f))
            pen=gdi.CreatePen(0,1,0xc0edb8);objects.append(pen);old_pen=gdi.SelectObject(dc,pen)
            try:
                for x in range(0,width,49):gdi.MoveToEx(dc,r.left+x,r.top,None);gdi.LineTo(dc,r.left+x,r.bottom)
                for y in range(0,height,16):gdi.MoveToEx(dc,r.left,r.top+y,None);gdi.LineTo(dc,r.right,r.top+y)
                values=list(self.history)
                if values and filled.right>r.left:
                    peak=max(values)*1.25;count=max(1,len(values)-1)
                    points=[w.POINT(r.left,r.bottom)]
                    points += [w.POINT(r.left+int((filled.right-r.left)*i/count),r.bottom-3-int((height-8)*v/peak)) for i,v in enumerate(values)]
                    points += [w.POINT(filled.right,r.bottom)]
                    old_brush=gdi.SelectObject(dc,brush(0x22b308));green=gdi.CreatePen(0,1,0x22b308);objects.append(green);gdi.SelectObject(dc,green)
                    try:gdi.Polygon(dc,(w.POINT*len(points))(*points),len(points))
                    finally:gdi.SelectObject(dc,old_brush)
                gdi.SetBkColor(dc,0xffffff);gdi.SetTextColor(dc,0)
                speed='Speed: paused' if self.paused.is_set() else f'Speed: {self.speed/1048576:.1f} MB/s' if self.speed and self.unit=='bytes' else 'Speed: calculating…'
                text_rect=w.RECT(r.left+8,r.bottom-22,r.right-8,r.bottom-3)
                user.DrawTextW(dc,speed,-1,ctypes.byref(text_rect),0x2|0x20)
                user.FrameRect(dc,ctypes.byref(r),brush(0xaaaaaa))
            finally:
                gdi.SelectObject(dc,old_pen)
                for obj in objects:gdi.DeleteObject(obj)
        def callback(hwnd,msg,wp,lp):
            nonlocal expanded
            if msg==0x8005:
                user.ShowWindow(hwnd,9);user.SetForegroundWindow(hwnd);return 0
            if self.settings is not None and msg==0x111 and (wp&0xffff)==2:
                user.DestroyWindow(hwnd);return 0
            if self.settings is not None and msg==0x111 and (wp&0xffff)==6:
                try:self.settings.save(icons=user.SendMessageW(icons_checkbox,0xf0,0,0)==1)
                except (OSError,ValueError) as error:
                    user.MessageBoxW(hwnd,str(error),'Could not save settings',0x10);return 0
                user.DestroyWindow(hwnd);return 0
            if msg==0x2b:
                draw=ctypes.cast(lp,ctypes.POINTER(DrawItem)).contents
                if draw.ident==3:draw_graph(draw);return 1

            if msg==0x138:
                gdi.SetBkColor(wp,0xffffff);gdi.SetTextColor(wp,0x333333)
                return white
            if msg==0x8003:
                if label:user.SetWindowTextW(label,self.text)
                if heading:user.SetWindowTextW(heading,self.headline)
                if details:user.SetWindowTextW(details,self.details)
                if cancel:user.EnableWindow(cancel,self.cancellable and not self.cancelled.is_set())
                if filename:user.SetWindowTextW(filename,'Name: '+self.current_file)
                if remaining:user.SetWindowTextW(remaining,'Time remaining: '+self.time_remaining)
                if items:user.SetWindowTextW(items,'Items remaining: '+self.item_details)
                if bar:user.InvalidateRect(bar,None,True)
                if not self.about:user.SetWindowTextW(hwnd,self.headline+' - '+self.title)
                if pause:
                    user.SetWindowTextW(pause,'Resume' if self.paused.is_set() else 'Pause')
                    user.EnableWindow(pause,self.cancellable and not self.cancelled.is_set())
                return 0
            if msg==0x111 and (wp&0xffff)==4:
                if self.paused.is_set():self.paused.clear();self.reset_rate=True
                else:self.paused.set()
                user.PostMessageW(hwnd,0x8003,0,0);return 0
            if msg==0x111 and (wp&0xffff)==5:
                expanded=not expanded
                for control in (filename,remaining,items):user.ShowWindow(control,5 if expanded else 0)
                user.SetWindowTextW(toggle,'Fewer details' if expanded else 'More details')
                bottom=300 if expanded else 220
                for control,x,width in ((toggle,24,150),(cancel,406,110)):
                    user.SetWindowPos(control,None,x,bottom,width,30,0x4)
                rect=w.RECT(0,0,540,bottom+46);user.AdjustWindowRect(ctypes.byref(rect),0x00C80000,False)
                user.SetWindowPos(hwnd,None,0,0,rect.right-rect.left,rect.bottom-rect.top,0x6)
                return 0
            if msg==0x111 and (wp&0xffff)==2:
                webbrowser.open(RELEASE_NOTES+'/tag/v'+VERSION);return 0
            if msg==0x8004 or (msg==0x10 and (self.about or self.settings is not None)):
                user.DestroyWindow(hwnd);return 0
            if msg==0x10 or (msg==0x111 and (wp&0xffff)==1):
                if self.about or self.settings is not None:user.DestroyWindow(hwnd)
                elif self.cancellable:
                    self.cancelled.set()
                    user.PostMessageW(hwnd,0x8003,0,0)
                return 0
            if msg==2:user.PostQuitMessage(0);return 0
            return user.DefWindowProcW(hwnd,msg,wp,lp)
        icon=load_tray_icon();small_icon=load_tray_icon(16)
        proc=Proc(callback);wc=WC();wc.proc=proc;wc.instance=instance;wc.icon=icon;wc.background=white;wc.name=name
        if not user.RegisterClassW(ctypes.byref(wc)):raise ctypes.WinError(ctypes.get_last_error())
        try:
            rect=w.RECT(0,0,540,224 if self.settings is not None else 180 if self.about else 346)
            user.AdjustWindowRect(ctypes.byref(rect),0x00C80000,False)
            self.hwnd=user.CreateWindowExW(0,name,self.title,0x00C80000,0x80000000,0x80000000,rect.right-rect.left,rect.bottom-rect.top,None,None,instance,None)
            if not self.hwnd:raise ctypes.WinError(ctypes.get_last_error())
            user.SendMessageW(self.hwnd,0x80,0,small_icon)
            user.SendMessageW(self.hwnd,0x80,1,icon)
            def font(size):
                handle=gdi.CreateFontW(-size,0,0,0,400,0,0,0,1,0,0,5,0,'Segoe UI')
                if not handle:raise ctypes.WinError(ctypes.get_last_error())
                fonts.append(handle);return handle
            normal=font(14);large=font(24)
            def child(kind,text,x,y,width,height,ident=0,extra=0,large_text=False):
                result=user.CreateWindowExW(0,kind,text,0x50000000|extra,x,y,width,height,self.hwnd,ident,instance,None)
                if not result:raise ctypes.WinError(ctypes.get_last_error())
                user.SendMessageW(result,0x30,large if large_text else normal,1)
                return result
            if self.settings is not None:
                child('BUTTON','Report options',24,20,492,104,extra=7)
                icons_checkbox=child('BUTTON','Icons',44,52,450,28,7,extra=3|0x10000)
                self.icons_checkbox=icons_checkbox
                user.SendMessageW(icons_checkbox,0xf1,int(self.settings.report_options()['icons']),0)
                child('STATIC','Applies to newly generated reports.',24,140,490,22)
                child('BUTTON','Save',286,176,110,32,6,extra=1|0x10000)
                child('BUTTON','Cancel',406,176,110,32,1,extra=0x10000)
                class ToolInfo(ctypes.Structure):
                    _fields_=[('size',w.UINT),('flags',w.UINT),('hwnd',w.HWND),('ident',ctypes.c_size_t),
                        ('rect',w.RECT),('instance',w.HINSTANCE),('text',w.LPWSTR),('param',w.LPARAM),('reserved',ctypes.c_void_p)]
                tooltip_text=ctypes.create_unicode_buffer(ICONS_TIP)
                tooltip=user.CreateWindowExW(8,'tooltips_class32',None,0x80000003,0,0,0,0,self.hwnd,None,instance,None)
                if not tooltip:raise ctypes.WinError(ctypes.get_last_error())
                tool=ToolInfo();tool.size=ctypes.sizeof(tool);tool.flags=0x11;tool.hwnd=self.hwnd;tool.ident=icons_checkbox;tool.text=ctypes.cast(tooltip_text,w.LPWSTR)
                if not user.SendMessageW(tooltip,0x432,0,ctypes.addressof(tool)):raise RuntimeError('Could not create the Icons explanation.')
                user.SendMessageW(tooltip,0x418,0,360)
                self.settings_tooltip=tooltip
            elif self.about:
                label=child('STATIC',f'WARHAMMER III Battle Logger\n\nInstalled version: {VERSION}',24,20,490,65)
                child('BUTTON','GitHub release notes',24,115,220,32,2)
                child('BUTTON','Close',406,115,110,32,1)
            else:
                label=child('STATIC',self.text,24,18,490,22)
                heading=child('STATIC',self.headline,24,48,360,34,large_text=True)
                pause=child('BUTTON','Pause',428,49,88,28,4)
                user.EnableWindow(pause,self.cancellable)
                bar=child('STATIC','',24,92,492,84,3,extra=0x0d)
                details=child('STATIC',self.details,24,188,490,22)
                filename=child('STATIC','Name: '+self.current_file,24,220,490,20)
                remaining=child('STATIC','Time remaining: '+self.time_remaining,24,242,490,20)
                items=child('STATIC','Items remaining: '+self.item_details,24,264,490,20)
                toggle=child('BUTTON','Fewer details',24,300,150,30,5)
                cancel=child('BUTTON','Cancel',406,300,110,30,1)
                user.EnableWindow(cancel,self.cancellable)
            user.ShowWindow(self.hwnd,5);user.SetForegroundWindow(self.hwnd)
            self.ready.set()
            msg=w.MSG()
            while True:
                code=user.GetMessageW(ctypes.byref(msg),None,0,0)
                if code==0:break
                if code==-1:raise ctypes.WinError(ctypes.get_last_error())
                if self.settings is not None and user.IsDialogMessageW(self.hwnd,ctypes.byref(msg)):continue
                user.TranslateMessage(ctypes.byref(msg));user.DispatchMessageW(ctypes.byref(msg))
        finally:
            if self.hwnd:user.DestroyWindow(self.hwnd)
            self.hwnd=None
            for handle in fonts:gdi.DeleteObject(handle)
            user.UnregisterClassW(name,instance)
            user.DestroyIcon(small_icon);user.DestroyIcon(icon)
