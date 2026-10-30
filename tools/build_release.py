"""Build the windowless release without copying private captures or keys."""
import importlib.util
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

P=Path(__file__).resolve().parents[1]


def main(build_only=False):
    dependencies=Path(os.environ.get('WH3_BUILD_DEPS', P/'build/packaging-deps'))
    sys.path.insert(0,str(dependencies))
    if importlib.util.find_spec('PyInstaller') is None:
        raise RuntimeError('Install PyInstaller into build/packaging-deps before building.')
    stage=P/'build'/('release-package-'+str(time.time_ns()))
    stage.mkdir(parents=True)
    command=[sys.executable,'-B','-m','PyInstaller','--windowed','--onedir',
        '--name','WH3BattleLogger','--icon',str(P/'assets/app/battle_logger.ico'),
        '--distpath',str(stage/'dist'),'--workpath',str(stage/'work'),'--specpath',str(stage),
        '--exclude-module','PIL']
    viewer_dependencies=P/'build/embedded-viewer-deps'
    if viewer_dependencies.is_dir():command+=['--paths',str(viewer_dependencies)]
    command+=['--collect-data','webview','--hidden-import','webview.platforms.winforms',
        '--hidden-import','webview.platforms.edgechromium','--copy-metadata','pywebview',
        '--copy-metadata','pythonnet','--copy-metadata','zstandard']
    for source,destination in [('assets','assets'),('profiles','profiles'),
        ('src/report_template.html','src'),('src/report_view.js','src'),('src/report.css','src'),
        ('src/viewer_shell.html','src'),('src/viewer_boot.js','src')]:
        command+=['--add-data',str(P/source)+os.pathsep+destination]
    command.append(str(P/'src/release_app.py'))
    environment=dict(os.environ,PYTHONPATH=os.pathsep.join([str(viewer_dependencies),str(dependencies)]),PYTHONDONTWRITEBYTECODE='1')
    subprocess.run(command,cwd=P,env=environment,check=True)
    built=stage/'dist/WH3BattleLogger'
    from prune_report_assets import prune
    prune(built)
    # Retain third-party attribution without shipping Markdown project notes.
    for notice in built.glob('_internal/*.dist-info/licenses/*.md'):
        notice.rename(notice.with_suffix('.txt'))
    # Merge only built app files. Existing captures/keys in a release stay intact.
    destination=P/'release/WH3BattleLogger'
    (built/'README.txt').write_text(
        'WARHAMMER III BATTLE LOGGER\n\n'
        'See where your army made the difference.\n\n'
        'Automatic battle recording, a live damage meter, and detailed reports with damage, healing budgets, statlines, buffs/debuffs and movement maps.\n\n'
        'GET STARTED\n'
        '1. Run WH3BattleLogger.exe before a battle.\n'
        '2. Play normally; recording starts with combat.\n'
        '3. Double-click a battle in the main menu to explore its report.\n\n'
        'Close the menu with X to keep logging in the tray. Double-click the tray icon to reopen it. Use Exit logger to stop.\n\n'
        'LIVE METER & SETTINGS\n'
        'Open Live Meter / Hide Live Meter controls the meter; Show meter in the tray opens or restores it. Damage / Heal budget and All / Ally / Enemy buttons filter one ranked list. Click a bar to switch stats. Green bars are allied; red bars are enemy. Enemies appear after being spotted. Departed units stay grey in Damage and disappear from Heal budget. Bars and rankings animate over the logging interval. Pin keeps it on top. Drag the header or resize an edge/corner; size, position and filters are remembered. The meter has its own taskbar preview and stays open when the menu is closed. Settings never opens the meter. Logging interval changes take effect next battle.\n\n'
        'SHARE & KEEP YOUR BATTLES\n'
        'Rename battles and export HTML to captures/shareables. Open folder takes you to captures/shareables. Reports work offline; HTML is optional.\n'
        'Encrypted recordings are in captures. Keep logger.key with them: without it, recordings cannot be opened. Missing readings stay unknown; interrupted battles may have incomplete data.\n\n'
        'Updates: use Check for updates in the menu or tray.\n'
        'YouTube: https://www.youtube.com/@Americanyutao\n'
        'Discord: https://discord.com/invite/v27y7AW7Kz\n',encoding='utf-8')
    if not build_only:shutil.copytree(built,destination,dirs_exist_ok=True)
    executable=(built if build_only else destination)/'WH3BattleLogger.exe'
    if not executable.is_file():raise RuntimeError('Release executable was not produced.')
    import PyInstaller
    sys.path.insert(0,str(P/'src'))
    from version import VERSION
    (P/'build/release-build.json').write_text(json.dumps(dict(executable=str(executable),
        version=VERSION,pyinstaller=PyInstaller.__version__,python=sys.version,windowless=True,
        private_capture_data_included=False),indent=2)+'\n',encoding='utf-8')
    print(executable)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--build-only',action='store_true',help='Build separately without replacing the local app (use while the logger is running).')
    main(parser.parse_args().build_only)
