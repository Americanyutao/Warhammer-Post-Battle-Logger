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
        '--exclude-module','tkinter','--exclude-module','PIL']
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
        'WARHAMMER III Battle Logger\n\n'
        'Run WH3BattleLogger.exe before your battle. Double-click a recorded battle in the main menu to open its report in a separate app window.\n'
        'Closing the main menu keeps logging in the tray. Double-click the LOG tray icon to reopen it. '
        'Interrupted recordings recover authenticated saved samples when opened. Icons and skill information load from bundled app files. '
        'The current view cache is removed when its window closes; stale caches are cleaned on next startup. '
        'Your graph choices and manually entered unit values are saved separately.\n'
        'Rename Battle changes a closed recording and its report title, preserving saved values and corrections. '
        'Battle names use date/time without random suffixes; duplicates use (1), (2), and so on. '
        'Export HTML writes captures/shareables/Battle name.html beside the app, then opens shareables in File Explorer. '
        'Re-exporting refreshes the matching HTML.\n'
        'Each executable launch shows What\'s new in the installed version with summarized GitHub release notes (cached for offline use). '
        'Startup checks for a newer stable release in the background and offers Yes/No to download it. '
        'No update alert is shown when offline or up to date. Installation still asks for confirmation.\n'
        'Right-click the LOG icon: Main menu / reports opens the menu; Restart app saves and restarts the logger; '
        'Check for updates downloads changed files with progress and offers to restart; '
        'About shows the installed version and GitHub release notes; '
        'Exit finishes saving the current recording and closes viewer windows.\n'
        'Deployment supplies initial values; combat timelines begin when battle starts. '
        'Leave the logger running through the results screen.\n'
        'Starting after deployment asks whether to keep or discard the battle. '
        'Game exits or 30 seconds without readable unit data finish the recording automatically. Pausing with readable data keeps recording. '
        'After a computer crash, restart the app to recover saved samples; final samples may be missing.\n'
        'Encrypted .wh3log recordings and their private logger.key are stored in captures beside the app. '
        'Keep the key with the captures. No HTML is generated automatically. '
        'New release recordings round approved measurement fields before Zstandard compression and encryption. Integer counters, raw regeneration, effect multipliers and legacy healing-ceiling calculation inputs are preserved. Debug performance data is not recorded in release mode. '
        'Startup optimizes older complete release recordings in the background after verifying the expected transformed records. Incomplete/unreadable files stay unchanged. '
        'Report windows open first and then load battle data, icons and skill details. '
        'Export HTML is a separate optional action. Check for updates deletes old HTML exports in captures; '
        'your recordings and private key are retained.\n'
        'The embedded viewer uses Microsoft Edge WebView2 Runtime on Windows.\n'
        'Updates preserve captures and keep no permanent backup copy.\n'
        'Only the supported game builds are read; no game files or process memory are modified.\n',encoding='utf-8')
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
