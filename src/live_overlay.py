"""Single solid taskbar window; Windows moves the whole meter directly."""
import ctypes
from ctypes import wintypes as w


class WindowsOverlay:
    def __init__(self):
        self.user=ctypes.WinDLL('user32',use_last_error=True)
        self.user.GetAncestor.argtypes=[w.HWND,w.UINT];self.user.GetAncestor.restype=w.HWND
        self.user.GetWindowLongPtrW.argtypes=[w.HWND,ctypes.c_int];self.user.GetWindowLongPtrW.restype=ctypes.c_ssize_t
        self.user.SetWindowLongPtrW.argtypes=[w.HWND,ctypes.c_int,ctypes.c_ssize_t];self.user.SetWindowLongPtrW.restype=ctypes.c_ssize_t
        self.user.GetWindowRect.argtypes=[w.HWND,ctypes.POINTER(w.RECT)]
        self.user.SetWindowPos.argtypes=[w.HWND,w.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,w.UINT]
        self.user.SendMessageW.argtypes=[w.HWND,w.UINT,w.WPARAM,w.LPARAM];self.user.SendMessageW.restype=ctypes.c_ssize_t
        self.user.ShowWindow.argtypes=[w.HWND,ctypes.c_int];self.user.SetForegroundWindow.argtypes=[w.HWND]
        self.user.SetCapture.argtypes=[w.HWND];self.user.SetCapture.restype=w.HWND
        self.user.GetAsyncKeyState.argtypes=[ctypes.c_int];self.user.GetAsyncKeyState.restype=ctypes.c_short
    def hwnd(self,widget):return self.user.GetAncestor(widget.winfo_id(),2)
    def style(self,widget):return self.user.GetWindowLongPtrW(self.hwnd(widget),-20)
    def taskbar_window(self,widget):
        hwnd=self.hwnd(widget)
        self.user.SetWindowLongPtrW(hwnd,-8,0)
        self.user.SetWindowLongPtrW(hwnd,-20,(self.style(widget)|0x40000)&~(0x80|0x80000|0x20))
        self.user.SetWindowPos(hwnd,None,0,0,0,0,0x37)
    def no_activate(self,widget,enabled=True):
        style=self.style(widget);self.user.SetWindowLongPtrW(self.hwnd(widget),-20,style|0x08000000 if enabled else style&~0x08000000)
    def bounds(self,widget):return self.window_bounds(self.hwnd(widget))
    def window_bounds(self,hwnd):
        rect=w.RECT();self.user.GetWindowRect(hwnd,ctypes.byref(rect));return rect.left,rect.top,rect.right-rect.left,rect.bottom-rect.top
    def move(self,widget,x,y):self.user.SetWindowPos(self.hwnd(widget),None,int(x),int(y),0,0,0x15)
    def capture(self,widget):self.user.SetCapture(widget.winfo_id())
    def release(self):self.user.ReleaseCapture()
    def mouse_down(self):return bool(self.user.GetAsyncKeyState(1)&0x8000)
    def activate(self,widget):self.user.ShowWindow(self.hwnd(widget),9);self.user.SetForegroundWindow(self.hwnd(widget))
    def fit_bounds(self,x,y,width,height):
        class MonitorInfo(ctypes.Structure):_fields_=[('size',w.DWORD),('monitor',w.RECT),('work',w.RECT),('flags',w.DWORD)]
        self.user.MonitorFromRect.argtypes=[ctypes.POINTER(w.RECT),w.DWORD];self.user.MonitorFromRect.restype=w.HANDLE
        self.user.GetMonitorInfoW.argtypes=[w.HANDLE,ctypes.POINTER(MonitorInfo)]
        rect=w.RECT(x,y,x+width,y+height);monitor=self.user.MonitorFromRect(ctypes.byref(rect),2);info=MonitorInfo();info.size=ctypes.sizeof(info)
        if monitor and self.user.GetMonitorInfoW(monitor,ctypes.byref(info)):
            area=info.work;width=min(width,area.right-area.left);height=min(height,area.bottom-area.top);x=max(area.left,min(x,area.right-width));y=max(area.top,min(y,area.bottom-height))
        return x,y,width,height
