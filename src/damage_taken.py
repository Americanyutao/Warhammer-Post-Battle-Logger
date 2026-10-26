"""Ceiling-difference damage estimate, independent of the native collector.

C = current HP + remaining healing budget. Budget-spending healing leaves C
unchanged; damage lowers it. Scripted healing without budget spending, maximum
HP changes and budget modifiers break that conservation assumption.
HP is cached separately from the native budget, so small timing/rounding
fluctuations are possible. These are estimates, not incoming/healing events.
"""
import math


def valid(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


class DamageTaken:
    def __init__(self):
        self.basis = None
        self.previous_budget = None
        self.invalid = None
        self.amount = self.fraction = self.ceiling = self.as_of = self.healing = self.remaining_budget = None
        self.reason = 'Waiting for an initial healing ceiling.'

    def observe(self, t, unit):
        self.amount = self.fraction = self.ceiling = self.as_of = self.healing = self.remaining_budget = None
        if unit.get('healing_budget_unlimited') is True:
            self.invalid = 'Healing budget is unlimited; budget spending cannot offset healing.'
        if self.invalid:
            self.reason = self.invalid
            return
        hp, budget, maximum = (unit.get(k) for k in ('hp_cached', 'healing_budget_remaining_hp', 'hp_max_cached'))
        # Capacity observations still matter when the UI HP cache is missing.
        if self.basis:
            if valid(budget):
                if self.previous_budget is not None and budget > self.previous_budget:
                    self.invalid = 'Remaining healing budget increased; the initial ceiling is no longer comparable.'
                self.previous_budget = budget
            reference = self.basis['maximum_hp']
            if valid(maximum) and maximum > 0 and reference is not None and maximum != reference:
                self.invalid = 'Maximum HP changed; the initial healing ceiling is no longer comparable.'
            if self.basis['method'] == 'single_entity_display_fraction' and valid(unit.get('models_initial')) and unit['models_initial'] > 1:
                self.invalid = 'Unit became multi-model; its legacy displayed healing ceiling is clamped.'
            if self.invalid:
                self.reason = self.invalid
                return
        method = None
        if valid(hp) and valid(budget):
            ceiling, method = hp + budget, 'hp_plus_remaining_budget'
            self.previous_budget = budget
        elif not any(k in unit for k in ('healing_budget_remaining_hp', 'healing_budget_unlimited')):
            # Older logs have only the displayed fraction. It is usable for
            # single entities; the extra multi-model UI clamp cannot be undone.
            fraction = unit.get('healing_ceiling_fraction_raw')
            if unit.get('models_initial') == 1 and valid(fraction) and valid(maximum) and maximum > 0:
                ceiling, method = fraction * maximum, 'single_entity_display_fraction'
        if method is None:
            self.reason = 'Current unclamped healing ceiling unavailable; legacy multi-model display fractions are not comparable.'
            return
        if self.basis is None:
            summoned = unit.get('spawned') is True
            if summoned and not (valid(maximum) and maximum > 0):
                self.reason = 'Waiting for summon maximum HP to apply the assumed 1.75 starting ceiling.'
                return
            self.basis = dict(sim_s=t, ceiling_hp=1.75 * maximum if summoned else ceiling,
                hp=maximum if summoned else hp if valid(hp) else None,
                maximum_hp=maximum if valid(maximum) and maximum > 0 else None, method=method,
                assumed_summon_start=summoned)
            self.basis['initial_budget_hp'] = (self.basis['ceiling_hp'] - self.basis['hp']
                if self.basis['hp'] is not None else None)
        b = self.basis
        if b['maximum_hp'] is None and valid(maximum) and maximum > 0:
            b['maximum_hp'] = maximum
        if valid(maximum) and maximum > 0 and b['maximum_hp'] is not None and maximum != b['maximum_hp']:
            self.invalid = 'Maximum HP changed; the initial healing ceiling is no longer comparable.'
        if method != b['method']:
            self.invalid = 'Healing-ceiling source changed during the capture.'
        if ceiling > b['ceiling_hp'] + 1:
            self.invalid = 'Healing ceiling rose above its initial value; healing or capacity changed outside the assumed budget accounting.'
        if self.invalid:
            self.reason = self.invalid
            return
        self.amount = max(0, b['ceiling_hp'] - ceiling)
        self.fraction = self.amount / b['maximum_hp'] if b['maximum_hp'] else None
        self.ceiling, self.as_of = ceiling, t
        if valid(hp) and b['hp'] is not None:
            healing = hp + self.amount - b['hp']
            self.healing = max(0,healing) if healing >= -1 else None
            initial_budget = b.get('initial_budget_hp')
            if self.healing is not None and valid(initial_budget):
                self.remaining_budget = max(0,initial_budget-self.healing)
        self.reason = 'Calculated since first valid observation; assumes healing spends an equal HP budget and maximum HP/capacity remain unchanged.'
        if b.get('assumed_summon_start'):
            self.reason = 'Calculated from an assumed full-health summon starting ceiling of 1.75 × maximum HP, including losses before its first sample; assumes normal 75% healing capacity and equal budget spending.'

    def summary(self):
        return dict(damage_taken_estimate=self.amount, damage_taken_fraction=self.fraction,
            healing_received_estimate=self.healing,
            healing_budget_remaining_calculated=self.remaining_budget,
            healing_received_reason=('Calculated as current HP + calculated damage taken - starting HP, using the captured deployment baseline when available. This estimates healing-budget spending, not an independent event counter.' if self.healing is not None else
                'Requires valid calculated damage taken, current HP and a recorded starting HP.'),
            damage_taken_calculation=dict(baseline=self.basis.copy() if self.basis else None,
                current_ceiling_hp=self.ceiling, as_of_s=self.as_of, reason=self.reason))
