"""Native report menu. Closing the window leaves the tray collector running."""
import ctypes
from ctypes import wintypes as w
import os
import queue
import threading
from icons import load_tray_icon
from version import VERSION
from release_notes import LOADING_NOTES,RELEASES_URL
from battle_names import validate_name

WELCOME='You can close the main menu with X. Battle Logger will continue recording in the Windows notification tray.\n\nDouble-click the tray icon to open the main menu again. To stop the logger, choose Exit from the menu or tray.'
LATE_START='The logger started after deployment. Values may be incorrect or incomplete when recording begins in the middle of a battle.\n\nContinue logging this battle?\n\nYes: continue recording.\nNo: discard this battle and wait for the next one.'
def rgb(value):
    return int(value[1:3],16)|int(value[3:5],16)<<8|int(value[5:7],16)<<16

BG=rgb('#0D111A');CARD=rgb('#151D28');BORDER=rgb('#253246')
TEXT=rgb('#EDF2F7');MUTED=rgb('#9FA8B6');GOLD=rgb('#E5A93C')
SELECTED=rgb('#1E2C40');ROW_ALT=rgb('#111622');HOVER=rgb('#1A2332')
PRIMARY=rgb('#C89B3C');PRIMARY_DOWN=rgb('#AD812C')
BUTTON=rgb('#202B3C');BUTTON_BORDER=rgb('#384A66')
MODAL=rgb('#111925');INNER=rgb('#18202C');MODAL_BORDER=rgb('#3A4B62')
DANGER=rgb('#E8A0A8');DANGER_BG=rgb('#3B202A');DANGER_BORDER=rgb('#6A3A45')
WHITE=0xffffff;BLACK=0


class MainMenu:
    def __init__(self, library, actions, kind='menu', owner=None, answer=None, text=None, title=None,show_welcome=True,notes=None):
        self.library=library;self.actions=actions
        self.kind=kind;self.owner=owner;self.answer=answer
        self.welcome=self.prompt=self.update_prompt=self.rename_prompt=None
        self.show_welcome=show_welcome;self.notes=notes or LOADING_NOTES;self.pending_update=None
        self.answered=False
        self.dialog_text=text;self.dialog_title=title
        self.pending_request=None
        self.ready=threading.Event();self.hwnd=None;self.error=None
        self.closed=threading.Event();self.closing=False;self.dimmer=None
        self.hover_row=-1
        self.status='Waiting for WARHAMMER III';self.questions=queue.Queue()
        self.thread=threading.Thread(target=self.run,name='battle-logger-menu',daemon=True)

    def start(self):
        self.thread.start()
        if not self.ready.wait(5) or self.error:raise RuntimeError(self.error or 'Could not open the main menu.')
        return self

    def post(self, message):
        if self.hwnd:self.user.PostMessageW(self.hwnd,message,0,0)

    def focus(self):self.post(0x8005)
    def update(self,status):self.status=status;self.post(0x8003)
    def ask_late_start(self,request,answer):
        self.pending_request=request
        self.questions.put((request,answer));self.post(0x8006)
    def cancel_late_start(self):
        self.pending_request=None
        if self.prompt:self.prompt.close()
    def set_release_notes(self,text):
        self.notes=text
        popup=self.welcome if self.kind=='menu' else self
        if popup:popup.notes=text;popup.post(0x8009)
    def offer_update(self,tag,answer):
        self.pending_update=(tag,answer);self.post(0x8006)
    def cancel_update_offer(self):
        self.pending_update=None
        if self.update_prompt:self.update_prompt.close()
    def close(self):
        self.closing=True
        if self.welcome:self.welcome.close()
        if self.prompt:self.prompt.close()
        if self.update_prompt:self.update_prompt.close()
        if self.rename_prompt:self.rename_prompt.close()
        self.post(0x8004)
        if self.thread.is_alive():self.thread.join(timeout=3)

    def run(self):
        try:self.loop()
        except Exception as error:self.error=str(error)
        finally:
            self.ready.set();self.closed.set()
            if self.owner and hasattr(self,'user'):self.user.PostMessageW(self.owner,0x8008,0,0)

    def loop(self):
        user=self.user=ctypes.WinDLL('user32',use_last_error=True)
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        gdi=ctypes.WinDLL('gdi32',use_last_error=True)
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
        user.DestroyWindow.argtypes=[w.HWND];user.DestroyIcon.argtypes=[w.HICON]
        user.ShowWindow.argtypes=[w.HWND,ctypes.c_int];user.SetForegroundWindow.argtypes=[w.HWND]
        user.SetWindowTextW.argtypes=[w.HWND,w.LPCWSTR]
        user.SetFocus.argtypes=[w.HWND]
        user.SetTimer.argtypes=[w.HWND,ctypes.c_size_t,w.UINT,ctypes.c_void_p]
        user.GetMessageW.argtypes=[ctypes.POINTER(w.MSG),w.HWND,w.UINT,w.UINT]
        user.TranslateMessage.argtypes=[ctypes.POINTER(w.MSG)];user.DispatchMessageW.argtypes=[ctypes.POINTER(w.MSG)];user.DispatchMessageW.restype=ctypes.c_ssize_t
        user.IsDialogMessageW.argtypes=[w.HWND,ctypes.POINTER(w.MSG)];user.IsDialogMessageW.restype=w.BOOL
        user.AdjustWindowRect.argtypes=[ctypes.POINTER(w.RECT),w.DWORD,w.BOOL]
        gdi.GetStockObject.argtypes=[ctypes.c_int];gdi.GetStockObject.restype=w.HANDLE
        gdi.SetTextColor.argtypes=[w.HDC,w.DWORD];gdi.SetBkColor.argtypes=[w.HDC,w.DWORD]
        gdi.CreateSolidBrush.argtypes=[w.DWORD];gdi.CreateSolidBrush.restype=w.HBRUSH
        gdi.CreateFontW.argtypes=[ctypes.c_int]*5+[w.DWORD]*8+[w.LPCWSTR];gdi.CreateFontW.restype=w.HANDLE
        gdi.SelectObject.argtypes=[w.HDC,w.HANDLE];gdi.SelectObject.restype=w.HANDLE
        gdi.DeleteObject.argtypes=[w.HANDLE]
        user.FillRect.argtypes=[w.HDC,ctypes.POINTER(w.RECT),w.HBRUSH]
        user.DrawTextW.argtypes=[w.HDC,w.LPCWSTR,ctypes.c_int,ctypes.POINTER(w.RECT),w.UINT]
        user.GetWindowTextW.argtypes=[w.HWND,w.LPWSTR,ctypes.c_int]
        user.FrameRect.argtypes=[w.HDC,ctypes.POINTER(w.RECT),w.HBRUSH]
        user.InvalidateRect.argtypes=[w.HWND,ctypes.c_void_p,w.BOOL]
        user.GetClientRect.argtypes=[w.HWND,ctypes.POINTER(w.RECT)]
        user.GetWindowRect.argtypes=[w.HWND,ctypes.POINTER(w.RECT)]
        user.EnableWindow.argtypes=[w.HWND,w.BOOL]
        user.IsWindowEnabled.argtypes=[w.HWND];user.IsWindowEnabled.restype=w.BOOL
        user.SetLayeredWindowAttributes.argtypes=[w.HWND,w.DWORD,w.BYTE,w.DWORD]
        class Paint(ctypes.Structure):
            _fields_=[('dc',w.HDC),('erase',w.BOOL),('rect',w.RECT),('restore',w.BOOL),('update',w.BOOL),('reserved',w.BYTE*32)]
        user.BeginPaint.argtypes=[w.HWND,ctypes.POINTER(Paint)];user.BeginPaint.restype=w.HDC
        user.EndPaint.argtypes=[w.HWND,ctypes.POINTER(Paint)]
        class TrackMouse(ctypes.Structure):
            _fields_=[('size',w.DWORD),('flags',w.DWORD),('hwnd',w.HWND),('hover',w.DWORD)]
        user.TrackMouseEvent.argtypes=[ctypes.POINTER(TrackMouse)]
        common=ctypes.WinDLL('comctl32',use_last_error=True)
        SubProc=ctypes.WINFUNCTYPE(ctypes.c_ssize_t,w.HWND,w.UINT,w.WPARAM,w.LPARAM,ctypes.c_size_t,ctypes.c_size_t)
        common.SetWindowSubclass.argtypes=[w.HWND,SubProc,ctypes.c_size_t,ctypes.c_size_t];common.SetWindowSubclass.restype=w.BOOL
        common.DefSubclassProc.argtypes=[w.HWND,w.UINT,w.WPARAM,w.LPARAM];common.DefSubclassProc.restype=ctypes.c_ssize_t
        class DrawItem(ctypes.Structure):
            _fields_=[('kind',w.UINT),('ident',w.UINT),('item',w.UINT),('action',w.UINT),('state',w.UINT),('hwnd',w.HWND),('dc',w.HDC),('rect',w.RECT),('data',ctypes.c_size_t)]
        class MeasureItem(ctypes.Structure):
            _fields_=[('kind',w.UINT),('ident',w.UINT),('item',w.UINT),('width',w.UINT),('height',w.UINT),('data',ctypes.c_size_t)]
        brushes={color:gdi.CreateSolidBrush(color) for color in
            (BG,CARD,BORDER,TEXT,MUTED,GOLD,SELECTED,ROW_ALT,HOVER,PRIMARY,PRIMARY_DOWN,
             BUTTON,BUTTON_BORDER,MODAL,INNER,MODAL_BORDER,DANGER,DANGER_BG,DANGER_BORDER,WHITE,BLACK)}
        fonts={size:gdi.CreateFontW(-14 if size==15 else -size,0,0,0,600 if size in (31,13,15) else 400,0,0,0,1,0,0,5,0,'Segoe UI') for size in (12,13,14,15,31)}
        static_colors={}
        static_backgrounds={}
        instance=kernel.GetModuleHandleW(None);icon=load_tray_icon()
        name=f'WH3LoggerMenu_{os.getpid()}_{id(self)}'
        rows=[];signature=None;listing=status=recovery=notes_control=rename_control=rename_error=None
        hovered_buttons=set()
        background=BG if self.kind=='menu' else MODAL
        owner_disabled=False;dimmer_registered=False
        def track(hwnd):
            tracking=TrackMouse(ctypes.sizeof(TrackMouse),2,hwnd,0)
            user.TrackMouseEvent(ctypes.byref(tracking))
        def hover_callback(hwnd,msg,wp,lp,ident,data):
            if msg==0x200:
                track(hwnd)
                if data==20:
                    hit=user.SendMessageW(hwnd,0x1a9,0,lp)
                    index=hit&0xffff if not (hit>>16)&0xffff else -1
                    if index>=len(rows):index=-1
                    if index!=self.hover_row:
                        self.hover_row=index;user.InvalidateRect(hwnd,None,False)
                elif hwnd not in hovered_buttons:
                    hovered_buttons.add(hwnd);user.InvalidateRect(hwnd,None,False)
            elif msg==0x2a3:
                if data==20:self.hover_row=-1
                else:hovered_buttons.discard(hwnd)
                user.InvalidateRect(hwnd,None,False)
            elif msg in (7,8):user.InvalidateRect(hwnd,None,False)
            elif msg==0xf4 and data!=20:
                # Dialog keyboard navigation must retain our custom button paint.
                wp=(wp&~15)|11
            return common.DefSubclassProc(hwnd,msg,wp,lp)
        hover_proc=SubProc(hover_callback)
        displayed_text={}
        def set_text(handle,text):
            if displayed_text.get(handle)!=text:
                user.SetWindowTextW(handle,text);displayed_text[handle]=text
        def refresh():
            nonlocal rows,signature
            entries=self.library.entries()
            current=tuple((e['name'],e['recording']) for e in entries)
            if current!=signature:
                selected=user.SendMessageW(listing,0x188,0,0)
                selected_name=rows[selected]['name'] if 0<=selected<len(rows) else None
                user.SendMessageW(listing,0x184,0,0)
                rows=entries;signature=current
                for index,row in enumerate(rows):
                    text=('Recording  ·  ' if row['recording'] else 'Battle  ·  ')+row['name']
                    buffer=ctypes.create_unicode_buffer(text)
                    user.SendMessageW(listing,0x180,0,ctypes.addressof(buffer))
                    if row['name']==selected_name:user.SendMessageW(listing,0x186,index,0)
                if rows and selected_name is None:user.SendMessageW(listing,0x186,0,0)
            set_text(status,self.status)
            set_text(recovery,self.library.status or ('No recordings yet. Battles will appear here after recording.' if not rows else 'Double-click a battle to open it in the app. Interrupted recordings recover when opened.'))
        def open_selected(action='open_capture'):
            selected=user.SendMessageW(listing,0x188,0,0)
            if not 0<=selected<len(rows):return
            path=rows[selected]['log']
            if rows[selected]['recording']:
                self.library.status='This battle is still recording. Wait until the recording finishes.'
                refresh()
            elif path and path.is_file():self.actions.put((action,str(path)))
            else:
                self.library.status='This recording is no longer available.'
                refresh()
        def answer_once(accepted):
            if self.answer and not self.answered:
                self.answered=True;self.answer(accepted)
        def callback(hwnd,msg,wp,lp):
            if msg==0x8005:
                if self.kind=='menu':
                    refresh()
                    for popup in (self.prompt,self.update_prompt,self.rename_prompt,self.welcome):
                        if popup and not popup.closed.is_set():popup.focus();return 0
                user.ShowWindow(hwnd,9);user.SetForegroundWindow(hwnd);return 0
            if msg in (0x113,0x8003) and self.kind=='menu':refresh();return 0
            if msg==0x8007:
                if self.closing or self.welcome or not self.show_welcome:return 0
                self.welcome=MainMenu(self.library,self.actions,kind='welcome',owner=hwnd,notes=self.notes)
                self.welcome.thread.start();return 0
            if msg==0x8009 and notes_control:
                user.SetWindowTextW(notes_control,self.notes.replace('\n','\r\n'));return 0
            if msg==0x8008:
                if not self.closing and (not self.questions.empty() or self.pending_update):self.post(0x8006)
                return 0
            if msg==0x8006:
                if self.closing:return 0
                if self.welcome and not self.welcome.closed.is_set():return 0
                if self.update_prompt and not self.update_prompt.closed.is_set():return 0
                if self.rename_prompt and not self.rename_prompt.closed.is_set():return 0
                if not self.questions.empty():
                    if self.prompt and not self.prompt.closed.is_set():
                        self.prompt.post(0x8004);return 0
                    while True:
                        try:request,answer=self.questions.get_nowait()
                        except queue.Empty:break
                        if request==self.pending_request:
                            self.prompt=MainMenu(self.library,self.actions,kind='late',owner=hwnd,
                                answer=lambda accepted:answer(request,accepted))
                            self.prompt.thread.start();return 0
                if self.prompt and not self.prompt.closed.is_set():return 0
                if self.pending_update:
                    tag,answer=self.pending_update;self.pending_update=None
                    self.update_prompt=MainMenu(self.library,self.actions,kind='question',owner=hwnd,
                        title=f'New version {tag} available',
                        text='Download now?\n\nThe logger will keep recording during the download. You can choose when to install and restart.\n\nYes: download the update.\nNo: continue with this version.',answer=answer)
                    self.update_prompt.thread.start()
                return 0
            if msg==0x111:
                ident=wp&0xffff;notification=(wp>>16)&0xffff
                if self.kind!='menu':
                    if self.kind=='rename' and ident in (9,10,11) and notification==0:
                        if ident==9:
                            buffer=ctypes.create_unicode_buffer(512);user.GetWindowTextW(rename_control,buffer,len(buffer))
                            try:name=validate_name(buffer.value)
                            except ValueError as error:user.SetWindowTextW(rename_error,str(error));return 0
                            answer_once(name)
                        else:answer_once(None)
                        user.DestroyWindow(hwnd);return 0
                    if ident==12 and notification==0:os.startfile(RELEASES_URL+'/tag/v'+VERSION);return 0
                    if ident in (9,10,11) and notification==0:
                        answer_once(ident==9);user.DestroyWindow(hwnd)
                    return 0
                if ident==20 and notification==2:open_selected()
                elif ident==8:
                    selected=user.SendMessageW(listing,0x188,0,0)
                    if 0<=selected<len(rows):
                        row=rows[selected];path=row['log']
                        if row['recording']:self.library.status='Wait until this battle finishes recording.';refresh()
                        elif path:
                            self.rename_prompt=MainMenu(self.library,self.actions,kind='rename',owner=hwnd,title='Rename Battle',text=path.stem,
                                answer=lambda name:self.actions.put(('rename_capture',(str(path),name))) if name else None)
                            self.rename_prompt.thread.start()
                elif ident==1:open_selected()
                elif ident==2:open_selected('export_capture')
                elif ident in (3,4,5,6,7):
                    self.actions.put({3:'settings',4:'check_updates',5:'restart',6:'exit',7:'open_folder'}[ident])
                return 0
            if msg==0x10:
                if self.kind=='menu':user.ShowWindow(hwnd,0)
                else:answer_once(None if self.kind=='rename' else False);user.DestroyWindow(hwnd)
                return 0
            if msg==0x8004:answer_once(None if self.kind=='rename' else False);user.DestroyWindow(hwnd);return 0
            if msg==2:user.PostQuitMessage(0);return 0
            if msg in (0x133,0x134,0x138):
                fill=CARD if lp==listing else static_backgrounds.get(lp,background)
                gdi.SetTextColor(wp,static_colors.get(lp,TEXT));gdi.SetBkColor(wp,fill)
                return brushes[fill]
            if msg==0xf:
                painting=Paint();dc=user.BeginPaint(hwnd,ctypes.byref(painting))
                try:
                    user.FillRect(dc,ctypes.byref(painting.rect),brushes[background])
                    rect=w.RECT(22,166,818,494) if self.kind=='menu' else w.RECT()
                    if self.kind!='menu':user.GetClientRect(hwnd,ctypes.byref(rect))
                    user.FrameRect(dc,ctypes.byref(rect),brushes[BORDER if self.kind=='menu' else MODAL_BORDER])
                finally:user.EndPaint(hwnd,ctypes.byref(painting))
                return 0
            if msg==0x14:
                rect=w.RECT();user.GetClientRect(hwnd,ctypes.byref(rect))
                user.FillRect(wp,ctypes.byref(rect),brushes[background]);return 1
            if msg==0x2c:
                ctypes.cast(lp,ctypes.POINTER(MeasureItem)).contents.height=42;return 1
            if msg==0x2b:
                draw=ctypes.cast(lp,ctypes.POINTER(DrawItem)).contents
                selected=bool(draw.state&1);focus=bool(draw.state&16)
                rect=w.RECT(draw.rect.left,draw.rect.top,draw.rect.right,draw.rect.bottom)
                if draw.ident==100:
                    user.FillRect(draw.dc,ctypes.byref(rect),brushes[INNER])
                    user.FrameRect(draw.dc,ctypes.byref(rect),brushes[BORDER]);return 1
                if draw.ident==20:
                    fill=SELECTED if selected else HOVER if draw.item==self.hover_row else ROW_ALT if draw.item%2 else CARD
                    color=WHITE if selected else MUTED
                    user.FillRect(draw.dc,ctypes.byref(rect),brushes[fill])
                    divider=w.RECT(rect.left,rect.bottom-1,rect.right,rect.bottom)
                    user.FillRect(draw.dc,ctypes.byref(divider),brushes[BORDER])
                    if selected:
                        accent=w.RECT(rect.left,rect.top,rect.left+3,rect.bottom-1)
                        user.FillRect(draw.dc,ctypes.byref(accent),brushes[GOLD])
                    if draw.item>=len(rows):return 1
                    row=rows[draw.item];text=('Recording  ·  ' if row['recording'] else 'Battle  ·  ')+row['name']
                    rect.left+=17;rect.right-=12;flags=0x24|0x8000;size=14
                else:
                    hover=draw.hwnd in hovered_buttons
                    primary=draw.ident in ((1,) if self.kind=='menu' else (9,11))
                    danger=self.kind=='menu' and draw.ident==6
                    if primary:
                        fill=PRIMARY_DOWN if selected else GOLD if hover else PRIMARY
                        color=BG;border=GOLD;size=15
                    elif danger:
                        fill=DANGER_BG if hover or selected else background
                        color=WHITE if hover else DANGER;border=DANGER_BORDER;size=14
                    else:
                        utility=self.kind=='menu' and draw.ident in (3,4,5,7)
                        fill=HOVER if selected else BUTTON if hover or not utility else background
                        color=TEXT;border=BUTTON_BORDER;size=14
                    if draw.state&4:fill=BUTTON;color=MUTED
                    user.FillRect(draw.dc,ctypes.byref(rect),brushes[fill])
                    user.FrameRect(draw.dc,ctypes.byref(rect),brushes[GOLD if focus else border])
                    buffer=ctypes.create_unicode_buffer(256);user.GetWindowTextW(draw.hwnd,buffer,256)
                    text=buffer.value;flags=0x25
                gdi.SetBkColor(draw.dc,fill);gdi.SetTextColor(draw.dc,color)
                old=gdi.SelectObject(draw.dc,fonts[size])
                user.DrawTextW(draw.dc,text,-1,ctypes.byref(rect),flags)
                gdi.SelectObject(draw.dc,old);return 1
            return user.DefWindowProcW(hwnd,msg,wp,lp)
        proc=Proc(callback);wc=WC();wc.proc=proc;wc.instance=instance;wc.icon=icon
        wc.background=brushes[background];wc.name=name
        if self.kind!='menu':wc.style=0x20000
        if not user.RegisterClassW(ctypes.byref(wc)):raise ctypes.WinError(ctypes.get_last_error())
        try:
            width,height=(840,650) if self.kind=='menu' else (660,580) if self.kind=='welcome' else (600,350) if self.kind=='late' else (620,420)
            style=0x02ca0000;rect=w.RECT(0,0,width,height)
            user.AdjustWindowRect(ctypes.byref(rect),style,False)
            title=self.dialog_title or ('WARHAMMER III Battle Logger' if self.kind=='menu' else f"What's new in v{VERSION}" if self.kind=='welcome' else 'Battle already in progress')
            x=y=0x80000000;owner=self.owner
            if self.owner:
                bounds=w.RECT()
                if not user.GetWindowRect(self.owner,ctypes.byref(bounds)):raise ctypes.WinError(ctypes.get_last_error())
                dimmer_proc=Proc(lambda hwnd,msg,wp,lp:user.DefWindowProcW(hwnd,msg,wp,lp))
                dimmer_wc=WC();dimmer_wc.proc=dimmer_proc;dimmer_wc.instance=instance
                dimmer_wc.background=brushes[BLACK];dimmer_wc.name=name+'_Dimmer'
                if not user.RegisterClassW(ctypes.byref(dimmer_wc)):raise ctypes.WinError(ctypes.get_last_error())
                dimmer_registered=True
                self.dimmer=user.CreateWindowExW(0x08080080,dimmer_wc.name,'Battle Logger background dimmer',
                    0x80000000,bounds.left,bounds.top,bounds.right-bounds.left,bounds.bottom-bounds.top,
                    self.owner,None,instance,None)
                if not self.dimmer:raise ctypes.WinError(ctypes.get_last_error())
                if not user.SetLayeredWindowAttributes(self.dimmer,0,166,2):raise ctypes.WinError(ctypes.get_last_error())
                owner_disabled=bool(user.IsWindowEnabled(self.owner))
                if owner_disabled:user.EnableWindow(self.owner,False)
                user.ShowWindow(self.dimmer,4)
                owner=self.dimmer
                x=bounds.left+((bounds.right-bounds.left)-(rect.right-rect.left))//2
                y=bounds.top+((bounds.bottom-bounds.top)-(rect.bottom-rect.top))//2
            self.hwnd=user.CreateWindowExW(0x02000000 if self.kind=='menu' else 0,name,title,style,x,y,
                rect.right-rect.left,rect.bottom-rect.top,owner,None,instance,None)
            if not self.hwnd:raise ctypes.WinError(ctypes.get_last_error())
            def child(kind,text,x,y,width,height,ident=0,extra=0,size=14,color=TEXT,background=background):
                if kind=='BUTTON':extra|=0xb
                if kind=='STATIC':extra|=0x80
                handle=user.CreateWindowExW(0,kind,text,0x50000000|extra,x,y,width,height,self.hwnd,ident,instance,None)
                if not handle:raise ctypes.WinError(ctypes.get_last_error())
                user.SendMessageW(handle,0x30,fonts[size],1)
                static_colors[handle]=color
                static_backgrounds[handle]=background
                if kind in ('BUTTON','LISTBOX'):
                    if not common.SetWindowSubclass(handle,hover_proc,1,20 if kind=='LISTBOX' else ident):raise ctypes.WinError(ctypes.get_last_error())
                return handle
            child('STATIC','WARHAMMER III Battle Logger',22,18,width-44,20,size=13,color=GOLD)
            if self.kind=='menu':
                child('STATIC','Battle reports',22,44,450,42,size=31)
                status=child('STATIC',self.status,488,58,330,24,extra=2,size=12,color=MUTED)
                child('STATIC','Close this window to keep logging in the tray.',22,94,796,24,color=MUTED)
                child('STATIC','RECORDED BATTLES',22,136,796,22,size=12,color=MUTED)
                listing=child('LISTBOX','',23,167,794,326,20,0x00210151)
                self.listing=listing
                recovery=child('STATIC','',22,506,796,42,size=12,color=MUTED)
                for ident,text,x,bw in [(1,'Open report',22,140),(8,'Rename Battle',172,150),(2,'Export HTML',332,150),(7,'Open folder',492,130)]:
                    child('BUTTON',text,x,558,bw,34,ident,0x10000)
                for ident,text,x,bw in [(3,'Settings',22,112),(4,'Check for updates',144,170),(5,'Restart app',558,130),(6,'Exit logger',698,120)]:
                    child('BUTTON',text,x,606,bw,30,ident,0x10000)
                refresh();user.SetTimer(self.hwnd,1,2000,None)
            else:
                child('STATIC',self.dialog_title or (f"What's new in v{VERSION}" if self.kind=='welcome' else 'Battle already in progress'),22,46,width-44,42,size=31)
                if self.kind=='rename':
                    child('STATIC','Choose a name for this battle. Its recording and HTML export will use the same name.',22,104,width-44,48)
                    rename_control=child('EDIT',self.dialog_text or '',22,166,width-44,32,102,extra=0x10080,background=INNER)
                    user.SendMessageW(rename_control,0xc5,160,0)
                    rename_error=child('STATIC','',22,218,width-44,90,color=DANGER)
                elif self.kind=='welcome':
                    child('STATIC','',22,102,width-44,338,100,extra=0xd,background=INNER)
                    child('STATIC','FROM GITHUB RELEASE NOTES',38,116,width-76,20,size=13,color=GOLD,background=INNER)
                    notes_control=child('EDIT',self.notes.replace('\n','\r\n'),38,146,width-76,278,101,
                        extra=0x200844,color=TEXT,background=INNER)
                    child('STATIC','Close the main menu to keep logging in the tray.\nDouble-click the tray icon to reopen it.',22,458,width-44,54,color=TEXT)
                    child('BUTTON','Full release notes',22,height-54,190,32,12,0x10000)
                else:
                    child('STATIC',self.dialog_text or LATE_START,22,104,width-44,height-170,color=TEXT)
                if self.kind in ('welcome','notice'):child('BUTTON','Got it' if self.kind=='welcome' else 'OK',width-154,height-54,132,32,11,0x10000)
                else:
                    child('BUTTON','Save name' if self.kind=='rename' else 'Yes, continue' if self.kind=='late' else 'Yes',width-312,height-54,140,32,9,0x10000)
                    child('BUTTON','Cancel' if self.kind=='rename' else 'No, discard' if self.kind=='late' else 'No',width-162,height-54,140,32,10,0x10000)
            try:
                dwm=ctypes.WinDLL('dwmapi');dwm.DwmSetWindowAttribute.argtypes=[w.HWND,w.DWORD,ctypes.c_void_p,w.DWORD]
                dark=ctypes.c_int(1);dwm.DwmSetWindowAttribute(self.hwnd,20,ctypes.byref(dark),4)
                for attribute,color in ((34,MODAL_BORDER if self.kind!='menu' else BORDER),(35,background),(36,TEXT)):
                    value=w.DWORD(color);dwm.DwmSetWindowAttribute(self.hwnd,attribute,ctypes.byref(value),4)
            except OSError:pass
            user.ShowWindow(self.hwnd,5);user.SetForegroundWindow(self.hwnd)
            if rename_control:
                user.SetFocus(rename_control);user.SendMessageW(rename_control,0xb1,0,-1)
            self.ready.set()
            # Startup only. Focusing or reopening this same window never welcomes again.
            if self.kind=='menu':self.post(0x8007)
            message=w.MSG()
            while True:
                result=user.GetMessageW(ctypes.byref(message),None,0,0)
                if result==0:break
                if result==-1:raise ctypes.WinError(ctypes.get_last_error())
                if user.IsDialogMessageW(self.hwnd,ctypes.byref(message)):continue
                user.TranslateMessage(ctypes.byref(message));user.DispatchMessageW(ctypes.byref(message))
        finally:
            if self.hwnd:user.DestroyWindow(self.hwnd)
            self.hwnd=None
            if self.dimmer:user.DestroyWindow(self.dimmer);self.dimmer=None
            if owner_disabled:user.EnableWindow(self.owner,True)
            if dimmer_registered:user.UnregisterClassW(name+'_Dimmer',instance)
            user.UnregisterClassW(name,instance);user.DestroyIcon(icon)
            for handle in (*fonts.values(),*brushes.values()):gdi.DeleteObject(handle)


def silent_message(text, title='Battle Logger', question=False):
    answers=[]
    dialog=MainMenu(None,None,kind='question' if question else 'notice',
        text=text,title=title,answer=answers.append).start()
    dialog.thread.join()
    return bool(answers and answers[0])
