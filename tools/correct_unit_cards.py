"""Replace only porthole fallbacks with traced DB/portrait unit-card paths."""
import hashlib
import json
from pathlib import Path
from package_report_assets import P,ROOT,table
from unit_card_sources import character_cards

def main():
    path=P/'assets/game-assets.json';index=json.loads(path.read_text(encoding='utf-8'))
    sources=character_cards(ROOT,table,index['provenance']);changes=[]
    evidence_path=P/'build/unit-card-corrections.json'
    prior=json.loads(evidence_path.read_text(encoding='utf-8')) if evidence_path.exists() else {}
    original={row['unit_key']:row['old'] for row in prior.get('changes',[])}
    for key,old in list(index['units_by_key'].items()):
        if 'porthole' not in old and key not in index.get('card_candidates_by_key',{}):continue
        rows=sources.get(key,[])
        if not rows:raise ValueError('No verified character card for '+key)
        image=rows[0]['image']
        if not (P/'assets/game'/image).is_file():raise ValueError('Missing card '+image)
        index['units_by_key'][key]=image
        alternatives=list(dict.fromkeys(r['image'] for r in rows))
        index.setdefault('card_candidates_by_key',{})[key]=alternatives
        if len(alternatives)>1:index.setdefault('unit_key_notes',{})[key]='Default appearance variant; a recorded portrait selects the exact unit card.'
        changes.append(dict(unit_key=key,old=original.get(key,old),new=image,source_chain=rows))
    for alias,old in list(index['units'].items()):
        if 'porthole' not in old and not any(key in original for key in index.get('name_units',{}).get(alias,[])):continue
        images={index['units_by_key'][key] for key in index.get('name_units',{}).get(alias,[]) if key in index['units_by_key']}
        if len(images)==1:index['units'][alias]=images.pop()
        else:del index['units'][alias]
    if any('porthole' in value for section in ('units','units_by_key') for value in index[section].values()):raise ValueError('Porthole fallback remains.')
    evidence=dict(changes=changes,sources={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'ui/portraits/units').glob('*.bin')})
    (P/'build/unit-card-corrections.json').write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf-8')
    path.write_text(json.dumps(index,indent=2)+'\n',encoding='utf-8')
    print('Corrected unit records:',len(changes))

if __name__=='__main__':main()
