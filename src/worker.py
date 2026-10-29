"""Native reader -> neutral samples -> recorder, with independent live preview."""
import datetime as dt
from pathlib import Path
import queue
import threading
import time
import uuid
from battle_names import unique_capture_path
from aggregate import Battle
from aggregate import number
from combat_window import CombatWindow
from logfile import load_key
from memory import WindowsAPI, ProcessMemory, ReadError, UnsupportedBuild, select_profile, load_profiles
from native_reader import LoggerReader
from recorder import Recorder
from resources import ResourceMonitor, pacific
from paths import resource_path

RATES = (1.0, .5, .2)


def latest_put(channel, value):
    try: channel.put_nowait(value)
    except queue.Full:
        try: channel.get_nowait()
        except queue.Empty: pass
        channel.put_nowait(value)


class Worker(threading.Thread):
    def __init__(self, root, channel, rate=1.0, pid=None, preview=True):
        super().__init__(name='battle-logger-reader', daemon=False)
        self.root, self.channel, self.requested_pid = Path(root), channel, pid
        self.preview = preview
        self.set_rate(rate)
        self.stop_event, self.finish_event = threading.Event(), threading.Event()
        self.memory = self.reader = self.token = self.battle = self.recorder = None
        self.suppressed = None
        self.recorders = []
        self.recorders_lock = threading.Lock()
        self.monitor, self.stats = ResourceMonitor() if preview else None, {}
        self.last_frame_t = None
        self.combat_window, self.window_identity = CombatWindow(), None
        self.status = 'Waiting for WARHAMMER III'
        self.late_start_request = None
        self.late_start_answers = queue.Queue()
        self.late_start_allowed = None
        self.last_unit_data = None
        self.data_timeout = 30.

    def answer_late_start(self, request, accepted):
        self.late_start_answers.put((request, bool(accepted)))

    def allow_start(self, identity, frame):
        """Keep reading while the UI asks; create no capture before consent."""
        if identity == self.suppressed: return False
        if self.combat_window.started or self.combat_window.baseline is not None:
            self.late_start_request = None
            if frame.get('battle_phase') in (0,4):self.late_start_allowed=None
            return True
        if frame.get('battle_phase') not in (5,6,7) or not number(frame.get('sim_s')):
            self.late_start_request = None
            return True
        if self.late_start_allowed == identity: return True
        if self.late_start_request != identity: self.late_start_request = identity
        while True:
            try: request, accepted = self.late_start_answers.get_nowait()
            except queue.Empty: break
            if request != identity: continue
            self.late_start_request = None
            if accepted:
                self.late_start_allowed = identity
                return True
            self.suppressed = identity
            return False
        return False

    def unit_data_missing(self, now, detail):
        if not self.recorder: return
        self.battle.break_continuity()
        self.recorder.submit(dict(kind='gap', detail=detail))
        if self.last_unit_data is not None and now-self.last_unit_data >= self.data_timeout:
            identity=self.window_identity
            self.finish('unit_data_timeout')
            self.suppressed=identity
            self.status='Unit data stopped · saving recording; waiting for next battle'

    def set_rate(self, rate):
        if rate not in RATES: raise ValueError('Refresh rate must be 1, 0.5 or 0.2 samples per second.')
        self.rate, self.interval = rate, 1 / rate

    def publish(self):
        summary = self.battle.summary() if self.preview and self.battle else None
        reports = [dict(path=str(r.path), report=str(r.report_path) if r.report_path else None,
            done=r.done.is_set(), error=r.error, dropped=r.dropped) for r in self.recorders[-10:]]
        latest_put(self.channel, dict(status=self.status, summary=summary, stats=dict(self.stats),
                                      reports=reports, recording=self.recorder is not None,
                                      late_start_request=self.late_start_request))

    def finish(self, reason):
        if self.recorder:
            footer=dict(reason=reason, first_s=self.battle.start_t, last_s=self.battle.end_t,
                rate_at_end=self.rate, cached_fields_live_validated=False)
            if self.preview:footer.update(wall_seconds=time.monotonic()-self.wall_start,process_cpu_seconds=time.process_time()-self.cpu_start)
            self.recorder.finish(footer)
            self.recorder = None
        self.token = None
        self.last_frame_t = None
        self.last_unit_data = None
        self.late_start_request = None

    def detach(self):
        if self.memory: self.memory.close()
        self.memory = self.reader = None

    def run(self):
        try:
            api = WindowsAPI()
            profiles = load_profiles(resource_path('profiles'))
            key = load_key(self.root / 'captures/logger.key', create=True)
            while not self.stop_event.is_set():
                started = time.monotonic()
                try:
                    if self.memory and not self.memory.alive():
                        self.finish('game_process_exit')
                        self.detach()
                    if self.memory is None:
                        pids = api.game_pids()
                        if self.requested_pid: pids = [p for p in pids if p == self.requested_pid]
                        if len(pids) != 1:
                            self.status = 'Waiting for WARHAMMER III' if not pids else 'More than one game is running; use --pid.'
                            self.publish()
                            self.stop_event.wait(1)
                            continue
                        module = api.game_module(pids[0])
                        self.memory = ProcessMemory(api, pids[0])
                        profile = select_profile(self.memory, module, profiles)
                        self.profile = profile
                        self.reader = LoggerReader(self.memory, module, profile)
                    if self.preview:calls, size = self.memory.calls, self.memory.bytes_read
                    before = time.perf_counter() if self.preview else None
                    sample = self.reader.sample()
                    frame = self.reader.normalized(sample)
                    if self.preview:self.stats = dict(self.monitor.sample(), read_ms=(time.perf_counter()-before)*1000,
                        read_calls=self.memory.calls-calls, bytes_read=self.memory.bytes_read-size, rate=self.rate)
                    if frame is None:
                        self.finish_event.clear()
                        self.finish('battle_roster_unavailable')
                        self.suppressed = None
                        self.combat_window, self.window_identity = CombatWindow(), None
                        self.late_start_request = self.late_start_allowed = None
                        self.status = 'Post-battle' if self.battle else 'Waiting for battle'
                    else:
                        t = frame['sim_s']
                        identity = (self.memory.pid, sample.token, sample.controller)
                        if identity != self.window_identity:
                            self.finish('battle_identity_changed')
                            self.combat_window, self.window_identity = CombatWindow(), identity
                            self.late_start_request = self.late_start_allowed = None
                        if self.finish_event.is_set():
                            self.finish_event.clear()
                            self.finish('user_finished_capture')
                            self.suppressed = identity
                        if frame.get('battle_phase') in (0,4) and self.recorder:
                            self.finish('returned_to_deployment')
                        rollback = self.last_frame_t is not None and t is not None and t < self.last_frame_t
                        if rollback:
                            self.finish('battle_clock_changed')
                            self.combat_window = CombatWindow()
                            self.late_start_request = self.late_start_allowed = None
                        if not frame.get('units') or not number(t):
                            self.status='Waiting for readable unit data'
                            self.unit_data_missing(time.monotonic(),'No readable units or battle clock')
                            self.publish()
                            self.stop_event.wait(max(.01,self.interval-(time.monotonic()-started)))
                            continue
                        if not self.allow_start(identity,frame):
                            self.status=('Battle discarded · waiting for next battle' if identity == self.suppressed else
                                'Battle already in progress · waiting for your choice')
                            self.publish()
                            self.stop_event.wait(max(.01,self.interval-(time.monotonic()-started)))
                            continue
                        frame = self.combat_window.accept(frame)
                        if frame is None:
                            if self.combat_window.baseline and identity != self.suppressed: self.battle = None
                            self.status = ('Capture finished · waiting for next battle' if identity == self.suppressed else
                                'Deployment · initial values ready; waiting for combat' if self.combat_window.baseline else
                                'Waiting for combat phase')
                            self.publish()
                            self.stop_event.wait(max(.01,self.interval-(time.monotonic()-started)))
                            continue
                        if identity != self.token or rollback:
                            if self.recorder: self.finish('battle_identity_or_clock_changed')
                            if identity != self.suppressed or rollback:
                                now = pacific(dt.datetime.now(dt.timezone.utc))
                                path = unique_capture_path(self.root,'battle-'+now.strftime('%Y%m%d-%H%M%S'))
                                metadata = dict(started_pacific=now.strftime('%Y-%m-%d %H:%M:%S %Z'),
                                    build=self.profile['name'], source='external-native', refresh_hz=self.rate,
                                    maximum_interval_s=80, debug_visibility='full_enemy_collection', schema=1)
                                metadata['started_mid_battle'] = self.late_start_allowed == identity
                                metadata.update(collector_revision=17,capabilities=['coalesced_paused_samples','sampled_unit_statline','effect_instances_and_intensity','configured_effect_damage_scale','native_battle_ui_clock','sampled_active_effects','battle_time_effect_ticks','native_result_type','native_combat_boundary','deployment_initial_values','native_fatigue_pair','native_starting_ammo','ammo_net_expended','retreat_state_union','native_result_health_and_exit','native_damage_by_source','friendly_self_hp_damage','explicit_winds_rate_units','native_healing_budget','flat_ammo','signed_leadership','unit_type_key','unit_portrait_path','fatigue_points_and_rules','character_level','native_results_phase','left_battlefield','rally_wait_raw'])
                                self.battle = Battle(metadata, keep_history=False, max_gap=80)
                                if self.preview:self.wall_start, self.cpu_start = time.monotonic(), time.process_time()
                                with self.recorders_lock:
                                    self.recorder = Recorder(path, key, metadata,diagnostics=self.preview)
                                    running = [r for r in self.recorders if not r.done.is_set()]
                                    finished = [r for r in self.recorders if r.done.is_set()][-9:]
                                    self.recorders = finished + running
                                    self.recorders.append(self.recorder)
                                self.token, self.suppressed = identity, None
                                self.last_frame_t = None
                        self.last_frame_t = t
                        if self.preview:frame['performance'] = self.stats
                        if self.recorder:
                            # A paused but readable frame is still a healthy stream.
                            self.last_unit_data = time.monotonic()
                            self.battle.observe(frame)
                            # The recorder coalesces equal timestamps to their latest state.
                            self.recorder.submit(frame)
                            self.status = 'In battle · recording'
                            if self.recorder.error: self.status = 'Recording error: '+self.recorder.error
                            elif self.recorder.limit_reached: self.status = 'Capture size limit reached; finish and save.'
                        else: self.status = 'Capture finished · waiting for next battle'
                    self.publish()
                except UnsupportedBuild as error:
                    self.status = str(error)
                    self.detach()
                    self.publish()
                    self.stop_event.wait(5)
                except (ReadError, OSError, ValueError) as error:
                    self.status = 'Unavailable · '+str(error)
                    self.unit_data_missing(time.monotonic(),str(error))
                    if self.reader is None: self.detach()
                    self.publish()
                # Polling cadence is wall time; all durations use the game clock.
                self.stop_event.wait(max(.01, self.interval-(time.monotonic()-started)))
        except Exception as error:
            self.status = 'Logger error: '+str(error)
            self.publish()
        finally:
            self.finish('logger_closed')
            self.detach()
            for recorder in self.recorders:
                if recorder.is_alive(): recorder.join()
            self.publish()
