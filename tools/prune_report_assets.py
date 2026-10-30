"""Trim packaged PNGs unreachable by card lookup; retain source/reference assets."""
import json
import os
from pathlib import Path
import sys
P=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(P/'src'))
from report_assets import required_images,canonical_card,generic_prince_key,GENERIC_DAEMON_PRINCE

def prune(app):
    root=Path(app)/'_internal/assets';index_path=root/'game-assets.json'
    index=json.loads(index_path.read_text(encoding='utf-8'))
    for section in ('units','units_by_key'):
        index[section]={key:GENERIC_DAEMON_PRINCE if section=='units_by_key' and generic_prince_key(key) else canonical_card(image) for key,image in index.get(section,{}).items()}
    for key in index.get('unit_info',{}):
        if generic_prince_key(key):index['units_by_key'][key]=GENERIC_DAEMON_PRINCE
    for name,keys in index.get('name_units',{}).items():
        if keys and all(generic_prince_key(key) for key in keys):index['units'][name]=GENERIC_DAEMON_PRINCE
    index['card_candidates_by_key']={key:list(dict.fromkeys(canonical_card(image) for image in images)) for key,images in index.get('card_candidates_by_key',{}).items()}
    keep=required_images(index)
    missing=[name for name in keep if not (root/'game'/name).is_file()]
    if missing:raise ValueError('Required card image missing: '+missing[0])
    removed=[];size=0
    for path in (root/'game').rglob('*.png'):
        name=path.relative_to(root/'game').as_posix()
        if name in keep:continue
        if not path.resolve().is_relative_to(root.resolve()) or path.is_symlink():raise ValueError('Unexpected asset link.')
        size+=path.stat().st_size;removed.append(name);path.unlink()
    index['provenance']={k:v for k,v in index['provenance'].items() if k in keep}
    index['distribution_summary']=dict(images=len(index['provenance']),portholes=False,
        excluded_portrait_mask_folders=['ui/portraits/units/no_culture/'],
        generic_daemon_prince=GENERIC_DAEMON_PRINCE,
        note='Unit-card and stat images only. Customizable Daemon Prince appearances use one generic card. Porthole fallbacks, body-part icons and unused no_culture masks are excluded.')
    for directory in sorted((root/'game').rglob('*'),key=lambda p:len(p.parts),reverse=True):
        if directory.is_dir() and not directory.is_symlink() and directory.resolve().is_relative_to(root.resolve()) and not any(directory.iterdir()):directory.rmdir()
    temporary=index_path.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(index,ensure_ascii=False,separators=(',',':')),encoding='utf-8');os.replace(temporary,index_path)
    result=dict(app_root=str(Path(app).resolve()),removed=removed,removed_bytes=size,kept=len(index['provenance']))
    (P/'build/release-assets-pruned.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    return result
