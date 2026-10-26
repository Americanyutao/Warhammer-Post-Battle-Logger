"""Small native Windows update/about windows; no additional UI runtime."""
import ctypes
from ctypes import wintypes as w
import os
import threading
import webbrowser
from version import VERSION

RELEASE_NOTES='https://github.com/Americanyutao/Warhammer-Post-Battle-Logger/releases'


class Cancelled(Exception):
    pass


class ProgressWindow:
    def __init__(self, title='Battle Logger update', cancellable=True, about=False):
        self.title=title; self.cancellable=cancellable; self.about=about
        self.cancelled=threading.Event();self.ready=threading.Event()
        self.hwnd=None;self.error=None;self.text='Checking for updates…';self.percent=0
        self.thread=threading.Thread(target=self.run,name='battle-logger-update-window',daemon=True)
    def start(self):
        self.thread.start()
        if not self.ready.wait(5) or self.error:
            raise RuntimeError(self.error or 'Could not open the update window.')
        return self
    def update(self, text, done=0, total=0):
        previous=(self.text,self.percent)
        self.text=text
        self.percent=max(0,min(100,round(done/total*100))) if total else 0
        if self.hwnd and previous!=(self.text,self.percent):self.user.PostMessageW(self.hwnd,0x8003,0,0)
        if self.cancelled.is_set():raise Cancelled()
    def close(self):
        if self.hwnd:self.user.PostMessageW(self.hwnd,0x8004,0,0)
        if self.thread.is_alive():self.thread.join(timeout=3)
    def run(self):
        try:self.loop()
        except Exception as error:self.error=str(error)
        finally:self.ready.set()
    def loop(self):
        user=self.user=ctypes.WinDLL('user32',use_last_error=True)
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        common=ctypes.WinDLL('comctl32',use_last_error=True)
        common.InitCommonControls()
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
        user.SetWindowTextW.argtypes=[w.HWND,w.LPCWSTR]
        user.GetMessageW.argtypes=[ctypes.POINTER(w.MSG),w.HWND,w.UINT,w.UINT]
        user.TranslateMessage.argtypes=[ctypes.POINTER(w.MSG)];user.DispatchMessageW.argtypes=[ctypes.POINTER(w.MSG)];user.DispatchMessageW.restype=ctypes.c_ssize_t
        user.ShowWindow.argtypes=[w.HWND,ctypes.c_int];user.SetForegroundWindow.argtypes=[w.HWND]
        instance=kernel.GetModuleHandleW(None)
        name=f'WH3LoggerUpdate_{os.getpid()}_{id(self)}'
        label=bar=None
        def callback(hwnd,msg,wp,lp):
            if msg==0x8003:
                if label:user.SetWindowTextW(label,self.text)
                if bar:user.SendMessageW(bar,0x402,self.percent,0)
                return 0
            if msg==0x111 and (wp&0xffff)==2:
                webbrowser.open(RELEASE_NOTES+'/tag/v'+VERSION);return 0
            if msg==0x8004 or (msg==0x10 and self.about):
                user.DestroyWindow(hwnd);return 0
            if msg==0x10 or (msg==0x111 and (wp&0xffff)==1):
                if self.about:user.DestroyWindow(hwnd)
                elif self.cancellable:
                    self.cancelled.set();user.DestroyWindow(hwnd)
                return 0
            if msg==2:user.PostQuitMessage(0);return 0
            return user.DefWindowProcW(hwnd,msg,wp,lp)
        proc=Proc(callback);wc=WC();wc.proc=proc;wc.instance=instance;wc.background=6;wc.name=name
        if not user.RegisterClassW(ctypes.byref(wc)):raise ctypes.WinError(ctypes.get_last_error())
        try:
            self.hwnd=user.CreateWindowExW(0,name,self.title,0x00C80000,0x80000000,0x80000000,520,210,None,None,instance,None)
            if not self.hwnd:raise ctypes.WinError(ctypes.get_last_error())
            def child(kind,text,x,y,width,height,ident=0,extra=0):
                result=user.CreateWindowExW(0,kind,text,0x50000000|extra,x,y,width,height,self.hwnd,ident,instance,None)
                if not result:raise ctypes.WinError(ctypes.get_last_error())
                return result
            label=child('STATIC',f'WARHAMMER III Battle Logger\n\nInstalled version: {VERSION}' if self.about else self.text,20,20,470,65)
            if self.about:
                child('BUTTON','GitHub release notes',20,110,220,32,2)
                child('BUTTON','Close',370,110,110,32,1)
            else:
                bar=child('msctls_progress32','',20,90,460,22)
                user.SendMessageW(bar,0x406,0,100)
                if self.cancellable:child('BUTTON','Cancel',370,125,110,28,1)
            user.ShowWindow(self.hwnd,5);user.SetForegroundWindow(self.hwnd)
            self.ready.set()
            msg=w.MSG()
            while True:
                code=user.GetMessageW(ctypes.byref(msg),None,0,0)
                if code==0:break
                if code==-1:raise ctypes.WinError(ctypes.get_last_error())
                user.TranslateMessage(ctypes.byref(msg));user.DispatchMessageW(ctypes.byref(msg))
        finally:
            if self.hwnd:user.DestroyWindow(self.hwnd)
            self.hwnd=None
            user.UnregisterClassW(name,instance)
