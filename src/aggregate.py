"""Provider-neutral aggregation: no native addresses or Tk requirements."""
import copy
import math
from damage_taken import DamageTaken
from terminal_result import resolve

STATES = ('firing', 'melee', 'idle', 'walking', 'running', 'flying', 'grounded', 'routing', 'shattered', 'withdrawing', 'under_missile', 'out_of_opponents_vision', 'retreating_combined', 'idle_after_rally')
HISTORY = ('hp_cached', 'hp_max_cached', 'models', 'damage', 'gold_damage', 'barrier_hp',
           'primary_ammo_fraction', 'secondary_ammo_fraction', 'morale_state', 'fatigue_state',
           'healing_ceiling_fraction_raw', 'regen_base_raw', 'xyz', 'damage_by_source',
           'healing_budget_remaining_hp', 'healing_budget_unlimited',
           'healing_budget_ceiling_hp', 'healing_budget_remaining_fraction',
           'primary_ammo', 'secondary_ammo', 'primary_ammo_max', 'secondary_ammo_max', 'leadership', 'fatigue_points','fatigue_state_native')
UNSUPPORTED = {
    'charge_time': 'No verified charging field in the bounded lookup.',
    'healing_applied': 'Healing received is calculated from HP + calculated damage taken - starting maximum HP, only with a full-health baseline. With the ceiling-based damage calculation it equals budget spent, not an independent actual-healing measurement.',
    'exact_damage_taken': 'Calculated damage taken uses the initial minus current unclamped healing ceiling. It assumes healing spends an equal budget; scripted healing without budget spending, capacity/max-HP changes and transformations can invalidate it. It is not a native incoming-damage counter.',
    'healing_cap_legacy': 'The native remaining healing budget is read directly for all model counts. The clamped UI ceiling is retained separately.',
    'winds_generated_and_spent': 'Pool changes conflate generation, drainage and spending. Recharge transfers reserves to power.',
    'ability_use_and_cooldown': 'Known scripting interfaces; native ability list has not been bound.',
    'damage_by_effect': 'Effect uptime and configured damage do not prove actual damage taken.',
    'friendly_fire_kills': 'Friendly/self HP damage categories are supported; friendly kills are not yet bound.',
    'attacker_target_damage_matrix': 'Native per-opponent history mixes incoming/outgoing damage, rotates and prunes. It is not a directional lifetime ledger.',
    'orders_per_minute': 'Target changes do not count repeated or cancelled commands.',
    'unit_cost_and_efficiency': 'Exact battle purchase value is not bound natively. Trade uses a manual/captured value, or the report default of 500 gold per character level for lords/heroes (level 1 assumed if missing), otherwise an unambiguous base multiplayer database price. Native gold damage is unchanged.',
    'wavering_crumbling_unstable': 'Raw morale enum logged; native enum meanings and effect lists need verification.',
    'limbering_climbing_working_ready': 'No verified fields here; limbering is not folded into walking.',
    'victory_and_result_boundary': 'Victory/defeat/draw is read only when the native results phase is observed. Victory countdown and pursuit boundaries are not bound; an early capture end leaves the outcome unknown.',
}


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


class Series:
    """Bound memory using progressively coarser samples, retaining first and latest."""
    def __init__(self, limit=240):
        self.points, self.stride, self.seen, self.limit = [], 1, 0, limit

    def add(self, point):
        if self.points and self.points[-1]['t'] == point['t']:
            self.points[-1] = point
            return
        self.seen += 1
        if self.seen % self.stride == 0 or not self.points:
            self.points.append(point)
        elif len(self.points) > 1:
            self.points[-1] = point
        if len(self.points) > self.limit:
            self.points = self.points[::2] + [self.points[-1]]
            self.stride *= 2


class Battle:
    MAX_UNITS = 4096

    def __init__(self, metadata=None, keep_history=True, max_gap=2.0):
        self.metadata = metadata or {}
        self.units, self.armies = {}, {}
        self.previous_t, self.start_t, self.end_t = None, None, None
        self.samples, self.gaps, self.unreadable, self.missing_clock, self.paused_samples = 0, 0, 0, 0, 0
        self.elevation_min = None
        self.movement_bounds = None
        self.battle_result = None
        self.initial_units, self.initial_armies = {}, {}
        self.fatigue_rules = None
        self.keep_history, self.max_gap = keep_history, max_gap
        self.performance = dict(read_ms_total=0., read_ms_max=0., calls_total=0, bytes_total=0, working_set_mib_max=0.)

    def observe(self, frame):
        if frame.get('schema') != 1 or frame.get('kind') != 'sample': raise ValueError('Unsupported sample schema.')
        if frame.get('gap_before'):
            self.break_continuity()
        t = frame.get('sim_s')
        if not number(t):
            self.missing_clock += 1
            self.break_continuity()
            return
        if self.previous_t is not None and t < self.previous_t: raise ValueError('Battle clock moved backwards; start a new battle.')
        dt = t - self.previous_t if self.previous_t is not None else 0
        if dt == 0 and self.previous_t is not None: self.paused_samples += 1
        if dt > self.max_gap: self.gaps += 1
        continuous = 0 < dt <= self.max_gap
        if self.start_t is None: self.start_t = t
        self.end_t = t
        baseline = frame.get('deployment_baseline')
        if self.samples == 0 and baseline:
            self.initial_units = {str(u['id']):copy.deepcopy(u) for u in baseline.get('units', [])}
            self.initial_armies = {str(a['id']):copy.deepcopy(a) for a in baseline.get('armies', [])}
        for field in ('battle_result','fatigue_rules'):
            if frame.get(field) is not None:
                if (field=='battle_result' and self.battle_result and self.battle_result.get('result_type_confirmed')
                        and not frame[field].get('result_type_confirmed')
                        and frame[field].get('outcome')==self.battle_result.get('outcome')):
                    continue  # Keep the last coherent classification through teardown.
                setattr(self,field,dict(copy.deepcopy(frame[field]),observed_s=t))
        self.samples += 1
        self.unreadable += frame.get('unreadable_units', 0)
        perf = frame.get('performance', {})
        p = self.performance
        p['read_ms_total'] += perf.get('read_ms', 0)
        p['read_ms_max'] = max(p['read_ms_max'], perf.get('read_ms', 0))
        p['calls_total'] += perf.get('read_calls', 0)
        p['bytes_total'] += perf.get('bytes_read', 0)
        p['working_set_mib_max'] = max(p['working_set_mib_max'], perf.get('working_set_mib') or 0)
        present = set()
        for unit in frame['units']:
            unit = dict(unit)
            # Revisions <=6 forced these zeros from IsAlive=false, even when
            # the combat cache was unavailable. They are not measurements.
            if self.metadata.get('source')=='external-native' and self.metadata.get('collector_revision',0)<=6 and unit.get('alive') is False:
                for key in ('hp_cached','models','healing_budget_ceiling_hp'): unit[key]=None
            flags = [unit.get(k) for k in ('awaiting_order_after_rally_raw','idle','alive','routing','shattered','withdrawing')]
            unit['idle_after_rally'] = (flags[0] and flags[1] and flags[2] and not any(flags[3:])) if all(isinstance(f,bool) for f in flags) else None
            retreat = [unit.get(k) for k in ('routing','shattered','withdrawing')]
            unit['retreating_combined'] = True if any(v is True for v in retreat) else False if all(v is False for v in retreat) else None
            uid = str(unit['id'])
            if uid in present: raise ValueError('Duplicate unit identity in sample.')
            present.add(uid)
            if uid not in self.units:
                if len(self.units) >= self.MAX_UNITS: raise ValueError('Battle unit retention limit reached.')
                initial = self.initial_units.get(uid)
                first = dict(unit, **{k:v for k,v in (initial or {}).items() if v is not None})
                self.units[uid] = dict(id=uid, name=unit['name'], side=unit['side'], army=unit['army'],
                    first_s=t, last_s=t, first=copy.deepcopy(first), last={}, previous=None,
                    initial_values_source='deployment' if initial else 'first_combat_observation',
                    state_seconds={s:0. for s in STATES}, state_observed_seconds={s:0. for s in STATES},
                    damage_firing_estimate=0,
                    damage_other_state_estimate=0, damage_ambiguous=0, counter_resets=0,
                    observed_hp_drops=0., observed_hp_rises=0.,
                    observed_barrier_drops=0., observed_barrier_rises=0.,
                    rallies_observed=0, landings_observed=0, missing_samples=0, fresh=True,
                    last_observed={}, damage_source_mismatches=0, last_damage_calculation=None,
                    initial_models_observed=None, initial_models_maximum=None, fatigue_points_peak=None,
                    ever_flying=False, ammo={}, taken_estimator=DamageTaken(), history_segment=0, position_segment=0,
                    history=Series() if self.keep_history else None)
                if initial:
                    row = self.units[uid]
                    row['taken_estimator'].observe(t,initial)
                    row['initial_models_observed'] = initial.get('models')
                    row['initial_models_maximum'] = initial.get('models_initial')
                    for pool in ('primary','secondary'):
                        current = initial.get(pool+'_ammo')
                        if number(current) and current >= 0:
                            row['ammo'][pool] = dict(initial=current,initial_s=t,initial_source='deployment',increase_observed=False)
            row = self.units[uid]
            if unit.get('flying') is True: row['ever_flying'] = True
            for pool in ('primary','secondary'):
                current = unit.get(pool+'_ammo')
                if number(current) and current >= 0:
                    start = unit.get(pool+'_ammo_start')
                    native_start = number(start) and start >= 0 and (start > 0 or current == 0)
                    a = row['ammo'].setdefault(pool,dict(initial=start if native_start else current,initial_s=t,
                        initial_source='native_start' if native_start else 'first_observed',increase_observed=False))
                    if native_start and a['initial_source'] == 'first_observed':
                        a.update(initial=start,initial_source='native_start')
                    if current > a.get('final',current): a['increase_observed'] = True
                    a.update(final=current,final_s=t,expended=a['initial']-current if current <= a['initial'] else None)
            if number(unit.get('fatigue_points')):
                row['fatigue_points_peak'] = max(row['fatigue_points_peak'] or 0,unit['fatigue_points'])
            if row['initial_models_observed'] is None and number(unit.get('models')):
                row['initial_models_observed']=unit['models']
                row['initial_models_maximum']=unit.get('models_initial')
            xyz = unit.get('xyz')
            if isinstance(xyz,(list,tuple)) and len(xyz)==3 and all(number(v) for v in xyz):
                self.elevation_min = min(self.elevation_min,xyz[1]) if self.elevation_min is not None else xyz[1]
                if self.movement_bounds is None:
                    self.movement_bounds = dict(xmin=xyz[0], xmax=xyz[0], zmin=xyz[2], zmax=xyz[2])
                else:
                    for key, value, operation in (('xmin',xyz[0],min), ('xmax',xyz[0],max),
                                                   ('zmin',xyz[2],min), ('zmax',xyz[2],max)):
                        self.movement_bounds[key] = operation(self.movement_bounds[key], value)
            terminal, candidate = resolve(unit,row.get('_terminal_candidate') if dt <= self.max_gap else None,t)
            row['_terminal_candidate'] = candidate
            row['terminal_result'] = terminal
            effective = dict(unit)
            if terminal:
                effective.update(hp_cached=terminal['hp'],models=terminal['models'])
                budget = effective.get('healing_budget_remaining_hp')
                if number(budget): effective['healing_budget_ceiling_hp'] = terminal['hp']+budget
            row['taken_estimator'].observe(t, effective)
            if number(row['taken_estimator'].amount): row['last_damage_calculation']=row['taken_estimator'].summary()
            if unit.get('damage_sources_consistent') is False:
                row['damage_source_mismatches'] += 1
            for field in (*HISTORY, 'models_initial', 'barrier_max', 'unit_gold_value', 'unit_key', 'portrait_path',
                          'character_level', 'has_character_rank', 'left_battlefield'):
                if unit.get(field) is not None:
                    row['last_observed'][field] = dict(value=copy.deepcopy(unit[field]), sim_s=t)
            previous = row['previous']
            if previous is None or (dt > 0 and not continuous):
                row['history_segment'] += 1
            if previous is None or (dt > 0 and not continuous) or previous.get('xyz') is None or unit.get('xyz') is None:
                row['position_segment'] += 1
            if previous and continuous:
                for s in STATES:
                    if isinstance(previous.get(s), bool) and isinstance(unit.get(s), bool):
                        row['state_observed_seconds'][s] += dt
                        if previous[s]: row['state_seconds'][s] += dt
                if (previous.get('routing') is True and unit.get('routing') is False and unit.get('alive') is True
                        and unit.get('shattered') is not True and unit.get('withdrawing') is not True):
                    row['rallies_observed'] += 1
                if previous.get('flying') is True and unit.get('flying') is False and unit.get('alive') is True:
                    row['landings_observed'] += 1
                for field, falls, rises in [('hp_cached','observed_hp_drops','observed_hp_rises'),
                    ('barrier_hp','observed_barrier_drops','observed_barrier_rises')]:
                    if number(previous.get(field)) and number(unit.get(field)):
                        change = unit[field] - previous[field]
                        row[rises if change > 0 else falls] += abs(change)
            if previous and number(previous.get('damage')) and number(unit.get('damage')):
                delta = unit['damage'] - previous['damage']
                if delta < 0: row['counter_resets'] += 1
                elif continuous and previous.get('firing') is True and unit.get('firing') is True:
                    row['damage_firing_estimate'] += delta
                elif continuous and previous.get('firing') is False and unit.get('firing') is False:
                    row['damage_other_state_estimate'] += delta
                else: row['damage_ambiguous'] += delta
            row.update(last=copy.deepcopy(unit), previous=copy.deepcopy(unit), last_s=t, fresh=True)
            if row['history']:
                row['history'].add(dict(t=t, segment=row['history_segment'], position_segment=row['position_segment'],
                                       **{k:unit.get(k) for k in HISTORY},
                                       resolved_hp=terminal['hp'] if terminal else None,
                                       resolved_models=terminal['models'] if terminal else None,
                                       **{pool+'_ammo_expended':row['ammo'].get(pool,{}).get('expended') if number(unit.get(pool+'_ammo')) else None for pool in ('primary','secondary')},
                                       damage_taken_estimate=row['taken_estimator'].amount,
                                       healing_received_estimate=row['taken_estimator'].healing))
        for uid, row in self.units.items():
            if uid not in present:
                row.update(fresh=False, previous=None, _terminal_candidate=None)
                row['missing_samples'] += 1
        for army in frame.get('armies', []):
            key = str(army['id'])
            if key not in self.armies:
                self.armies[key] = dict(first=copy.deepcopy(self.initial_armies.get(key,army)), last={}, last_s=None, segment=0,
                                       history=Series() if self.keep_history else None)
            row = self.armies[key]
            new_segment = self.previous_t is None or (dt > 0 and not continuous) or row['last_s'] != self.previous_t
            if new_segment:
                row['segment'] += 1
            row['last'] = copy.deepcopy(army)
            row['last_s'] = t
            if row['history']: row['history'].add(dict(t=t, segment=row['segment'], **army))
        self.previous_t = t

    def break_continuity(self):
        for row in self.units.values():
            row.update(previous=None, fresh=False, _terminal_candidate=None)
        self.previous_t = None
        self.gaps += 1

    def summary(self):
        rows = []
        for row in self.units.values():
            item = {k:copy.deepcopy(v) for k,v in row.items() if k not in ('history', 'previous', 'taken_estimator','last_damage_calculation','_terminal_candidate')}
            item.update(row['taken_estimator'].summary())
            terminal=row['last'].get('alive') is False or row['last'].get('left_battlefield') is True
            if terminal and item['damage_taken_estimate'] is None and not row['taken_estimator'].invalid and row['last_damage_calculation']:
                item.update(copy.deepcopy(row['last_damage_calculation']))
                item['damage_taken_calculation']['reason']+=' Last valid calculation before the unit became inactive; final HP was not recorded.'
            item['history'] = row['history'].points if row['history'] else []
            last, first = item['last'], item['first']
            span = item['last_s'] - item['first_s']
            item['damage_since_attach'] = max(0,last['damage']-first['damage']) if number(last.get('damage')) and number(first.get('damage')) and not item['counter_resets'] else None
            if item['damage_since_attach'] is not None:
                item['damage_ambiguous'] = max(0,item['damage_since_attach']-item['damage_firing_estimate']-item['damage_other_state_estimate'])
            item['dps_since_attach'] = item['damage_since_attach']/span if item['damage_since_attach'] is not None and span > 0 else None
            item['final_status'] = (item['terminal_result']['status'] if item.get('terminal_result') else 'Dead / retreated' if last.get('alive') is False or last.get('left_battlefield') is True or item['last_observed'].get('left_battlefield',{}).get('value') is True else
                'Last observed / missing' if not item['fresh'] else
                'Shattered' if last.get('shattered') is True else
                'Withdrawing' if last.get('withdrawing') is True else 'Routing' if last.get('routing') is True else
                'Alive' if last.get('alive') is True else 'Unknown')
            rows.append(item)
        armies = [dict(first=r['first'], last=r['last'], history=r['history'].points if r['history'] else []) for r in self.armies.values()]
        name_counts, name_indices = {}, {}
        for item in rows:
            key = item['side'], item['name']
            name_counts[key] = name_counts.get(key,0)+1
        for item in rows:
            key = item['side'], item['name']
            name_indices[key] = name_indices.get(key,0)+1
            item['display_name'] = item['name']+(f" #{name_indices[key]}" if name_counts[key]>1 else '')
        return dict(schema=1, metadata=self.metadata, start_s=self.start_t, end_s=self.end_t,
            samples=self.samples, gaps=self.gaps, unreadable_units=self.unreadable, missing_clock=self.missing_clock,
            paused_samples=self.paused_samples, elevation_min=self.elevation_min,
            movement_bounds=self.movement_bounds.copy() if self.movement_bounds else None,
            battle_result=copy.deepcopy(self.battle_result),fatigue_rules=copy.deepcopy(self.fatigue_rules),
            units=rows, armies=armies, unsupported=UNSUPPORTED,
            performance=dict(self.performance, read_ms_average=self.performance['read_ms_total']/max(1,self.samples)),
            caveats=['Cached fields need in-game validation, including hidden units and multi-model healing.',
                'State durations and paths are sampled estimates; simultaneous states overlap.',
                'Firing versus other-state damage is timing-based, not a verified ranged/melee split.',
                'Ammo expended compares beginning and ending ammo only. Replenishment is not separately accounted for. Ammo lost with models, if removed from the pool, cannot be distinguished from firing; the tracked pool can also retain ammo after casualties.',
                'Logging can start late and end before the final native updates. Missing rows are not proof of death.',
                'Winner requires an observed native results phase; capture end alone does not establish an outcome.'])
