"""Exercise the app's own native windows with temporary reports and no game."""
import ctypes
from ctypes import wintypes as w
import json
import os
from pathlib import Path
import queue
import sys
import tempfile
import time
from unittest.mock import patch
from unittest.mock import Mock

P=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(P/'src'))
from main_menu import MainMenu
from report_library import ReportLibrary
from tray import TrayIcon
from version import VERSION

user=ctypes.WinDLL('user32',use_last_error=True)
Proc=ctypes.WINFUNCTYPE(w.BOOL,w.HWND,w.LPARAM)
user.EnumWindows.argtypes=[Proc,w.LPARAM]
user.GetWindowThreadProcessId.argtypes=[w.HWND,ctypes.POINTER(w.DWORD)]
user.GetWindowTextW.argtypes=[w.HWND,w.LPWSTR,ctypes.c_int]
user.SendMessageW.argtypes=[w.HWND,w.UINT,w.WPARAM,w.LPARAM];user.SendMessageW.restype=ctypes.c_ssize_t
user.PostMessageW.argtypes=[w.HWND,w.UINT,w.WPARAM,w.LPARAM]
user.IsWindowVisible.argtypes=[w.HWND];user.IsWindowVisible.restype=w.BOOL
user.GetDlgItem.argtypes=[w.HWND,ctypes.c_int];user.GetDlgItem.restype=w.HWND
user.IsWindowEnabled.argtypes=[w.HWND];user.IsWindowEnabled.restype=w.BOOL
user.IsWindow.argtypes=[w.HWND];user.IsWindow.restype=w.BOOL
user.UpdateWindow.argtypes=[w.HWND]
user.GetLayeredWindowAttributes.argtypes=[w.HWND,ctypes.POINTER(w.DWORD),ctypes.POINTER(w.BYTE),ctypes.POINTER(w.DWORD)]

def dialog(title):
    found=[]
    @Proc
    def visit(hwnd,lp):
        pid=w.DWORD();user.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
        if pid.value==os.getpid():
            text=ctypes.create_unicode_buffer(256);user.GetWindowTextW(hwnd,text,256)
            if text.value==title:found.append(hwnd)
        return True
    user.EnumWindows(visit,0)
    return found[0] if found else None

def wait_for(predicate):
    deadline=time.monotonic()+5
    while time.monotonic()<deadline:
        value=predicate()
        if value:return value
        time.sleep(.02)
    raise AssertionError('Native window did not reach the expected state.')

def text_of(hwnd):
    text=ctypes.create_unicode_buffer(4096);user.GetWindowTextW(hwnd,text,len(text))
    return text.value

with tempfile.TemporaryDirectory(dir=P/'build') as d:
    folder=Path(d)/'captures';folder.mkdir()
    preview=folder/'battle-20261028-120000-test.wh3log';preview.write_bytes(b'placeholder')
    (folder/'battle-20261028-110000-missing.wh3log').write_bytes(b'placeholder')
    actions=queue.Queue();menu=MainMenu(ReportLibrary(d),actions,notes='Loading fixture notes…').start()
    try:
        welcome=wait_for(lambda:dialog(f"What's new in v{VERSION}"))
        button=wait_for(lambda:user.GetDlgItem(welcome,11) if user.IsWindowVisible(welcome) else None)
        time.sleep(.05)
        assert not user.IsWindowEnabled(menu.hwnd)
        dimmer=menu.welcome.dimmer
        assert dimmer and user.IsWindowVisible(dimmer)
        color=w.DWORD();alpha=w.BYTE();flags=w.DWORD()
        assert user.GetLayeredWindowAttributes(dimmer,ctypes.byref(color),ctypes.byref(alpha),ctypes.byref(flags))
        assert alpha.value==166 and flags.value&2
        notes=wait_for(lambda:user.GetDlgItem(welcome,101))
        assert text_of(notes)=='Loading fixture notes…'
        menu.set_release_notes('• Track unit stats throughout battle: explore how stats change compared with initial values.\n\n• Buff/debuff timelines: see detected effects and their descriptions.\n\n• Improved updater: clearer progress, counters and cancellation.\n\n• Improved report interface: synchronized timelines and customizable tooltips.\n\n• Report options: control embedded icons in standalone exports.')
        wait_for(lambda:'Track unit stats' in text_of(notes))
        update_answers=[]
        menu.offer_update('v99.0.0',update_answers.append)
        startup_answers=[];startup_request=(1,(1,),1)
        menu.ask_late_start(('stale',),lambda *args:startup_answers.append('stale'))
        menu.ask_late_start(startup_request,lambda r,accepted:startup_answers.append((r,accepted)))
        time.sleep(.05)
        assert not dialog('Battle already in progress'),'Battle choice should wait for the welcome.'
        assert not dialog('New version v99.0.0 available'),'The update offer should wait for the welcome.'
        from PIL import ImageGrab
        ImageGrab.grab(window=welcome).save(P/'build/welcome-preview.png')
        user.SendMessageW(button,0xf5,0,0)
        wait_for(lambda:not dialog(f"What's new in v{VERSION}"))
        startup_prompt=wait_for(lambda:dialog('Battle already in progress'))
        startup_no=wait_for(lambda:user.GetDlgItem(startup_prompt,10) if user.IsWindowVisible(startup_prompt) else None)
        user.SendMessageW(startup_no,0xf5,0,0)
        wait_for(lambda:startup_answers)
        assert startup_answers==[(startup_request,False)]
        update=wait_for(lambda:dialog('New version v99.0.0 available'))
        no=wait_for(lambda:user.GetDlgItem(update,10))
        ImageGrab.grab(window=update).save(P/'build/update-available-preview.png')
        user.SendMessageW(no,0xf5,0,0)
        wait_for(lambda:update_answers==[False])
        wait_for(lambda:menu.update_prompt.closed.is_set())
        menu.offer_update('v99.0.0',update_answers.append)
        update=wait_for(lambda:dialog('New version v99.0.0 available'))
        yes=wait_for(lambda:user.GetDlgItem(update,9))
        user.SendMessageW(yes,0xf5,0,0)
        wait_for(lambda:update_answers==[False,True])
        wait_for(lambda:menu.update_prompt.closed.is_set())
        wait_for(lambda:user.IsWindowEnabled(menu.hwnd))
        assert not user.IsWindow(dimmer)
        assert user.IsWindowVisible(menu.hwnd)
        assert user.SendMessageW(menu.listing,0x18b,0,0)==2
        user.SendMessageW(menu.listing,0x186,0,0)
        user.SendMessageW(menu.hwnd,0x111,(2<<16)|20,0)
        assert actions.get_nowait()==('open_capture',str(preview))
        # Capture only this test window for layout review.
        ImageGrab.grab(window=menu.hwnd).save(P/'build/main-menu-preview.png')
        user.SendMessageW(menu.hwnd,0x111,8,0)
        rename=wait_for(lambda:dialog('Rename Battle'))
        editor=wait_for(lambda:user.GetDlgItem(rename,102))
        assert text_of(editor)==preview.stem
        user.SetWindowTextW(editor,'bad/name')
        user.SendMessageW(user.GetDlgItem(rename,9),0xf5,0,0)
        assert user.IsWindow(rename),'Invalid filename must leave the editor open.'
        user.SetWindowTextW(editor,'My renamed battle')
        ImageGrab.grab(window=rename).save(P/'build/rename-battle-preview.png')
        user.SendMessageW(user.GetDlgItem(rename,9),0xf5,0,0)
        wait_for(lambda:menu.rename_prompt.closed.is_set())
        assert actions.get_nowait()==('rename_capture',(str(preview),'My renamed battle'))
        wait_for(lambda:user.IsWindowEnabled(menu.hwnd))
        # Inject an isolated hover without moving the user's real pointer.
        with patch.object(menu.user,'TrackMouseEvent',return_value=True) as tracking:
            assert user.SendMessageW(menu.listing,0x1a9,0,(63<<16)|24)==1
            user.SendMessageW(menu.listing,0x200,0,(63<<16)|24)
            user.UpdateWindow(menu.listing)
            tracking.assert_called()
            # The stock list can immediately send Leave for the real pointer,
            # which remains outside this isolated test window.
            user.SendMessageW(menu.listing,0x2a3,0,0)
            assert menu.hover_row==-1
        user.SendMessageW(menu.hwnd,0x10,0,0)
        assert menu.thread.is_alive() and not user.IsWindowVisible(menu.hwnd)
        menu.focus();wait_for(lambda:user.IsWindowVisible(menu.hwnd))
        assert not dialog(f"What's new in v{VERSION}")
        answers=[];request=(1,(2,),3)
        menu.ask_late_start(request,lambda r,accepted:answers.append((r,accepted)))
        prompt=wait_for(lambda:dialog('Battle already in progress'))
        button=wait_for(lambda:user.GetDlgItem(prompt,10) if user.IsWindowVisible(prompt) else None)
        ImageGrab.grab(window=prompt).save(P/'build/late-start-preview.png')
        user.SendMessageW(button,0xf5,0,0)
        wait_for(lambda:answers)
        wait_for(lambda:user.IsWindowEnabled(menu.hwnd))
        assert answers==[(request,False)]
        for ident,expected in [(2,('export_capture',str(preview))),(5,'restart'),(6,'exit')]:
            user.SendMessageW(menu.hwnd,0x111,ident,0)
            assert actions.get_nowait()==expected
    finally:menu.close()
    assert not menu.thread.is_alive(),menu.error

# Exercise the actual tray window procedure without requiring Explorer in QA.
# Only Shell registration is stubbed; native window/messages remain real.
original_dll=ctypes.WinDLL
shell=Mock();shell.Shell_NotifyIconW=Mock(return_value=1)
def dll(name,*args,**kwargs):
    return shell if name=='shell32' else original_dll(name,*args,**kwargs)
with patch('tray.ctypes.WinDLL',side_effect=dll):
    tray=TrayIcon();tray.start()
    try:
        assert tray.ready.wait(5) and tray.available,tray.error
        user.SendMessageW(tray.hwnd,0x8001,1,0x203)
        assert tray.actions.get(timeout=1)=='main_menu'
        user.SendMessageW(tray.hwnd,0x111,6,0)
        assert tray.actions.get(timeout=1)=='restart'
    finally:tray.stop()

result=dict(startup_menu=True,separate_welcome=True,reopen_without_welcome=True,
    close_keeps_running=True,double_click_opens_capture=True,late_start_no=True,
    separate_html_export=True,restart_action=True,safe_meter_theme=True,silent_custom_dialogs=True,
    native_tray_double_click_dispatch=True,native_tray_restart_dispatch=True,
    modal_dimmer_alpha=166,modal_owner_restored=True,queued_modal_choice=True,
    row_hover_dispatch=True,button_hierarchy=True,installed_version_notes=True,
    background_notes_refresh=True,startup_update_yes_no=True,update_offer_waits_for_welcome=True,
    rename_dialog=True,rename_validation=True)
(P/'build/main-menu-check.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,indent=2))
