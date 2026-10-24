"""Offline, self-contained report; no website or in-game UI dependency."""
import argparse
import json
from pathlib import Path
from aggregate import Battle
from logfile import read_log, load_key
from paths import DATA_ROOT, resource_path


def convert(source, key, destination=None):
    battle = None
    footer = None
    for record in read_log(source, key):
        if record['kind'] == 'header':
            meta = record.get('metadata', {})
            battle = Battle(meta, max_gap=meta.get('maximum_interval_s', 80))
        elif record['kind'] == 'sample':
            if battle.metadata.get('source') == 'external-native':
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
        elif record['kind'] == 'gap':
            battle.break_continuity()
        elif record['kind'] == 'footer': footer = record['summary']
    if battle is None or footer is None: raise ValueError('Incomplete capture.')
    summary = battle.summary()
    corrections=DATA_ROOT/'report-corrections.json'
    if corrections.is_file():
        correction=json.loads(corrections.read_text(encoding='utf-8')).get(Path(source).name)
        if correction and correction.get('outcome') in ('Victory','Defeat','Draw'):
            summary['battle_result']=dict(correction,source='user_report_correction')
    size = Path(source).stat().st_size
    if 'encrypted_bytes' in footer and footer['encrypted_bytes'] != size:
        footer['legacy_reported_encrypted_bytes'] = footer['encrypted_bytes']
    footer['encrypted_bytes'] = size
    wall, cpu = footer.get('wall_seconds'), footer.get('process_cpu_seconds')
    if wall and cpu is not None:
        footer['process_cpu_one_core_average_percent'] = cpu/wall*100
    summary['capture'] = footer
    output = Path(destination) if destination else Path(source).with_suffix('.html')
    write_report(output, summary)
    return output


def write_report(path, summary):
    from report_assets import assets_for
    summary = dict(summary, report_filename=Path(path).stem, assets=assets_for(summary.get("units", [])))
    payload = json.dumps(summary, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
    payload = payload.replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    root = resource_path('src')
    template = (root/'report_template.html').read_text(encoding='utf-8')
    template = template.replace('__CSS__', (root/'report.css').read_text(encoding='utf-8'))
    template = template.replace('__JS__', (root/'report_view.js').read_text(encoding='utf-8'))
    Path(path).write_text(template.replace('__DATA__', payload), encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Convert an encrypted battle log to an offline report.')
    parser.add_argument('file', type=Path)
    parser.add_argument('--key', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    print(convert(args.file, load_key(args.key), args.output))
