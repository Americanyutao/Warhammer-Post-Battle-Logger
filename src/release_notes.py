"""Bounded GitHub release-note text and an installed-version offline cache."""
import html
import json
from pathlib import Path
import re
import urllib.request
from version import VERSION

REPOSITORY='Americanyutao/Warhammer-Post-Battle-Logger'
RELEASES_API=f'https://api.github.com/repos/{REPOSITORY}/releases'
RELEASES_URL=f'https://github.com/{REPOSITORY}/releases'
MAX_RELEASE=8*1024*1024
LOADING_NOTES='Loading patch notes from GitHub…'
UNAVAILABLE_NOTES='Patch notes could not be loaded from GitHub. You can use Full release notes to view them when you are online.'


def fetch_release(tag='latest',*,timeout=8):
    if tag!='latest' and not re.fullmatch(r'v\d+\.\d+\.\d+',tag):raise ValueError('Invalid release tag.')
    url=RELEASES_API+('/latest' if tag=='latest' else '/tags/'+tag)
    request=urllib.request.Request(url,headers={'User-Agent':f'WH3BattleLogger/{VERSION}','Accept':'application/vnd.github+json'})
    with urllib.request.urlopen(request,timeout=timeout) as response:data=response.read(MAX_RELEASE+1)
    if len(data)>MAX_RELEASE:raise ValueError('Release information is too large.')
    release=json.loads(data)
    if not isinstance(release,dict) or release.get('draft') or release.get('prerelease'):
        raise ValueError('Release is not a stable public release.')
    actual=release.get('tag_name','')
    if not isinstance(actual,str) or not re.fullmatch(r'v?\d+\.\d+\.\d+',actual):raise ValueError('Invalid release version.')
    if tag!='latest' and actual.lstrip('v')!=tag.lstrip('v'):raise ValueError('Release notes do not match the installed version.')
    return release


def plain_text(value):
    value=re.sub(r'<!--.*?-->','',value,flags=re.S)
    value=re.sub(r'!\[[^\]]*\]\([^)]*\)','',value)
    value=re.sub(r'\[([^\]]+)\]\([^)]*\)',r'\1',value)
    value=html.unescape(re.sub(r'<[^>]*>','',value))
    value=re.sub(r'[*_`~]','',value)
    value=''.join(c for c in value if c in '\n\t' or ord(c)>=32)
    return ' '.join(value.split()).strip()


def summarize_notes(body):
    if not isinstance(body,str):return 'No patch notes were published for this version.'
    body=re.sub(r'```.*?```','',body[:100000],flags=re.S)
    bullets=[];paragraphs=[]
    for line in body.splitlines():
        match=re.match(r'^\s*(?:[-*+]\s+|\d+[.)]\s+)(.+)',line)
        if match:
            text=plain_text(match.group(1))
            if text:bullets.append(text)
        elif line.strip() and not line.lstrip().startswith(('#','>','---')):
            text=plain_text(line)
            if text:paragraphs.append(text)
    selected=bullets[:6] if bullets else paragraphs[:4]
    short=[]
    for text in selected:
        if len(text)>240:text=text[:237].rsplit(' ',1)[0]+'…'
        short.append(('• ' if bullets else '')+text)
    return '\n\n'.join(short)[:1800] or 'No patch notes were published for this version.'


def cached_notes(root):
    path=Path(root)/'state/release-notes.json'
    try:
        if path.stat().st_size>16384:return None
        data=json.loads(path.read_text(encoding='utf-8'))
        if data['version']!=VERSION or not isinstance(data['summary'],str) or not 0<len(data['summary'])<=1800:return None
        return data['summary']
    except (OSError,ValueError,KeyError,TypeError):return None


def save_notes(root,summary):
    path=Path(root)/'state/release-notes.json';path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(dict(version=VERSION,summary=summary),ensure_ascii=False),encoding='utf-8')
    temporary.replace(path)
