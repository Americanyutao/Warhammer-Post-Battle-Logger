"""Exercise a real packaged incremental upgrade over local HTTP, without publishing."""
import argparse
import gzip
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
from unittest.mock import patch

P=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(P/'src'))
from update_manifest import app_files,MANIFEST,ARCHIVE,validate_manifest,file_hash
from updater import plan_update,stage_update,install_files,cleanup_update


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--old-app',type=Path,required=True)
    parser.add_argument('--publish',type=Path,required=True)
    args=parser.parse_args()
    archive=(args.publish/ARCHIVE).resolve();size=archive.stat().st_size
    metadata=json.loads(gzip.decompress((args.publish/MANIFEST).read_bytes()))
    files=validate_manifest(metadata,'v'+metadata['version'],size)
    traffic=[]
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            value=self.headers.get('Range')
            if not value:self.send_error(400);return
            first,last=map(int,value[6:].split('-'))
            length=last-first+1;traffic.append(length)
            self.send_response(206);self.send_header('Content-Range',f'bytes {first}-{last}/{size}')
            self.send_header('Content-Length',str(length));self.end_headers()
            with archive.open('rb') as source:
                source.seek(first)
                while length:
                    chunk=source.read(min(length,256*1024));self.wfile.write(chunk);length-=len(chunk)
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        with tempfile.TemporaryDirectory(prefix='incremental-qa-',dir=P/'build') as temp:
            root=Path(temp).resolve();installed=root/'installed';installed.mkdir()
            for source in app_files(args.old_app):
                target=installed/source.relative_to(args.old_app);target.parent.mkdir(parents=True,exist_ok=True)
                try:os.link(source,target)
                except OSError:shutil.copy2(source,target)
            (installed/'captures').mkdir();(installed/'captures/logger.key').write_bytes(b'private test key')
            (installed/'captures/saved-report.html').write_bytes(b'Existing report must not change')
            changed,removed=plan_update(files,installed)
            stage=stage_update(dict(size=size,browser_download_url=f'http://127.0.0.1:{server.server_port}/app.zip'),files,changed,removed,installed)
            check=root/'stage-check.json'
            subprocess.run([str(stage/'WH3BattleLogger.exe'),'--check-install',str(check)],check=True,timeout=90)
            assert json.loads(check.read_text())['version']==metadata['version']
            install_files(stage,installed)
            subprocess.run([str(installed/'WH3BattleLogger.exe'),'--check-install',str(root/'installed-check.json')],check=True,timeout=90)
            assert json.loads((root/'installed-check.json').read_text())['version']==metadata['version']
            assert (installed/'captures/logger.key').read_bytes()==b'private test key'
            assert (installed/'captures/saved-report.html').read_bytes()==b'Existing report must not change'
            for item in files:assert file_hash(installed/item['path'])==item['sha256'],item['path']
            with patch('updater.sys.executable',str(installed/'WH3BattleLogger.exe')),patch('updater.wait_for_exit'):
                cleanup_update(stage.parent,0)
            assert sorted(p.name for p in installed.iterdir())==['README.txt','WH3BattleLogger.exe','_internal','captures']
            result=dict(version=metadata['version'],changed_files=len(changed),range_requests=len(traffic),download_bytes=sum(traffic),full_zip_bytes=size,
                        staged_self_check=True,installed_self_check=True,all_file_hashes_match=True,private_data_preserved=True,no_backup_or_staging_left=True)
            (P/'build/incremental-package-check.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
            print(json.dumps(result,indent=2))
    finally:server.shutdown();server.server_close();thread.join()


if __name__=='__main__':main()
