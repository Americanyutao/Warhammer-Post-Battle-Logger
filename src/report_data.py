"""Authenticated capture -> report data, independent of any display/export."""
import json
from pathlib import Path
from aggregate import Battle
from logfile import read_log
from paths import DATA_ROOT
from capture_precision import DIAGNOSTICS


def read_summary(source,key,*,recover_tail=False,corrections_root=None,progress=None,cancel=None):
    battle=footer=None
    for record in read_log(source,key,recover_tail=recover_tail,progress=progress):
        if cancel and cancel.is_set():raise InterruptedError('Report closed.')
        if record['kind']=='header':
            meta=record.get('metadata',{})
            battle=Battle(meta,max_gap=meta.get('maximum_interval_s',80))
        elif record['kind']=='sample':
            if battle.metadata.get('source')=='external-native':
                result=record.get('battle_result')
                if result and result.get('result_layout')!='result_context_slot_8':
                    record=dict(record,battle_result=None)
                for army in record.get('armies',[]):
                    if 'recharge_per_second' not in army:
                        reciprocal=army.get('recharge')
                        army['recharge_seconds_per_point']=reciprocal
                        army['recharge_per_second']=1/reciprocal if reciprocal and reciprocal>0 else None
                        army['recharge_rate_source']='derived from legacy native reciprocal'
            battle.observe(record)
        elif record['kind']=='gap':battle.break_continuity()
        elif record['kind']=='footer':footer=record['summary']
    if battle is None:raise ValueError('Incomplete capture: no readable header.')
    if footer is None and recover_tail and battle.samples:
        footer=dict(reason='recovered_interrupted_recording',incomplete=True,
            recovery_note='Recovered authenticated samples only. Recording ended unexpectedly; the final samples may be missing.')
    if footer is None:raise ValueError('Incomplete capture: no recorded battle samples.')
    if cancel and cancel.is_set():raise InterruptedError('Report closed.')
    summary=battle.summary()
    summary.pop('performance',None)
    footer={k:v for k,v in footer.items() if k not in DIAGNOSTICS}
    corrections=Path(corrections_root or DATA_ROOT)/'report-corrections.json'
    if corrections.is_file():
        correction=json.loads(corrections.read_text(encoding='utf-8')).get(Path(source).name)
        if correction and correction.get('outcome') in ('Victory','Defeat','Draw'):
            summary['battle_result']=dict(correction,source='user_report_correction')
    size=Path(source).stat().st_size
    if 'encrypted_bytes' in footer and footer['encrypted_bytes']!=size:
        footer['legacy_reported_encrypted_bytes']=footer['encrypted_bytes']
    footer['encrypted_bytes']=size
    summary['capture']=footer
    warnings=[]
    if summary['metadata'].get('started_mid_battle'):
        warnings.append('Recording started after deployment. Values and totals may be incorrect or incomplete.')
    if footer.get('recovery_note'):warnings.append(footer['recovery_note'])
    elif footer.get('reason') in ('unit_data_timeout','game_process_exit'):
        warnings.append('Recording ended because the game stopped supplying unit data. The final battle result may be unavailable.')
    summary['recording_warnings']=warnings
    return summary
