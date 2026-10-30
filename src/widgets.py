"""Virtualized damage rows and small native Tk controls."""
import tkinter as tk
import time
from tkinter import ttk, font
from animation import Transitions

BG = '#131a22'
TEXT = '#eef0f3'
MUTED = '#97a4b4'
GOLD = '#d6b568'
GOLD_BAR = '#3a3c36'
DIM = '#697482'


class Tooltip:
    def __init__(self, widget, text):
        self.widget, self.text = widget, text
        self.pending = self.window = None
        widget.bind('<Enter>', self.enter, add='+')
        widget.bind('<Leave>', self.hide, add='+')
        widget.bind('<ButtonPress>', self.hide, add='+')
    def enter(self, event=None):
        self.pending = self.widget.after(450, self.show)
    def show(self):
        self.pending = None
        if not self.widget.winfo_exists(): return
        self.window = tk.Toplevel(self.widget)
        self.window.overrideredirect(True)
        self.window.attributes('-topmost', True)
        self.window.geometry(f'+{self.widget.winfo_rootx()-80}+{self.widget.winfo_rooty()+self.widget.winfo_height()+7}')
        tk.Label(self.window, text=self.text, background='white', foreground='#202020',
                 font=('Segoe UI', 9), padx=10, pady=7, wraplength=235, justify='left',
                 relief='solid', borderwidth=1).pack()
    def hide(self, event=None):
        if self.pending:
            self.widget.after_cancel(self.pending); self.pending = None
        if self.window:
            self.window.destroy(); self.window = None


class RankedTable(ttk.Frame):
    def __init__(self, parent, on_sort=None, columns=None, on_bar_click=None, bar_color=None, transparent_background=False,
                 slide_rows=False,minimum_width=430,stat_width=200,show_header=True):
        super().__init__(parent)
        self.columns=columns or (('DAMAGE','damage'),('GOLD DAMAGE DEALT','gold_damage'),('KILLS','kills'))
        self.rows, self.labels, self.pool, self.names = [], {}, [], {}
        self.row_height, self.enemy, self.selected = 42, False, None
        self.offset = 0
        self.transitions = Transitions()
        self.frame_id = None
        self.on_sort, self.sort_by = on_sort, 'damage'
        self.on_bar_click=on_bar_click;self.bar_color=bar_color;self.transparent_background=transparent_background
        self.slide_rows=slide_rows;self.minimum_width=minimum_width;self.stat_width=stat_width;self.last_scroll=0;self.unit_slots={}
        self.normal = font.Font(family='Segoe UI', size=10)
        self.small = font.Font(family='Segoe UI', size=8)
        self.number = font.Font(family='Segoe UI Semibold', size=11)
        self.header = tk.Canvas(self, height=32, background=BG, highlightthickness=0)
        self.header.grid(row=0, column=0, sticky='ew')
        if not show_header:self.header.grid_remove()
        self.canvas = tk.Canvas(self, background=BG, yscrollincrement=1, highlightthickness=0)
        self.canvas.grid(row=1, column=0, sticky='nsew')
        self.columnconfigure(0, weight=1); self.rowconfigure(1, weight=1)
        self.canvas.bind('<Configure>', lambda event: self.draw())
        self.canvas.bind('<MouseWheel>', self.wheel); self.canvas.bind('<Button-1>', self.click)
        self.header.bind('<Configure>', lambda event: self.draw_header())
        self.heading_items = []
        for text,anchor,metric in [('UNIT','w',None),*((label,'e',field) for label,field in self.columns)]:
            item = self.header.create_text(0, 16, anchor=anchor, text=text, fill=MUTED, font=self.small)
            self.heading_items.append(item)
            if metric:
                self.header.tag_bind(item, '<Button-1>', lambda event, index=len(self.heading_items)-2: self.choose_sort(self.columns[index][1]))
                self.header.tag_bind(item, '<Enter>', lambda event: self.header.configure(cursor='hand2'))
                self.header.tag_bind(item, '<Leave>', lambda event: self.header.configure(cursor=''))
        self.empty = self.canvas.create_text(0, 52, anchor='center', fill=MUTED, font=self.normal)
        self.empty_message = 'Waiting for battle'
    def choose_sort(self, metric):
        if metric in [field for _,field in self.columns] and self.on_sort:
            self.on_sort(metric)
    def draw_header(self):
        width = max(self.header.winfo_width(), self.minimum_width)
        positions=[18,width-16] if len(self.columns)==1 else [18,width-205,width-16] if len(self.columns)==2 else [18,width-240,width-74,width-16]
        for item,x,(label,metric) in zip(self.heading_items,positions,[('UNIT',None),*self.columns]):
            self.header.coords(item,x,16)
            self.header.itemconfigure(item,text=label+('  \u25be' if metric and metric==self.sort_by else ''),
                                      fill=GOLD if metric and metric==self.sort_by else MUTED)
    def set_rows(self, rows, enemy=False, compact=False, empty_message='No units in this view', labels=None, sort_by='damage', generation=None,animation_seconds=.5):
        self.rows, self.enemy, self.labels, self.sort_by = rows, enemy, labels or {}, sort_by
        height = 32 if compact else 42
        if height != self.row_height:
            self.row_height = height
        self.empty_message = empty_message
        maximum=max((getattr(entry,sort_by) or 0 for entry in rows),default=0)
        targets={}
        for index,entry in enumerate(rows):
            key=(entry.sample.uid,entry.sample.address,entry.sample.result)
            for _,field in self.columns:
                targets[key+(field,)]=getattr(entry,field)
            targets[key+('bar',)]=(getattr(entry,sort_by) or 0)/maximum if maximum else 0
            if self.slide_rows:targets[key+('rank',)]=index*self.row_height
        self.transitions.update(targets,time.monotonic(),(generation,enemy),duration=animation_seconds)
        if self.slide_rows:
            keys={(entry.sample.uid,entry.sample.address,entry.sample.result) for entry in rows}
            for key in list(self.unit_slots):
                if key not in keys:
                    slot=self.unit_slots.pop(key)
                    for item in slot['items']:self.canvas.delete(item)
            self.pool=list(self.unit_slots.values())
        self.draw()

    def animate(self):
        self.frame_id=None
        self.draw()

    def destroy(self):
        if self.frame_id is not None:
            self.after_cancel(self.frame_id);self.frame_id=None
        super().destroy()
    def scroll_to(self, *args):
        self.last_scroll=time.monotonic()
        viewport = max(self.canvas.winfo_height(),1)
        total = max(viewport,len(self.rows)*self.row_height)
        if args[0] == 'moveto': self.offset = float(args[1])*total
        elif args[0] == 'scroll':
            self.offset += int(args[1])*(viewport if args[2]=='pages' else self.row_height)
        self.draw()
    def wheel(self, event):
        if event.delta:
            self.scroll_to('scroll',-int(event.delta/120) or (-1 if event.delta > 0 else 1),'units')
        return 'break'
    def click(self, event):
        index = int(self.canvas.canvasy(event.y)//self.row_height)
        if self.slide_rows:
            position=self.canvas.canvasy(event.y);animated=self.transitions.snapshot(time.monotonic())
            index=next((i for i,entry in reversed(list(enumerate(self.rows))) if
                (y:=animated.get((entry.sample.uid,entry.sample.address,entry.sample.result,'rank'),i*self.row_height))<=position<y+self.row_height),-1)
        if 0 <= index < len(self.rows):
            if self.on_bar_click and 10<=event.x<=max(self.canvas.winfo_width(),self.minimum_width)-self.stat_width+10:
                self.on_bar_click();return
            self.selected = self.rows[index].sample.uid; self.draw()
    def shorten(self, text, width):
        key = text, int(width)
        if key in self.names: return self.names[key]
        if self.normal.measure(text) <= width: result = text
        else:
            low, high = 0, len(text)
            while low < high:
                mid = (low+high+1)//2
                if self.normal.measure(text[:mid]+'…') <= width: low = mid
                else: high = mid-1
            result = text[:low]+'…'
        if len(self.names) >= 2048: self.names.clear()
        self.names[key] = result
        return result
    def new_slot(self):
        c = self.canvas
        return dict(items=[c.create_rectangle(0,0,1,1,width=0,tags=('rowbg',)), c.create_rectangle(0,0,1,1,width=0,tags=('rowbar',))] +
                    [c.create_text(0,0,anchor=a,font=f,tags=('rowtext',)) for a,f in [('w',self.normal),*(('e',self.number) for _ in self.columns)]], values=None,texts={})
    def draw(self):
        c = self.canvas; width = max(c.winfo_width(),self.minimum_width); viewport = max(c.winfo_height(),1)
        total = max(viewport,len(self.rows)*self.row_height)
        self.offset = max(0,min(self.offset,total-viewport))
        c.configure(scrollregion=(0,0,1,total))
        c.yview_moveto(self.offset/total)
        first = max(0,int(c.canvasy(0)//self.row_height)); last = min(len(self.rows),first+viewport//self.row_height+2)
        now=time.monotonic();animated=self.transitions.snapshot(now)
        visible=[(i,entry,animated.get((entry.sample.uid,entry.sample.address,entry.sample.result,'rank'),i*self.row_height)) for i,entry in enumerate(self.rows)] if self.slide_rows else [(i,self.rows[i],i*self.row_height) for i in range(first,last)]
        if self.slide_rows:visible=[row for row in visible if self.offset-self.row_height<row[2]<self.offset+viewport+self.row_height]
        if self.slide_rows:
            assigned=[]
            for index,entry,y in visible:
                key=(entry.sample.uid,entry.sample.address,entry.sample.result)
                if key not in self.unit_slots:self.unit_slots[key]=self.new_slot()
                assigned.append((self.unit_slots[key],(index,entry,y)))
            self.pool=list(self.unit_slots.values())
            active={id(slot) for slot,_ in assigned}
            assigned.extend((slot,None) for slot in self.pool if id(slot) not in active)
        else:
            while len(self.pool)<len(visible):self.pool.append(self.new_slot())
            assigned=[(slot,visible[offset] if offset<len(visible) else None) for offset,slot in enumerate(self.pool)]
        for slot,row in assigned:
            if row is None:
                for item in slot['items']: c.itemconfigure(item,state='hidden')
                slot['values'] = None; continue
            index,entry,y=row;uid = entry.sample.uid
            name = self.shorten(self.labels.get(uid,entry.sample.name),max(50,width-(self.stat_width+12 if len(self.columns)==1 else 365 if len(self.columns)==2 else 290)))
            key=(uid,entry.sample.address,entry.sample.result)
            amount = lambda value: format(int(value+0.5),',') if value is not None else '-'
            texts=[('Unlimited' if field=='healing_budget_remaining_hp' and getattr(entry,'healing_budget_unlimited',False) else amount(animated.get(key+(field,),getattr(entry,field)))) for _,field in self.columns]
            fraction=animated.get(key+('bar',),0)
            dim = entry.dimmed
            color=self.bar_color(entry) if callable(self.bar_color) else self.bar_color
            color=color or ('#222831' if dim else GOLD_BAR if self.sort_by=='gold_damage' else '#463039' if self.enemy else '#263c39')
            values = (index,uid,name,*texts,dim,width,self.row_height,fraction,self.sort_by,self.enemy,self.selected,color,y)
            if slot['values'] == values: continue
            slot['values'] = values
            background,bar,label,*numbers = slot['items'];middle = y+self.row_height/2
            c.coords(background,3,y+1,width-3,y+self.row_height-1)
            c.itemconfigure(background,state='normal',fill=BG if self.transparent_background else '#263344' if uid==self.selected else BG if index%2 else '#18212b')
            c.coords(bar,10,y+3,10+max(0,width-(self.stat_width if len(self.columns)==1 else 345 if len(self.columns)==2 else 270))*fraction,y+self.row_height-3)
            c.itemconfigure(bar,state='normal',fill=color)
            positions=[width-16] if len(self.columns)==1 else [width-205,width-16] if len(self.columns)==2 else [width-240,width-74,width-16]
            for item,x,txt in [(label,18,name),*zip(numbers,positions,texts)]:
                c.coords(item,x,middle)
                style=(txt,DIM if dim else TEXT)
                if slot['texts'].get(item)!=style:
                    c.itemconfigure(item,text=txt,fill=style[1]);slot['texts'][item]=style
                c.itemconfigure(item,state='normal')
        # Moving row backgrounds must never cover another unit's label.
        c.tag_lower('rowbg');c.tag_raise('rowbar');c.tag_raise('rowtext')
        c.coords(self.empty,width/2,58)
        c.itemconfigure(self.empty,text=self.empty_message,state='normal' if not self.rows else 'hidden',width=max(150,width-40))
        c.tag_raise(self.empty); self.draw_header()
        if self.transitions.active(now) and self.winfo_ismapped():
            if self.frame_id is None:self.frame_id=self.after(16,self.animate)
        elif self.frame_id is not None:
            self.after_cancel(self.frame_id);self.frame_id=None
