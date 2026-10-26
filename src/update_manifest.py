"""Release file inventory and strict app-owned path validation."""
import hashlib
from pathlib import Path, PurePosixPath
import re

MANIFEST = 'WH3BattleLogger-update.json.gz'
ARCHIVE = 'WH3BattleLogger-Windows-x64.zip'
MAX_FILE = 600 * 1024 * 1024
MAX_TOTAL = 1500 * 1024 * 1024


def app_path(name):
    if not isinstance(name, str) or not name or len(name) > 240 or '\\' in name or ':' in name:
        raise ValueError('Invalid application file path.')
    path = PurePosixPath(name)
    if path.is_absolute() or any(p in ('', '.', '..') or p.endswith((' ', '.')) for p in name.split('/')):
        raise ValueError('Unsafe application file path.')
    if any(re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\..*)?', p, re.I) for p in path.parts):
        raise ValueError('Reserved application file path.')
    if name not in ('WH3BattleLogger.exe', 'README.txt') and not (len(path.parts) > 1 and path.parts[0] == '_internal'):
        raise ValueError('Update attempted to modify a non-application file.')
    return path


def file_hash(path):
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def app_files(root):
    root = Path(root)
    files = []
    for name in ('WH3BattleLogger.exe', 'README.txt', '_internal'):
        entry = root/name
        if entry.is_symlink():
            raise ValueError('Application files must not be symbolic links.')
        if entry.is_file(): files.append(entry)
        elif entry.is_dir():
            for path in sorted(entry.rglob('*')):
                if path.is_symlink() or path.is_junction():
                    raise ValueError('Application files must not contain links.')
                if path.is_file(): files.append(path)
    return sorted(files, key=lambda p:p.relative_to(root).as_posix())


def validate_manifest(data, tag, archive_size):
    if data.get('schema') != 1 or data.get('version') != tag.lstrip('v') or data.get('archive') != ARCHIVE:
        raise ValueError('Update manifest does not match this release.')
    files = data.get('files')
    if not isinstance(files, list) or not 1 <= len(files) <= 20000:
        raise ValueError('Invalid update inventory.')
    seen = set(); total = 0; end = 0
    for item in files:
        name = item.get('path'); app_path(name)
        if name.casefold() in seen: raise ValueError('Duplicate application file.')
        seen.add(name.casefold())
        for field in ('size', 'compressed', 'offset'):
            if type(item.get(field)) is not int or item[field] < 0:
                raise ValueError('Invalid update file size or location.')
        if item['size'] > MAX_FILE or item['compressed'] > MAX_FILE or item['offset'] < end or item['offset'] + item['compressed'] > archive_size:
            raise ValueError('Update file exceeds its bounds.')
        if item.get('method') not in (0, 8) or not re.fullmatch('[0-9a-f]{64}', item.get('sha256', '')):
            raise ValueError('Unsupported update file or checksum.')
        end = item['offset'] + item['compressed']; total += item['size']
    if total > MAX_TOTAL or not {'wh3battlelogger.exe','_internal/python313.dll'}.issubset(seen):
        raise ValueError('Incomplete or oversized update inventory.')
    for name in seen:
        if any('/'.join(name.split('/')[:i]) in seen for i in range(1,len(name.split('/')))):
            raise ValueError('Conflicting update file paths.')
    return files
