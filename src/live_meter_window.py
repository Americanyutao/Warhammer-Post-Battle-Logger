"""Compact overlay; one control layout, independent from game collection."""
import json
import sys
import time
import tkinter as tk
from pathlib import Path
from widgets import RankedTable,BG
from live_meter import COLUMNS,entries_for
from meter_controls import MeterButton,MeterTooltip,HEADER,TEXT,MUTED,GOLD

SIDE_COLORS={'Allied':'#1F7848','Enemy':'#963F4B'}
def unit_bar_color(entry):return SIDE_COLORS.get(entry.sample.side,'#2563EB')


class LiveMeterWindow:
    def __init__(self,root,check_output=None,preferences=None,on_preferences=None):
        options=preferences or {};layout=options.get('layout',{})
        self.root=root;self.check_output=check_output;self.on_preferences=on_preferences;self.current={}
        self.native=None;self.errors=[];self._moving=False;self.gesture_job=None
        self.drag_origin=self.resize_origin=None;self.save_job=None;self.display_revision=-1;self.applying_display=False
        self.animation_seconds=1.;self.show_revision=0;self.last_bounds=(layout.get('x',50),layout.get('y',50),layout.get('width',470),layout.get('height',460))
        self.cached_preferences={};self.hover_held=False;self.last_order_context=None;self.check_pending=False
        self.saved_preferences=dict(layout=dict(layout))
        root.overrideredirect(True);root.title('Live damage meter');root.configure(background=BG);root.minsize(340,220)
        root.geometry(f'{self.last_bounds[2]}x{self.last_bounds[3]}');root.attributes('-alpha',1.)
        self.scope=tk.StringVar(root,layout.get('scope','all'));self.metric=tk.StringVar(root,layout.get('metric','damage'))
        self.topmost=tk.BooleanVar(root,False)
        panel=self.panel=tk.Frame(root,background=BG);panel.pack(fill='both',expand=True,padx=5,pady=5)
        self.header=tk.Frame(panel,background=HEADER,height=44);self.header.pack(fill='x');self.header.pack_propagate(False)
        self.grip=tk.Label(self.header,text='⠿',font=('Segoe UI',13),background=HEADER,foreground=MUTED,cursor='fleur');self.grip.pack(side='left',padx=(7,2))
        title=tk.Label(self.header,text='Meter',font=('Segoe UI Semibold',11),background=HEADER,foreground=TEXT);title.pack(side='left')
        self.close_button=MeterButton(self.header,icon='close',command=root.destroy);self.close_button.pack(side='right',padx=2)
        self.topmost_check=MeterButton(self.header,icon='pin',command=lambda:self.topmost.set(not self.topmost.get()));self.topmost_check.pack(side='right',padx=2)
        self.filters=tk.Frame(panel,background=HEADER,height=44);self.filters.pack(fill='x');self.filters.pack_propagate(False)
        self.metric_buttons={key:MeterButton(self.filters,text=label,command=lambda key=key:self.choose_metric(key)) for label,key in [('Damage','damage'),('Heal budget','healing_budget_remaining_hp')]}
        self.scope_buttons={key:MeterButton(self.filters,text=label,command=lambda key=key:self.choose_scope(key)) for label,key in [('All','all'),('Ally','ally'),('Enemy','enemy')]}
        self.filters.bind('<Configure>',lambda event:self.layout_filters())
        table=RankedTable(panel,columns=(COLUMNS[0],),bar_color=unit_bar_color,transparent_background=True,slide_rows=True,minimum_width=280,stat_width=90,show_header=False)
        table.pack(fill='both',expand=True,pady=(4,0));self.tables={'Units':table};self.table=table
        self.footer=tk.Frame(panel,background=BG,height=22);self.footer.pack(side='bottom',fill='x',before=table);self.footer.pack_propagate(False)
        self.state_label=tk.Label(self.footer,text='Waiting',font=('Segoe UI',9),background=BG,foreground=MUTED);self.state_label.pack(side='left',padx=5)
        self.resize_grip=tk.Canvas(self.footer,width=22,height=20,background=HEADER,highlightthickness=0,cursor='size_nw_se');self.resize_grip.pack(side='right')
        for inset in (5,10,15):self.resize_grip.create_line(22-inset,18,20,20-inset,fill=MUTED,width=1)
        self.resize_grip.bind('<ButtonPress-1>',lambda event:self.start_resize(event,'se'))
        self.resize_grip.bind('<B1-Motion>',lambda event:self.resize_to(event.x_root,event.y_root));self.resize_grip.bind('<ButtonRelease-1>',lambda event:self.end_gesture())
        for place in [dict(relx=0,rely=0,relheight=1,width=3),dict(relx=1,rely=0,relheight=1,width=3,anchor='ne'),dict(relx=0,rely=0,relwidth=1,height=3),dict(relx=0,rely=1,relwidth=1,height=3,anchor='sw')]:tk.Frame(root,background='#253246').place(**place)
        root.update_idletasks()
        if sys.platform=='win32':
            from live_overlay import WindowsOverlay
            self.native=WindowsOverlay();self.last_bounds=self.native.fit_bounds(*self.last_bounds)
            root.geometry(f'{self.last_bounds[2]}x{self.last_bounds[3]}');root.update_idletasks();self.native.move(root,*self.last_bounds[:2])
        self.tooltip=MeterTooltip(root,self.native)
        for widget,text in [(self.close_button,'Close meter'),(self.topmost_check,'Always on top'),(self.metric_buttons['healing_budget_remaining_hp'],'Remaining healing budget')]:self.tooltip.attach(widget,text)
        for widget in (self.header,self.grip,title):
            widget.bind('<ButtonPress-1>',lambda event:self.start_drag(event.x_root,event.y_root));widget.bind('<B1-Motion>',lambda event:self.move_drag(event.x_root,event.y_root));widget.bind('<ButtonRelease-1>',lambda event:self.end_gesture())
        self.topmost.trace_add('write',lambda *_:self.set_topmost())
        root.bind('<Configure>',self.schedule_control,add='+');root.bind('<Map>',self.schedule_control,add='+')
        root.bind('<Destroy>',lambda event:self.close_control() if event.widget==root else None,add='+')
        root.bind('<ButtonPress-1>',self.edge_press,add='+');root.bind('<B1-Motion>',self.edge_move,add='+');root.bind('<ButtonRelease-1>',lambda event:self.end_gesture(),add='+')
        root.bind('<Motion>',self.edge_cursor,add='+')
        if check_output:root.report_callback_exception=lambda kind,value,tb:self.errors.append(str(value))
        self.table.on_bar_click=self.toggle_metric;self.refresh_controls();self.render();self.queue_save();root.after(80,self.hover_tick)

    def layout_filters(self):
        width=self.filters.winfo_width();metrics=list(self.metric_buttons.values());scopes=list(self.scope_buttons.values())
        metric_width=sum(button.winfo_reqwidth() for button in metrics)+4;scope_width=sum(button.winfo_reqwidth() for button in scopes)+4
        wrap=metric_width+scope_width+28>width;self.filters.configure(height=76 if wrap else 42)
        for buttons,start,y in [(metrics,7,4),(scopes,7 if wrap else width-scope_width-7,38 if wrap else 4)]:
            x=start
            for button in buttons:button.place(x=x,y=y);x+=button.winfo_reqwidth()+2
    def choose_scope(self,value):self.scope.set(value);self.refresh_controls();self.render(force_order=True);self.queue_save()
    def choose_metric(self,value):self.metric.set(value);self.refresh_controls();self.render(force_order=True);self.queue_save()
    def toggle_metric(self):self.choose_metric('healing_budget_remaining_hp' if self.metric_key=='damage' else 'damage')
    @property
    def metric_key(self):return self.metric.get()
    def refresh_controls(self):
        for key,button in self.scope_buttons.items():button.paint(active=key==self.scope.get())
        for key,button in self.metric_buttons.items():button.paint(active=key==self.metric.get())
        self.topmost_check.paint(active=self.topmost.get())
    def set_topmost(self):
        self.root.attributes('-topmost',self.topmost.get());self.refresh_controls()
    def process_native_input(self):return True
    def hover_tick(self):
        x,y=self.root.winfo_pointerxy()
        if self.hover_held and not self.point_in(self.table.canvas,x,y) and time.monotonic()-self.table.last_scroll>.6:self.render(force_order=True)
        self.root.after(80,self.hover_tick)
    def point_in(self,widget,x,y):return widget.winfo_ismapped() and widget.winfo_rootx()<=x<widget.winfo_rootx()+widget.winfo_width() and widget.winfo_rooty()<=y<widget.winfo_rooty()+widget.winfo_height()
    def table_at(self,x,y):return self.table if self.point_in(self.table.canvas,x,y) else None
    def bounds(self):return self.native.bounds(self.root) if self.native else (self.root.winfo_x(),self.root.winfo_y(),self.root.winfo_width(),self.root.winfo_height())
    def edge_at(self,x,y):
        left,top,width,height=self.bounds();horizontal='w' if x-left<6 else 'e' if left+width-x<=6 else '';vertical='n' if y-top<6 else 's' if top+height-y<=6 else ''
        return vertical+horizontal if left<=x<=left+width and top<=y<=top+height else ''
    def edge_cursor(self,event):
        edge=self.edge_at(event.x_root,event.y_root)
        self.root.configure(cursor=('size_nw_se' if edge in ('nw','se') else 'size_ne_sw' if edge in ('ne','sw') else 'size_we' if edge in ('w','e') else 'size_ns' if edge else ''))
    def edge_press(self,event):
        edge=self.edge_at(event.x_root,event.y_root)
        if edge:self.start_resize(event,edge)
    def edge_move(self,event):
        if self.resize_origin:self.resize_to(event.x_root,event.y_root)
    def start_drag(self,x,y):
        self.tooltip.hide()
        self.drag_origin=(x,y,*self.bounds()[:2]);self.header.grab_set()
        if self.native:self.native.capture(self.header)
        self.watch_gesture()
    def move_drag(self,x,y):
        if self.drag_origin:
            sx,sy,left,top=self.drag_origin;left=int(left+x-sx);top=int(top+y-sy)
            if self.native:self.native.move(self.root,left,top)
            else:self.root.geometry(f'+{left}+{top}')
            self.queue_save()
    def start_resize(self,event,edge='se'):
        self.tooltip.hide();self.drag_origin=None;self.resize_origin=(event.x_root,event.y_root,*self.bounds(),edge)
        self.resize_grip.grab_set()
        if self.native:self.native.capture(self.resize_grip)
        self.watch_gesture()
    def watch_gesture(self):
        # Tk can suppress motion outside a frameless window. Sample only the
        # current pointer during a held gesture; never queue or ease window moves.
        if self.gesture_job is None:self.gesture_job=self.root.after(16,self.gesture_tick)
    def gesture_tick(self):
        self.gesture_job=None
        if not (self.resize_origin or self.drag_origin):return
        if self.native and not self.native.mouse_down():self.end_gesture();return
        x,y=self.root.winfo_pointerxy()
        if self.resize_origin:self.resize_to(x,y)
        else:self.move_drag(x,y)
        self.watch_gesture()
    def resize_to(self,x,y):
        if not self.resize_origin:return
        sx,sy,left,top,width,height,edge=self.resize_origin;dx=x-sx;dy=y-sy
        new_width=max(340,width+dx if 'e' in edge else width-dx if 'w' in edge else width);new_height=max(220,height+dy if 's' in edge else height-dy if 'n' in edge else height)
        new_left=left+width-new_width if 'w' in edge else left;new_top=top+height-new_height if 'n' in edge else top;self._moving=True
        try:
            self.root.geometry(f'{new_width}x{new_height}');self.root.update_idletasks()
            if self.native:self.native.move(self.root,new_left,new_top)
        finally:self._moving=False
        self.last_bounds=self.bounds();self.queue_save()
    def end_gesture(self):
        self.drag_origin=self.resize_origin=None
        if self.gesture_job:self.root.after_cancel(self.gesture_job);self.gesture_job=None
        if self.native:self.native.release()
        if self.root.grab_current():self.root.grab_current().grab_release()
        self.queue_save()
    def schedule_control(self,event=None):
        if event is not None and event.widget!=self.root:return
        if self._moving:return
        self.tooltip.hide();self.queue_save()
    def close_control(self):self.flush_preferences();self.tooltip.hide()
    def show(self):
        if self.native:self.native.taskbar_window(self.root);self.native.no_activate(self.root)
        self.root.deiconify();self.root.update_idletasks()
        if self.native:
            self.native.taskbar_window(self.root)
            self.root.after_idle(lambda:self.native.no_activate(self.root,False))
    def queue_save(self):
        if self.applying_display:return
        try:
            x,y,width,height=self.bounds();self.last_bounds=(x,y,width,height)
            self.cached_preferences=dict(layout=dict(x=x,y=y,width=width,height=height,scope=self.scope.get(),metric=self.metric.get()))
            if self.save_job:self.root.after_cancel(self.save_job)
            self.save_job=self.root.after(500,self.flush_preferences)
        except tk.TclError:pass
    def flush_preferences(self):
        if self.save_job:
            try:self.root.after_cancel(self.save_job)
            except tk.TclError:pass
            self.save_job=None
        changes={key:value for key,value in self.cached_preferences.items() if self.saved_preferences.get(key)!=value}
        if self.on_preferences and changes:self.on_preferences(changes);self.saved_preferences.update(changes)
    def apply_snapshot(self,data):
        self.current=data
        interval=data.get('interval_seconds',1)
        if type(interval) in (int,float) and 1<=interval<=5:self.animation_seconds=float(interval)
        revision=data.get('show_revision',0)
        if revision>self.show_revision and self.native:self.native.activate(self.root)
        self.show_revision=revision
        self.state_label.configure(text='Recording' if data.get('active') else 'Ended' if data.get('generation') else 'Waiting');self.render()
    def render(self,force_order=False):
        side={'ally':'Allied','enemy':'Enemy'}.get(self.scope.get());rows=entries_for(self.current,side,self.metric_key)
        context=self.current.get('generation'),self.scope.get(),self.metric_key;x,y=self.root.winfo_pointerxy()
        hold=not force_order and context==self.last_order_context and (self.point_in(self.table.canvas,x,y) or time.monotonic()-self.table.last_scroll<.6)
        if hold:
            order={entry.sample.uid:i for i,entry in enumerate(self.table.rows)};rows.sort(key=lambda entry:order.get(entry.sample.uid,len(order)))
        self.hover_held=hold;self.last_order_context=context
        self.table.columns=((next(label for label,key in COLUMNS if key==self.metric_key),self.metric_key),)
        self.table.set_rows(rows,compact=True,sort_by=self.metric_key,empty_message='Waiting for battle' if not self.current.get('generation') else 'No units',generation=(self.current.get('generation'),self.scope.get()),animation_seconds=self.animation_seconds);self.write_check()
    def write_check(self):
        if not self.check_output:return
        def rect(widget):return dict(x=widget.winfo_rootx(),y=widget.winfo_rooty(),width=widget.winfo_width(),height=widget.winfo_height())
        now=time.monotonic();animated=self.table.transitions.snapshot(now)
        data=dict(errors=self.errors,generation=self.current.get('generation'),scope=self.scope.get(),metric=self.metric_key,topmost=self.topmost.get(),
            alpha=self.root.attributes('-alpha'),background_material='solid',borderless=bool(self.root.overrideredirect()),window=rect(self.root),bars={'Units':rect(self.table.canvas)},animation_duration=self.animation_seconds,animation_active=self.table.transitions.active(now),offset=self.table.offset,
            rows=[dict(id=entry.sample.uid,name=entry.sample.name,side=entry.sample.side,color=unit_bar_color(entry),dimmed=entry.dimmed,damage=entry.damage,healing_budget_remaining_hp=entry.healing_budget_remaining_hp,unlimited=entry.healing_budget_unlimited,y=animated.get((entry.sample.uid,entry.sample.address,entry.sample.result,'rank'),i*self.table.row_height)) for i,entry in enumerate(self.table.rows)],
            controls={name:rect(widget) for name,widget in [('close',self.close_button),('topmost',self.topmost_check),('resize',self.resize_grip),*[('scope_'+key,button) for key,button in self.scope_buttons.items()],*[('metric_'+key,button) for key,button in self.metric_buttons.items()]]},
            painted_rows=[dict(id=self.table.rows[slot['values'][0]].sample.uid,side=self.table.rows[slot['values'][0]].sample.side,color=self.table.canvas.itemcget(slot['items'][1],'fill'),text_color=self.table.canvas.itemcget(slot['items'][2],'fill'),label_item=slot['items'][2],bounds=self.table.canvas.coords(slot['items'][1])) for slot in self.table.pool if slot['values']])
        if self.native:data.update(hwnd=int(self.native.hwnd(self.root)),exstyle=self.native.style(self.root),owner=int(self.native.user.GetWindowLongPtrW(self.native.hwnd(self.root),-8)))
        try:Path(self.check_output).write_text(json.dumps(data,indent=2),encoding='utf-8')
        except OSError:pass
        if not self.check_pending:self.check_pending=True;self.root.after(60,self.check_tick)
    def check_tick(self):self.check_pending=False;self.write_check()
