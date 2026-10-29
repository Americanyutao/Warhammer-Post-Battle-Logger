"""Trim packaged PNGs unreachable by card lookup; retain source/reference assets."""
import json
from pathlib import Path
import sys
P=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(P/'src'))
from report_assets import required_images

def prune(app):
    root=Path(app)/'_internal/assets';index_path=root/'game-assets.json'
    index=json.loads(index_path.read_text(encoding='utf-8'));keep=required_images(index)
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
        note='Unit-card and stat images only. Character cards follow DB-linked art-set metadata; porthole and minspec-porthole fallbacks are excluded.')
    for directory in sorted((root/'game').rglob('*'),key=lambda p:len(p.parts),reverse=True):
        if directory.is_dir() and not directory.is_symlink() and directory.resolve().is_relative_to(root.resolve()) and not any(directory.iterdir()):directory.rmdir()
    index_path.write_text(json.dumps(index,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    result=dict(app_root=str(Path(app).resolve()),removed=removed,removed_bytes=size,kept=len(index['provenance']))
    (P/'build/release-assets-pruned.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    return result
