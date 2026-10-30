"""Matching small meter buttons; icons are drawn from shared vector paths."""
from functools import lru_cache
import math
import tkinter as tk

HEADER='#151D28';TEXT='#EDF2F7';MUTED='#ACB8C9';ACTIVE='#28384E';HOVER='#263447';GOLD='#E5A93C'
PATHS={
    'close':[[(6,6),(18,18)],[(18,6),(6,18)]],
    'pin':[[(9,3),(15,3)],[(10,3),(10,9),(7,13),(17,13),(14,9),(14,3)],[(12,13),(12,21)]],
    'pointer':[[(5,3),(19,11),(13,13),(11,19),(5,3)]],
    'sliders':[[(4,6),(20,6)],[(4,12),(20,12)],[(4,18),(20,18)],[(9,3),(9,9)],[(15,9),(15,15)],[(10,15),(10,21)]],
    'grip':[[(9,5),(9,6)],[(15,5),(15,6)],[(9,11),(9,12)],[(15,11),(15,12)],[(9,17),(9,18)],[(15,17),(15,18)]],
    'resize':[[(7,20),(20,7)],[(13,20),(20,13)],[(19,20),(20,19)]]}


class IconBitmap:
    def __init__(self,size,rgb):self.size=size;self.rgb=bytes(rgb)
    def ppm(self):return f'P6\n{self.size} {self.size}\n255\n'.encode('ascii')+self.rgb
    def bgrx(self):
        data=bytearray()
        for i in range(0,len(self.rgb),3):data.extend((self.rgb[i+2],self.rgb[i+1],self.rgb[i],0))
        return bytes(data)


@lru_cache(maxsize=64)
def icon_bitmap(name,active=False,hover=False,size=32):
    bg=ACTIVE if active else HOVER if hover else HEADER;ink=GOLD if active else MUTED
    rgb=lambda value:bytes.fromhex(value[1:]);scale=4;side=size*scale;raster=bytearray(rgb(bg)*(side*side))
    def line(a,b,color,width=1.5):
        ax,ay=a;bx,by=b;ax*=scale;ay*=scale;bx*=scale;by*=scale;r=width*scale/2
        dx=bx-ax;dy=by-ay;length=dx*dx+dy*dy
        for y in range(max(0,math.floor(min(ay,by)-r)),min(side,math.ceil(max(ay,by)+r))):
            for x in range(max(0,math.floor(min(ax,bx)-r)),min(side,math.ceil(max(ax,bx)+r))):
                t=max(0,min(1,((x+.5-ax)*dx+(y+.5-ay)*dy)/length)) if length else 0
                if (x+.5-ax-t*dx)**2+(y+.5-ay-t*dy)**2<=r*r:
                    index=(y*side+x)*3;raster[index:index+3]=rgb(color)
    if active:
        for a,b in [((1,1),(30,1)),((30,1),(30,30)),((30,30),(1,30)),((1,30),(1,1))]:line(a,b,'#43546C',1)
    for path in PATHS[name]:
        points=[((x+4)*size/32,(y+4)*size/32) for x,y in path]
        for a,b in zip(points,points[1:]):line(a,b,ink)
    if name=='pointer' and active:line((9*size/32,23*size/32),(24*size/32,8*size/32),GOLD,1)
    output=bytearray()
    for y in range(size):
        for x in range(size):
            indices=[((y*scale+sy)*side+x*scale+sx)*3 for sy in range(scale) for sx in range(scale)]
            output.extend(round(sum(raster[index+c] for index in indices)/(scale*scale)) for c in range(3))
    return IconBitmap(size,output)


class MeterButton(tk.Button):
    def __init__(self,parent,text='',icon=None,command=None):
        text=text or {'pin':'Always on top','pointer':'Let clicks through','sliders':'Appearance'}.get(icon,'')
        super().__init__(parent,text=text,command=command,font=('Segoe UI',10),background=HEADER,foreground=MUTED,
            activebackground=HOVER,activeforeground=TEXT,relief='flat',borderwidth=0,highlightthickness=1,
            highlightbackground=HEADER,highlightcolor=GOLD,padx=9,pady=5,takefocus=True,cursor='hand2')
        self.icon=icon;self.active=False;self.hover=False;self.images={}
        if icon:self.configure(width=30,height=30,padx=0,pady=0)
        self.bind('<Enter>',lambda event:self.paint(hover=True));self.bind('<Leave>',lambda event:self.paint(hover=False))
        self.paint()

    def paint(self,active=None,hover=None):
        if active is not None:self.active=active
        if hover is not None:self.hover=hover
        bg=ACTIVE if self.active else HOVER if self.hover else HEADER
        self.configure(background=bg,activebackground=bg,foreground=TEXT if self.active else MUTED,highlightbackground=bg)
        if self.icon:
            key=self.active,self.hover
            if key not in self.images:
                self.images[key]=tk.PhotoImage(master=self,data=icon_bitmap(self.icon,*key).ppm(),format='PPM')
            self.configure(image=self.images[key])


class MeterTooltip:
    def __init__(self,root,native):self.root=root;self.native=native;self.pending=None;self.window=None
    def attach(self,widget,text):
        widget.bind('<Enter>',lambda event:self.schedule(widget,text),add='+')
        widget.bind('<Leave>',lambda event:self.hide(),add='+');widget.bind('<ButtonPress>',lambda event:self.hide(),add='+')
        widget.bind('<FocusIn>',lambda event:self.schedule(widget,text),add='+');widget.bind('<FocusOut>',lambda event:self.hide(),add='+')
    def schedule(self,widget,text):
        self.hide();self.pending=self.root.after(450,lambda:self.show(widget,text))
    def show(self,widget,text):
        self.pending=None
        if not widget.winfo_exists():return
        self.window=tk.Toplevel(self.root);self.window.withdraw();self.window.overrideredirect(True)
        tk.Label(self.window,text=text,font=('Segoe UI',9),background='#202B3C',foreground=TEXT,padx=9,pady=5).pack()
        self.window.geometry(f'+{max(0,widget.winfo_rootx()-40)}+{widget.winfo_rooty()+widget.winfo_height()+6}')
        self.window.update_idletasks()
        if self.native:self.native.no_activate(self.window)
        self.window.deiconify();self.window.lift()
    def hide(self):
        if self.pending:self.root.after_cancel(self.pending);self.pending=None
        if self.window:self.window.destroy();self.window=None
