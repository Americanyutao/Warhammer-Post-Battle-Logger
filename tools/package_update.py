"""Create a clean download and byte-range inventory for incremental updates."""
import argparse
import gzip
import json
from pathlib import Path
import struct
import sys
import zipfile

P=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(P/'src'))
from update_manifest import app_files, app_path, file_hash, validate_manifest, ARCHIVE, MANIFEST
from version import VERSION


def package_release(source, output, version=VERSION):
    source, output = Path(source), Path(output)
    output.mkdir(parents=True,exist_ok=True)
    archive = output/ARCHIVE
    files = []
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as package:
        for path in app_files(source):
            name=path.relative_to(source).as_posix();app_path(name)
            package.write(path,name)
            item=package.getinfo(name)
            files.append(dict(path=name,size=item.file_size,compressed=item.compress_size,
                              offset=item.header_offset,method=item.compress_type,sha256=file_hash(path)))
    # Local ZIP headers contain variable-length file names and extra fields.
    with archive.open('rb') as raw:
        for item in files:
            raw.seek(item['offset'])
            header=raw.read(30)
            if header[:4]!=b'PK\x03\x04':raise ValueError('Invalid ZIP header.')
            lengths=struct.unpack_from('<HH',header,26)
            item['offset']+=30+sum(lengths)
    manifest=dict(schema=1,version=version,archive=ARCHIVE,files=files)
    validate_manifest(manifest,'v'+version,archive.stat().st_size)
    (output/MANIFEST).write_bytes(gzip.compress(json.dumps(manifest,separators=(',',':')).encode('utf-8'),mtime=0))
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--app-dir',type=Path,default=P/'release/WH3BattleLogger')
    parser.add_argument('--output',type=Path,default=P/'build/publish')
    args=parser.parse_args()
    manifest=package_release(args.app_dir,args.output)
    print(f'v{VERSION}: {len(manifest["files"])} app files. Publish BOTH {ARCHIVE} and {MANIFEST} from {args.output}.')
