"""Conservative reconciliation of native final health and departure records."""
def resolve(unit, previous, t, *, results_phase=False):
    # IsAlive is an activity test, not a death reason. Neither it nor routing
    # alone establishes death/retreat. Require populated, coherent result data.
    fields = ('result_hp','result_models','result_initial_hp','result_initial_models','result_exit_reason')
    values = tuple(unit.get(k) for k in fields)
    valid = all(isinstance(v,int) and not isinstance(v,bool) for v in values)
    if not valid or unit.get('alive') is not False or unit.get('left_battlefield') is not True:
        return None, None
    hp, models, initial_hp, initial_models, reason = values
    maximum = max(initial_hp, unit.get('hp_max_cached') or 0)
    valid = initial_hp > 0 and initial_models > 0 and 0 <= hp <= maximum and 0 <= models <= initial_models
    status = 'Dead' if reason in (0,3) and hp == 0 and models == 0 else 'Retreated' if reason in (1,2) and hp > 0 and models > 0 else None
    if not valid or status is None: return None, None
    candidate = dict(values=values,t=t)
    # Final health/model records populate on the results screen, where the
    # battle clock can stop. The verified results phase confirms coherent final
    # records even if only one results tick was saved or later ticks share t.
    if results_phase:
        return dict(status=status,hp=hp,models=models,observed_s=t,
                    source='native_result',exit_reason=reason,
                    confirmation='results_phase'), candidate
    # During combat, two distinct battle times guard transient/unfinalized data.
    # Paused duplicate timestamps do not advance this provisional confirmation.
    if previous and previous['values'] == values:
        candidate['t'] = previous['t']
        if t > previous['t']:
            return dict(status=status,hp=hp,models=models,observed_s=t,
                        source='native_result',exit_reason=reason), candidate
    return None, candidate
