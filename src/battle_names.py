"""Readable battle filenames, with collision-safe timestamp suffixes."""
from pathlib import Path
import re

LEGACY_NAME=re.compile(r'^(battle-\d{8}-\d{6})-[0-9a-f]{8}$',re.I)

def validate_name(name):
    if not isinstance(name,str) or not name or len(name)>160:raise ValueError('Enter a battle name between 1 and 160 characters.')
    if name!=name.strip() or name.endswith('.') or any(ord(c)<32 or c in '<>:"/\\|?*' for c in name):
        raise ValueError('Names cannot contain < > : " / \\ | ? *, or start/end with spaces or end with a dot.')
    if name.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),*(f'LPT{i}' for i in range(1,10))}:
        raise ValueError('That name is reserved by Windows. Please choose another.')
    return name

def unique_capture_path(root,name,exclude=None):
    root=Path(root);validate_name(name);number=0
    while True:
        stem=name+(f' ({number})' if number else '')
        path=root/'captures'/(stem+'.wh3log')
        candidates=(path,root/'captures'/(stem+'.html'),root/'shareables'/(stem+'.html'),root/'captures/shareables'/(stem+'.html'))
        if not any(p.exists() and (exclude is None or p.resolve()!=Path(exclude).resolve()) for p in candidates):return path
        number+=1
