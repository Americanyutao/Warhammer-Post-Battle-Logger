"""Run the real packaged viewer against an isolated or read-only battle log."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

P=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--app-dir',type=Path)
    parser.add_argument('--source',type=Path)
    parser.add_argument('--key',type=Path)
    args=parser.parse_args()
    executable=(args.app_dir/'WH3BattleLogger.exe') if args.app_dir else Path(json.loads((P/'build/release-build.json').read_text(encoding='utf-8'))['executable'])
    root=P/'build'/('viewer-qa-'+uuid.uuid4().hex[:10]);root.mkdir()
    if args.source:
        source=args.source.resolve();key=args.key or source.parent/'logger.key'
        corrections=source.parent.parent/'report-corrections.json'
        if corrections.is_file():shutil.copy2(corrections,root/'report-corrections.json')
    else:
        sys.path.insert(0,str(P/'src'))
        from demo import frames
        from logfile import LogWriter,load_key
        source=root/'captures/test.wh3log';key=source.parent/'logger.key'
        writer=LogWriter(source,load_key(key,True),dict(source='synthetic'))
        for frame in frames(4,600):writer.write(frame)
        writer.close({})
    original=hashlib.sha256(source.read_bytes()).hexdigest()
    result_path=root/'result.json'
    completed=subprocess.run([str(executable),'--view-log',str(source),'--view-key',str(key),
        '--data-dir',str(root),'--viewer-check',str(result_path)],timeout=110)
    result=json.loads(result_path.read_text(encoding='utf-8'))
    if completed.returncode or not result.get('success'):raise RuntimeError(result.get('error','Viewer check failed.'))
    assert result['cache_removed'],'Temporary browser cache remained.'
    assert not list(root.rglob('*.html')),'An HTML report was generated.'
    assert original==hashlib.sha256(source.read_bytes()).hexdigest(),'Source recording changed.'
    summary={k:v for k,v in result.items() if k not in ('images','cache_path')}
    summary['linked_images']=len(result['images']);summary['evidence_directory']=str(root)
    (P/'build/embedded-viewer-check.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
