"""Build the windowless release without copying private captures or keys."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

P=Path(__file__).resolve().parents[1]


def main():
    dependencies=P/'build/packaging-deps'
    sys.path.insert(0,str(dependencies))
    if importlib.util.find_spec('PyInstaller') is None:
        raise RuntimeError('Install PyInstaller into build/packaging-deps before building.')
    stage=P/'build'/('release-package-'+str(time.time_ns()))
    stage.mkdir(parents=True)
    command=[sys.executable,'-B','-m','PyInstaller','--windowed','--onedir',
        '--name','WH3BattleLogger','--icon',str(P/'assets/app/battle_logger.ico'),
        '--distpath',str(stage/'dist'),'--workpath',str(stage/'work'),'--specpath',str(stage),
        '--exclude-module','tkinter','--exclude-module','PIL']
    for source,destination in [('assets','assets'),('profiles','profiles'),
        ('src/report_template.html','src'),('src/report_view.js','src'),('src/report.css','src')]:
        command+=['--add-data',str(P/source)+os.pathsep+destination]
    command.append(str(P/'src/release_app.py'))
    environment=dict(os.environ,PYTHONPATH=str(dependencies),PYTHONDONTWRITEBYTECODE='1')
    subprocess.run(command,cwd=P,env=environment,check=True)
    built=stage/'dist/WH3BattleLogger'
    # Merge only built app files. Existing captures/keys in a release stay intact.
    destination=P/'release/WH3BattleLogger'
    shutil.copytree(built,destination,dirs_exist_ok=True)
    (destination/'README.txt').write_text(
        'WARHAMMER III Battle Logger\n\n'
        'Run WH3BattleLogger.exe before your battle. It runs only in the notification tray.\n'
        'Right-click the LOG icon: Open reports opens the captures folder in File Explorer; '
        'Exit finishes saving the current capture and report before closing.\n'
        'Deployment supplies initial values; combat timelines begin when battle starts. '
        'Leave the logger running through the results screen.\n'
        'Reports, encrypted captures and their private logger.key are created in captures beside the app. '
        'Keep the key with the captures. HTML reports are readable standalone files.\n'
        'Only the supported game builds are read; no game files or process memory are modified.\n',encoding='utf-8')
    executable=destination/'WH3BattleLogger.exe'
    if not executable.is_file():raise RuntimeError('Release executable was not produced.')
    import PyInstaller
    (P/'build/release-build.json').write_text(json.dumps(dict(executable=str(executable),
        pyinstaller=PyInstaller.__version__,python=sys.version,windowless=True,
        private_capture_data_included=False),indent=2)+'\n',encoding='utf-8')
    print(executable)


if __name__=='__main__':main()
