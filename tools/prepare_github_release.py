"""Validate release versions and attach the tested file pair to a GitHub draft."""
import argparse
import gzip
import json
import os
from pathlib import Path
import re
import subprocess
import sys

P=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(P/'src'))
from version import VERSION
from update_manifest import ARCHIVE,MANIFEST,validate_manifest


def validate_tag(tag, version=VERSION):
    if not re.fullmatch(r'v\d+\.\d+\.\d+',tag) or tag!='v'+version:
        raise ValueError(f'Release tag {tag!r} must match the application version: v{version}.')


def gh(*args):
    return subprocess.run(['gh',*args],check=True,capture_output=True,text=True).stdout


def prepare_release(tag, directory, repository):
    # The upload helper can come from main while Windows builds an older tag.
    # The manifest and Windows version gate bind these files to that exact tag.
    validate_tag(tag,tag.removeprefix('v'))
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repository):
        raise ValueError('Invalid GitHub repository.')
    directory=Path(directory)
    archive=directory/ARCHIVE;manifest=directory/MANIFEST
    data=json.loads(gzip.decompress(manifest.read_bytes()))
    validate_manifest(data,tag,archive.stat().st_size)
    releases=json.loads(gh('release','list','--repo',repository,'--limit','100','--json','tagName,isDraft'))
    existing=next((release for release in releases if release['tagName']==tag),None)
    if existing:
        if not existing['isDraft']:
            raise ValueError(f'{tag} is already published. Create a new version instead of replacing public downloads.')
        gh('release','upload',tag,str(archive),str(manifest),'--repo',repository,'--clobber')
    else:
        gh('release','create',tag,str(archive),str(manifest),'--repo',repository,
           '--draft','--verify-tag','--title',tag,'--generate-notes')
    print(f'{tag}: both update files attached to the draft. Review release notes, then publish on GitHub.')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--tag',default=os.environ.get('RELEASE_TAG',''))
    parser.add_argument('--directory',type=Path,default=P/'build/publish')
    parser.add_argument('--repository',default=os.environ.get('GITHUB_REPOSITORY',''))
    parser.add_argument('--check-tag',action='store_true')
    args=parser.parse_args()
    if args.check_tag:
        validate_tag(args.tag);print(f'Release tag matches app version: {args.tag}')
    else:prepare_release(args.tag,args.directory,args.repository)


if __name__=='__main__':main()
