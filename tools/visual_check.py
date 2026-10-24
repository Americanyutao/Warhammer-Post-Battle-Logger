"""Capture only the prototype's own window; never a desktop screenshot."""
from pathlib import Path
import sys
import tkinter as tk
sys.dont_write_bytecode = True
PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT/'src'))
from app import App
from PIL import ImageGrab
root=tk.Tk()
app=App(root,demo=True)
def capture():
    root.update()
    ImageGrab.grab(window=root.winfo_id()).save(PROJECT/'build/live-debug-preview.png')
    app.advanced.set(True);app.refresh();root.geometry('820x560');root.update()
    ImageGrab.grab(window=root.winfo_id()).save(PROJECT/'build/live-debug-minimum.png')
    app.close()
root.after(700,capture)
root.mainloop()
print('Window rendered at default and minimum sizes.')
