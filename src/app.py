"""Warhammer III Logger: opt-in live debugging and post-battle reports."""
import argparse
import json
import os
from pathlib import Path
import queue
import sys
from types import SimpleNamespace
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

sys.dont_write_bytecode = True
PROJECT = Path(__file__).resolve().parents[1]
from aggregate import Battle, STATES
from logfile import load_key
from report import convert
from worker import Worker, RATES
from icons import set_app_identity, set_window_icon
from widgets import RankedTable, BG, TEXT, MUTED, GOLD


class App:
    def __init__(self, root, rate=1., pid=None, demo=False):
        self.root, self.demo = root, demo
        self.channel = queue.Queue(maxsize=1)
        self.worker = None if demo else Worker(PROJECT, self.channel, rate, pid)
        self.summary, self.message, self.last_report = None, {}, None
        self.sort_by, self.side, self.closing = 'damage', 'Mine', False
        root.title('Warhammer III Battle Logger')
        set_window_icon(root)
        root.geometry('1180x760')
        root.minsize(960, 640)
        root.configure(background=BG)
        style = ttk.Style(root)
        style.theme_use('clam')
        style.configure('.', background=BG, foreground=TEXT, font=('Segoe UI', 10))
        style.configure('TButton', background='#233244', padding=7)
        style.map('TButton', background=[('active', '#31475c')])
        style.configure('TCheckbutton', background=BG)
        style.configure('TMenubutton', background='#233244', padding=7)
        header = ttk.Frame(root, padding=(18, 14))
        header.pack(fill='x')
        ttk.Label(header, text='Warhammer III Battle Logger', font=('Segoe UI Semibold', 18)).pack(side='left')
        self.rate = tk.DoubleVar(value=rate)
        rates = ttk.Menubutton(header, text='Refresh rate ▾')
        menu = tk.Menu(rates, tearoff=False)
        for value, label in [(1., '1× / second (default)'), (.5, '0.5× / second · every 2s'), (.2, '0.2× / second · every 5s')]:
            menu.add_radiobutton(label=label, variable=self.rate, value=value, command=self.set_rate)
        rates['menu'] = menu
        rates.pack(side='right')
        self.topmost = tk.BooleanVar(value=False)
        self.pin_button = ttk.Button(header, text='Always on top: Off', command=self.toggle_topmost)
        self.pin_button.pack(side='right', padx=8)
        self.status = ttk.Label(root, text='Demo data' if demo else 'Waiting for WARHAMMER III', foreground=GOLD, padding=(20, 0))
        self.status.pack(fill='x')
        toolbar = ttk.Frame(root, padding=(16, 12))
        toolbar.pack(fill='x')
        self.debug = tk.BooleanVar(value=demo)
        ttk.Checkbutton(toolbar, text='Live debug · includes hidden enemies', variable=self.debug, command=self.refresh).pack(side='left')
        self.advanced = tk.BooleanVar(value=False)
        ttk.Checkbutton(toolbar, text='Advanced statistics', variable=self.advanced, command=self.refresh).pack(side='left', padx=12)
        self.finish_button = ttk.Button(toolbar, text='Finish capture', command=self.finish_capture)
        self.finish_button.pack(side='right')
        ttk.Button(toolbar, text='Open report', command=self.open_report).pack(side='right', padx=8)
        self.main = ttk.Panedwindow(root, orient='horizontal')
        self.main.pack(fill='both', expand=True, padx=16, pady=4)
        left, right = ttk.Frame(self.main), ttk.Frame(self.main)
        self.main.add(left, weight=3)
        self.main.add(right, weight=2)
        tabs = ttk.Frame(left)
        tabs.pack(fill='x', pady=(0, 8))
        ttk.Button(tabs, text='My units', command=lambda:self.choose_side('Mine')).pack(side='left')
        ttk.Button(tabs, text='All friendly', command=lambda:self.choose_side('Allied')).pack(side='left', padx=6)
        ttk.Button(tabs, text='Enemy', command=lambda:self.choose_side('Enemy')).pack(side='left', padx=6)
        self.table = RankedTable(left, on_sort=self.choose_sort)
        self.table.pack(fill='both', expand=True)
        self.table.canvas.bind('<Button-1>', lambda e:root.after_idle(self.details), add='+')
        self.detail = tk.Text(right, background='#18212b', foreground=TEXT, relief='flat', wrap='word',
                              font=('Consolas', 10), padx=14, pady=12, width=40)
        scrollbar = ttk.Scrollbar(right, command=self.detail.yview)
        scrollbar.pack(side='right', fill='y')
        self.detail.configure(yscrollcommand=scrollbar.set)
        self.detail.pack(fill='both', expand=True, padx=(12, 0))
        self.perf = ttk.Label(root, text='Prototype · encrypted local capture · read-only game access', foreground=MUTED, padding=(16,10), wraplength=900)
        self.perf.pack(side='bottom', fill='x', before=self.main)
        root.protocol('WM_DELETE_WINDOW', self.close)
        if self.worker: self.worker.start()
        if demo:
            from demo import frames
            b = Battle(dict(started_pacific='Synthetic preview · not an in-game measurement'))
            for frame in frames(16, 20): b.observe(frame)
            self.summary = b.summary()
            self.refresh()
        root.after(100, self.poll)

    def toggle_topmost(self):
        self.topmost.set(not self.topmost.get())
        self.root.attributes('-topmost', self.topmost.get())
        self.pin_button.configure(text='Always on top: '+('On' if self.topmost.get() else 'Off'))

    def set_rate(self):
        if self.worker: self.worker.set_rate(self.rate.get())
        self.refresh()

    def choose_side(self, side):
        self.side = side
        self.refresh()

    def choose_sort(self, key):
        self.sort_by = key
        self.refresh()

    def refresh(self):
        rows = []
        if self.debug.get() and self.summary:
            for row in self.summary['units']:
                last = row['last']
                if self.side == 'Mine':
                    if last.get('controlled') is not True: continue
                elif row['side'] != self.side: continue
                sample = SimpleNamespace(uid=row['id'], address=0, result=0, name=row.get('display_name',row['name']))
                rows.append(SimpleNamespace(sample=sample, damage=last.get('damage'),
                    kills=last.get('kills'), gold_damage=last.get('gold_damage'), dimmed=not row['fresh'] or last.get('alive') is False))
        rows.sort(key=lambda row: (-(getattr(row, self.sort_by) or 0), row.sample.name))
        self.table.set_rows(rows, enemy=self.side=='Enemy', sort_by=self.sort_by,
            generation=self.summary.get('metadata', {}).get('started_pacific') if self.summary else None,
            empty_message='Enable Live debug to inspect captured statistics' if not self.debug.get() else 'Waiting for units')
        if rows and self.table.selected not in {r.sample.uid for r in rows}: self.table.selected = rows[0].sample.uid
        self.details()

    def details(self):
        lines = ['LIVE DEBUG', '']
        row = next((u for u in (self.summary or {}).get('units', []) if u['id']==self.table.selected), None)
        if not self.debug.get():
            lines = ['Recording runs without displaying battle data.', '', 'Enable Live debug for human validation.', 'Enemy debug data can include hidden units.', '', 'Post-battle reports open in a separate browser window.']
        elif row:
            last = row['last']
            lines += [row.get('display_name',row['name']), row['side']+' · '+row['final_status'], '']
            sources = last.get('damage_by_source')
            lines += ['NATIVE HP DAMAGE CREDIT']
            if sources is None:
                lines += ['Unknown · requires a new capture with verified counters.']
            else:
                for category,counts in sources.items():
                    if category in ('charge','melee_collision'): continue
                    if category == 'melee':
                        counts = {r:sum(sources[c][r] for c in ('melee','charge','melee_collision')) for r in ('enemy','ally','self')}
                    label = 'Missiles and spells' if category == 'missile' else category.replace('_',' ')
                    lines.append(label+f": enemy {counts['enemy']:,} / ally {counts['ally']:,} / self {counts['self']:,}")
                lines += ['Native source categories; independent of firing state.', 'Enemy HP credit excludes absorbed barrier damage.']
            lines += ['']
            fmt = lambda v: 'unknown' if v is None else f'{v:,.2f}'
            lines += ['SAMPLED TOTALS', 'Calculated damage taken: '+fmt(row.get('damage_taken_estimate')),
                'Calculated healing received: '+fmt(row.get('healing_received_estimate')),
                f"Rallies observed: {row['rallies_observed']}",
                'Damage while firing*: '+str(row['damage_firing_estimate']),
                'Damage in other states*: '+str(row['damage_other_state_estimate']),
                'Unclassified damage: '+str(row['damage_ambiguous']),
                '* Timing estimates; projectiles can land later.', '', 'TIME IN STATE (simulation seconds)']
            for state in STATES:
                duration, coverage = row['state_seconds'][state], row['state_observed_seconds'][state]
                lines.append(state.replace('_',' ')+': '+(f'{duration:.0f}s / {coverage:.0f}s covered' if coverage else 'unknown'))
            lines += ['', 'CURRENT VALUES']
            for key in ['result_hp','result_models','result_initial_hp','result_initial_models','result_exit_reason','damage','gold_damage','kills','hp_cached','hp_max_cached','models','models_initial','primary_ammo','secondary_ammo','leadership','primary_ammo_fraction','secondary_ammo_fraction','spawned','healing_budget_remaining_hp','healing_budget_remaining_fraction','healing_budget_ceiling_hp','healing_budget_unlimited','healing_ceiling_fraction_raw','regen_base_raw','firing','melee','idle','walking','running','flying','routing','shattered','withdrawing','out_of_opponents_vision']:
                value = last.get(key)
                lines.append(key.replace('_',' ')+': '+('unknown' if value is None else str(round(value, 3)) if isinstance(value,float) else str(value)))
            fatigue=last.get('fatigue_state_native') if last.get('fatigue_state_native') is not None else last.get('fatigue_state')
            names=('Fresh','Active','Winded','Tired','Very tired','Exhausted')
            cap=(self.summary or {}).get('fatigue_rules') or {}
            points=last.get('fatigue_points')
            at_max=points is not None and cap.get('maximum') is not None and points>=cap['maximum']
            lines += ['Fatigue state: '+('Maximum' if at_max else names[fatigue] if isinstance(fatigue,int) and 0<=fatigue<len(names) else 'unknown'),
                'Fatigue points: '+str(last.get('fatigue_points')), '',
                'Base healing budget: 75% of maximum HP. Healing-cap increases multiply that base.',
                '+100% increased healing cap gives 150% of maximum HP as healing budget.',
                'The healing ceiling is current HP + remaining healing budget.',
                'Healing received above is calculated; no native incoming-healing counter is bound.', 'Projectile credit includes some spells and breath attacks']
            if self.advanced.get():
                lines += ['', 'ADVANCED OBSERVATIONS',
                          'Observed net HP drops: '+str(row['observed_hp_drops']),
                          'Observed net HP rises: '+str(row['observed_hp_rises']),
                          'Raw morale state: '+str(last.get('morale_state'))]
                for field in ('hp_max_cached','models_initial'):
                    known=row['last_observed'].get(field)
                    if known:
                        lines.append(f"Last observed {field}: {known['value']} at {known['sim_s']:.0f}s")
            if self.summary:
                lines += ['', 'WINDS (each army)']
                for a in self.summary['armies']:
                    a=a['last']; lines.append(f"{a['side']}: {a.get('current')} power / {a.get('reserve')} reserve")
                    interval=a.get('recharge_seconds_per_point')
                    lines.append('  Recharge: '+fmt(a.get('recharge_per_second'))+' Winds/s · '+('unknown' if interval is None else f'{interval:.0f}')+'s/point')
                lines += ['', 'Fields require live validation.', 'Net changes omit simultaneous damage/healing.', 'Missing data is not zero.']
        selected = row['id'] if row and self.debug.get() else None
        scroll = self.detail.yview()[0] if selected == getattr(self, 'detail_unit', None) else 0
        self.detail_unit = selected
        self.detail.configure(state='normal')
        self.detail.delete('1.0','end')
        self.detail.insert('1.0','\n'.join(lines))
        self.detail.yview_moveto(scroll)
        self.detail.configure(state='disabled')

    def poll(self):
        try:
            while True:
                self.message = self.channel.get_nowait()
                self.summary = self.message['summary']
                self.status.configure(text=self.message['status'])
                for report in self.message['reports']:
                    if report['report']: self.last_report = report['report']
                errors = [r['error'] for r in self.message['reports'] if r['error']]
                stats = self.message['stats']
                if errors: self.status.configure(text='Saving error: '+errors[-1])
                self.perf.configure(text=f"{self.rate.get():g} samples/s · read {stats.get('read_ms',0):.2f} ms · "
                    f"{stats.get('read_calls',0)} reads · RAM {stats.get('working_set_mib') or 0:.1f} MiB · "
                    f"CPU {stats.get('cpu_window_percent') or 0:.1f}% of one logical core · "
                    f"dropped records {sum(r['dropped'] for r in self.message['reports'])}")
                self.finish_button.configure(state='normal' if self.message['recording'] else 'disabled')
                self.refresh()
        except queue.Empty:
            pass
        if self.closing and (not self.worker or not self.worker.is_alive()): self.root.destroy(); return
        self.root.after(100, self.poll)

    def finish_capture(self):
        if self.worker: self.worker.finish_event.set()

    def open_report(self):
        if self.last_report:
            os.startfile(self.last_report)
            return
        path = filedialog.askopenfilename(initialdir=PROJECT/'captures', filetypes=[('Battle log','*.wh3log'), ('Report','*.html')])
        if not path: return
        if Path(path).suffix == '.html': os.startfile(path); return
        try:
            keypath = PROJECT/'captures/logger.key'
            if not keypath.exists():
                selected = filedialog.askopenfilename(title='Select the logger key', filetypes=[('Logger key','*.key')])
                if not selected: return
                keypath = Path(selected)
            output = convert(path, load_key(keypath))
            self.last_report = str(output)
            os.startfile(str(output))
        except Exception as error:
            messagebox.showerror('Cannot open report', str(error))

    def close(self):
        self.closing = True
        self.status.configure(text='Saving capture and report…')
        if self.worker: self.worker.stop_event.set()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--rate', type=float, choices=RATES, default=1.)
    parser.add_argument('--pid', type=int)
    parser.add_argument('--demo', action='store_true')
    args = parser.parse_args()
    set_app_identity('debug')
    root = tk.Tk()
    App(root, args.rate, args.pid, args.demo)
    root.mainloop()


if __name__ == '__main__': main()
