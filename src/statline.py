"""Full-resolution sampled unit-card values; never derive stats from effect uptime."""
import math

FIELDS=('hp','hp_max','models','models_max','armour','leadership','speed','melee_attack',
        'melee_defence','weapon_strength','charge_bonus','spell_resistance','missile_resistance',
        'fire_resistance','fire_weakness','physical_resistance','ward_save','healing_budget_remaining_hp')


def unit_values(unit):
    values=unit.get('statline')
    return dict(values,healing_budget_remaining_hp=unit.get('healing_budget_remaining_hp')) if isinstance(values,dict) else None


def unit_state(unit,terminal=None):
    state={k:unit.get(k) if isinstance(unit.get(k),bool) else None for k in
        ('alive','routing','shattered','withdrawing','left_battlefield','spawned','healing_budget_unlimited')}
    state['recorded']=True
    budget=unit.get('healing_budget_remaining_hp')
    if not isinstance(unit.get('statline'),dict) and isinstance(budget,(int,float)) and not isinstance(budget,bool) and math.isfinite(budget):
        state['healing_budget_remaining_hp']=budget
    if terminal:state.update(terminal_status=terminal['status'],terminal_hp=terminal['hp'],terminal_models=terminal['models'])
    return state


def snapshot(values):
    if not isinstance(values,dict):return None
    return {k:float(v) if isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) else None for k in FIELDS for v in [values.get(k)]}


class StatlineTimeline:
    MAX_SAMPLES=100000

    def __init__(self,initial=None,initial_state=None):
        self.samples=[]
        self.truncated_from_s=None
        self.baseline=None
        initial=snapshot(initial)
        if initial and any(v is not None for v in initial.values()):self.observe(0,initial,source='deployment',state=initial_state)

    def observe(self,t,values,segment=0,source='first_sample',state=None):
        values=snapshot(values)
        point=dict(t=t,values=values,segment=segment)
        if state is not None:point['state']=dict(state)
        if self.samples and self.samples[-1]['t']==t:self.samples[-1]=point
        elif len(self.samples)<self.MAX_SAMPLES:self.samples.append(point)
        else:
            if self.truncated_from_s is None:self.truncated_from_s=t
            return
        readable=values is not None and any(v is not None for v in values.values())
        # Freeze one observed baseline, including its unknown fields. Paused
        # replacements refine the first tick, never change a deployment base.
        if readable and (self.baseline is None or (
                self.baseline['source']=='first_sample' and self.baseline['t']==t)):
            self.baseline=dict(t=t,source=source,values=dict(values))
            if state is not None:self.baseline['state']=dict(state)

    def summary(self):
        import copy
        return dict(samples=copy.deepcopy(self.samples),baseline=copy.deepcopy(self.baseline),
            truncated_from_s=self.truncated_from_s)
