"""Small offline audit of the user's latest capture; no raw memory search."""
import json
from pathlib import Path
import sys
P=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(P/'src'))
from logfile import read_log,load_key

def main():
    source=P/'captures/battle-20261022-211519-f35d34fc.wh3log'
    previous=0; events=[];spawn=None
    for r in read_log(source,load_key(P/'captures/logger.key')):
        if r['kind']!='sample':continue
        for u in r['units']:
            if u.get('spawned') and spawn is None:spawn=r['sim_s']
            if u['side']=='Allied' and 'Necrarch' in u['name']:
                ally=sum(v['ally'] for v in (u.get('damage_by_source') or {}).values())
                if ally!=previous:events.append(dict(sim_s=r['sim_s'],ally_damage_delta=ally-previous,cumulative=ally))
                previous=ally
    result=dict(source=source.name,first_summon_s=spawn,ally_damage_events=events,
        ally_damage_before_summon=sum(e['ally_damage_delta'] for e in events if spawn is None or e['sim_s']<spawn),
        ally_damage_total=previous,
        limitation='Native ally credit has no victim identity. Spell overlap and summon damage attribution cannot be separated from this log.')
    (P/'build/latest-capture-review.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))

if __name__=='__main__':main()
