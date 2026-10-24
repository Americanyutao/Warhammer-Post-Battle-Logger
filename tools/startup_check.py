"""Start the real window/worker briefly; verify read-only access without game changes."""
import ctypes
import os
from pathlib import Path
import sys
import tkinter as tk

sys.dont_write_bytecode = True
PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT/'src'))
from app import App
from memory import WindowsAPI, ProcessMemory
from resources import atomic_json, process_resources

api = WindowsAPI()
memory = ProcessMemory(api,os.getpid())
buffer = ctypes.create_string_buffer(b'logger-access-check')
assert memory.read(ctypes.addressof(buffer),19) == b'logger-access-check'
memory.close()
root = tk.Tk()
root.withdraw()
app = App(root)
result = dict(read_only_windows_access=True, game_pids=api.game_pids(), live_battle=False)


def finish():
    result.update(status=app.worker.status, worker_started=app.worker.is_alive(), live_battle=app.worker.recorder is not None,
                  debug_default=app.debug.get(), **process_resources())
    app.close()


root.after(1500,finish)
root.mainloop()
result['worker_stopped'] = not app.worker.is_alive()
assert result['worker_started'] and result['worker_stopped']
assert not result['status'].startswith('Logger error:'), result['status']
atomic_json(PROJECT/'build/startup-check.json',result)
print(result)
