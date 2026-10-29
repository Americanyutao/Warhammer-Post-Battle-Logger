"""Explicit release-storage precision; unknown fields remain untouched."""
POLICY=1
DIAGNOSTICS={'performance','wall_seconds','process_cpu_seconds','process_cpu_one_core_average_percent',
    'io_seconds','read_ms','read_calls','bytes_read','working_set_mib','private_mib','monotonic_s',
    'process_cpu_s','cpu_one_core_percent','cpu_window_percent','cpu_window_s'}
UNIT_FOUR={'health_percent','primary_ammo_fraction','secondary_ammo_fraction','healing_budget_remaining_fraction'}
STAT_FOUR={'armour','leadership','speed','melee_attack','melee_defence','weapon_strength','charge_bonus',
    'spell_resistance','missile_resistance','fire_resistance','fire_weakness','physical_resistance','ward_save'}
ARMY_FOUR={'current','reserve','maximum','recharge','recharge_per_second','recharge_seconds_per_point'}

def rounded(value,digits=4):return round(value,digits) if type(value) is float else value

def unit(value):
    out=dict(value)
    for key in UNIT_FOUR:
        if key in out:out[key]=rounded(out[key])
    if any(k in out for k in ('healing_budget_remaining_hp','healing_budget_unlimited')) and 'healing_ceiling_fraction_raw' in out:
        out['healing_ceiling_fraction_raw']=rounded(out['healing_ceiling_fraction_raw'])
    if isinstance(out.get('xyz'),(list,tuple)):out['xyz']=[rounded(v) for v in out['xyz']]
    if isinstance(out.get('statline'),dict):out['statline']={k:rounded(v) if k in STAT_FOUR else v for k,v in out['statline'].items()}
    return out

def sample(value):
    out={k:v for k,v in value.items() if k not in DIAGNOSTICS}
    for key in ('sim_s','first_s','last_s'):
        if key in out:out[key]=rounded(out[key])
    if 'model_s' in out:out['model_s']=rounded(out['model_s'],3)
    if isinstance(out.get('battle_clock'),dict):out['battle_clock']={k:rounded(v) if k in ('elapsed_s','remaining_s','limit_s') else v for k,v in out['battle_clock'].items()}
    if 'units' in out:out['units']=[unit(v) for v in out['units']]
    if 'armies' in out:out['armies']=[{k:rounded(v) if k in ARMY_FOUR else v for k,v in a.items()} for a in out['armies']]
    if isinstance(out.get('deployment_baseline'),dict):out['deployment_baseline']=sample(out['deployment_baseline'])
    return out

def release_record(record):
    if record.get('kind')=='header':
        out=dict(record);out['metadata']=dict(record.get('metadata',{}),storage_precision_policy=POLICY,diagnostics=False);return out
    if record.get('kind')=='footer':return dict(record,summary=sample(record['summary']))
    return sample(record)
