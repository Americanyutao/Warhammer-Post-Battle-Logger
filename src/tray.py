"""Windows notification icon with a private message loop; no Tk calls off-thread."""
import ctypes
from ctypes import wintypes as w
import os
import queue
import threading
from icons import load_tray_icon


class TrayIcon:
    def __init__(self, icon_handle=None):
        self.icon_handle = icon_handle
        self.actions = queue.Queue()
        self.ready = threading.Event()
        self.stopping = threading.Event()
        self.available = False
        self.error = None
        self.hwnd = None
        self.tooltip = 'WARHAMMER III Battle Logger'
        self.thread = threading.Thread(target=self.run, name='battle-logger-tray', daemon=True)
    def start(self):
        if os.name == 'nt': self.thread.start()
    def set_tooltip(self, text):
        self.tooltip = text[:127]
        if self.hwnd:self.user.PostMessageW(self.hwnd,0x8002,0,0)
    def stop(self):
        self.stopping.set()
        if self.hwnd:
            self.user.PostMessageW(self.hwnd, 0x10, 0, 0)
        if self.thread.is_alive(): self.thread.join(timeout=2)
    def run(self):
        try: self.message_loop()
        except Exception as error:
            self.error = str(error); self.available = False
        finally: self.ready.set()
    def message_loop(self):
        user = self.user = ctypes.WinDLL('user32', use_last_error=True)
        shell = ctypes.WinDLL('shell32', use_last_error=True)
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        Proc = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, w.HWND, w.UINT, w.WPARAM, w.LPARAM)
        class WNDCLASS(ctypes.Structure):
            _fields_ = [('style',w.UINT),('lpfnWndProc',Proc),('cbClsExtra',ctypes.c_int),
                ('cbWndExtra',ctypes.c_int),('hInstance',w.HINSTANCE),('hIcon',w.HICON),
                ('hCursor',w.HANDLE),('hbrBackground',w.HBRUSH),('lpszMenuName',w.LPCWSTR),('lpszClassName',w.LPCWSTR)]
        class GUID(ctypes.Structure):
            _fields_ = [('Data1',w.DWORD),('Data2',w.WORD),('Data3',w.WORD),('Data4',w.BYTE*8)]
        class NID(ctypes.Structure):
            _fields_ = [('cbSize',w.DWORD),('hWnd',w.HWND),('uID',w.UINT),('uFlags',w.UINT),
                ('uCallbackMessage',w.UINT),('hIcon',w.HICON),('szTip',w.WCHAR*128),('dwState',w.DWORD),
                ('dwStateMask',w.DWORD),('szInfo',w.WCHAR*256),('uVersion',w.UINT),
                ('szInfoTitle',w.WCHAR*64),('dwInfoFlags',w.DWORD),('guidItem',GUID),('hBalloonIcon',w.HICON)]
        kernel.GetModuleHandleW.argtypes=[w.LPCWSTR];kernel.GetModuleHandleW.restype=w.HMODULE
        user.RegisterClassW.argtypes=[ctypes.POINTER(WNDCLASS)];user.RegisterClassW.restype=w.ATOM
        user.UnregisterClassW.argtypes=[w.LPCWSTR,w.HINSTANCE];user.UnregisterClassW.restype=w.BOOL
        user.CreateWindowExW.argtypes=[w.DWORD,w.LPCWSTR,w.LPCWSTR,w.DWORD,ctypes.c_int,ctypes.c_int,
            ctypes.c_int,ctypes.c_int,w.HWND,w.HMENU,w.HINSTANCE,ctypes.c_void_p];user.CreateWindowExW.restype=w.HWND
        user.DefWindowProcW.argtypes=[w.HWND,w.UINT,w.WPARAM,w.LPARAM];user.DefWindowProcW.restype=ctypes.c_ssize_t
        user.DestroyWindow.argtypes=[w.HWND];user.DestroyWindow.restype=w.BOOL
        user.PostMessageW.argtypes=[w.HWND,w.UINT,w.WPARAM,w.LPARAM];user.PostMessageW.restype=w.BOOL
        user.GetMessageW.argtypes=[ctypes.POINTER(w.MSG),w.HWND,w.UINT,w.UINT];user.GetMessageW.restype=ctypes.c_int
        user.TranslateMessage.argtypes=[ctypes.POINTER(w.MSG)];user.DispatchMessageW.argtypes=[ctypes.POINTER(w.MSG)]
        user.DispatchMessageW.restype=ctypes.c_ssize_t
        user.RegisterWindowMessageW.argtypes=[w.LPCWSTR];user.RegisterWindowMessageW.restype=w.UINT
        user.CreatePopupMenu.restype=w.HMENU
        user.AppendMenuW.argtypes=[w.HMENU,w.UINT,ctypes.c_size_t,w.LPCWSTR];user.AppendMenuW.restype=w.BOOL
        user.SetForegroundWindow.argtypes=[w.HWND];user.SetForegroundWindow.restype=w.BOOL
        user.TrackPopupMenu.argtypes=[w.HMENU,w.UINT,ctypes.c_int,ctypes.c_int,ctypes.c_int,w.HWND,ctypes.c_void_p]
        user.TrackPopupMenu.restype=w.UINT
        user.DestroyMenu.argtypes=[w.HMENU];user.GetCursorPos.argtypes=[ctypes.POINTER(w.POINT)]
        user.CreateIcon.argtypes=[w.HINSTANCE,ctypes.c_int,ctypes.c_int,w.BYTE,w.BYTE,
            ctypes.POINTER(w.BYTE),ctypes.POINTER(w.BYTE)];user.CreateIcon.restype=w.HICON
        user.DestroyIcon.argtypes=[w.HICON];user.DestroyIcon.restype=w.BOOL
        shell.Shell_NotifyIconW.argtypes=[w.DWORD,ctypes.POINTER(NID)];shell.Shell_NotifyIconW.restype=w.BOOL
        instance = kernel.GetModuleHandleW(None)
        icon=self.icon_handle or load_tray_icon()
        if not icon: raise ctypes.WinError(ctypes.get_last_error())
        callback_message=0x8001
        taskbar=user.RegisterWindowMessageW('TaskbarCreated')
        nid=NID();nid.cbSize=ctypes.sizeof(nid);nid.uID=1;nid.uFlags=7
        nid.uCallbackMessage=callback_message;nid.hIcon=icon;nid.szTip=self.tooltip
        def menu(hwnd):
            popup=user.CreatePopupMenu()
            try:
                for ident,label in [(1,'Open reports'),(2,'Exit')]:
                    user.AppendMenuW(popup,0,ident,label)
                point=w.POINT();user.GetCursorPos(ctypes.byref(point));user.SetForegroundWindow(hwnd)
                choice=user.TrackPopupMenu(popup,0x180,point.x,point.y,0,hwnd,None)
                if choice: self.actions.put({1:'open_reports',2:'exit'}[choice])
                user.PostMessageW(hwnd,0,0,0)
            finally: user.DestroyMenu(popup)
        def callback(hwnd,msg,wp,lp):
            if msg==0x111 and (wp & 0xffff) in (1,2):
                self.actions.put({1:'open_reports',2:'exit'}[wp & 0xffff]);return 0
            if msg==callback_message:
                if lp in (0x205,0x7b): menu(hwnd)
                return 0
            if msg==0x8002:
                nid.szTip=self.tooltip
                shell.Shell_NotifyIconW(1,ctypes.byref(nid));return 0
            if msg==taskbar:
                self.available=bool(shell.Shell_NotifyIconW(0,ctypes.byref(nid)))
                return 0
            if msg==0x10:
                user.DestroyWindow(hwnd);return 0
            if msg==2:
                user.PostQuitMessage(0);return 0
            return user.DefWindowProcW(hwnd,msg,wp,lp)
        # Hold the callback strongly for the entire native window lifetime.
        proc=Proc(callback);name=f'BattleLoggerTray_{os.getpid()}_{id(self)}'
        wc=WNDCLASS();wc.lpfnWndProc=proc;wc.hInstance=instance;wc.hIcon=icon;wc.lpszClassName=name
        registered=False
        try:
            if not user.RegisterClassW(ctypes.byref(wc)): raise ctypes.WinError(ctypes.get_last_error())
            registered=True
            self.hwnd=user.CreateWindowExW(0,name,'Battle Logger tray',0,0,0,0,0,None,None,instance,None)
            if not self.hwnd: raise ctypes.WinError(ctypes.get_last_error())
            nid.hWnd=self.hwnd
            self.available=bool(shell.Shell_NotifyIconW(0,ctypes.byref(nid)))
            if not self.available: raise RuntimeError(f'Windows could not create the tray icon (error {ctypes.get_last_error()}).')
            self.ready.set()
            if self.stopping.is_set(): user.PostMessageW(self.hwnd,0x10,0,0)
            message=w.MSG()
            while True:
                result=user.GetMessageW(ctypes.byref(message),None,0,0)
                if result==0: break
                if result==-1: raise ctypes.WinError(ctypes.get_last_error())
                user.TranslateMessage(ctypes.byref(message));user.DispatchMessageW(ctypes.byref(message))
        finally:
            shell.Shell_NotifyIconW(2,ctypes.byref(nid))
            if self.hwnd: user.DestroyWindow(self.hwnd)
            self.hwnd=None;self.available=False
            user.DestroyIcon(icon)
            if registered: user.UnregisterClassW(name,instance)
