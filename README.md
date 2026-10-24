# WARHAMMER III Battle Logger

An external battle logger for Total War: WARHAMMER III that runs quietly in the Windows tray and generates interactive post-battle reports. Analyze unit damage, healing estimates, ammunition, fatigue, leadership, movement heatmaps and Winds of Magic in standalone HTML reports.

## Screenshots

Compare unit performance in the battle overview, including damage, gold damage, damage taken, status, HP and models.

![Battle overview with unit comparisons](docs/screenshots/battle-overview.png)

Explore healing received and the remaining healing budget for each unit.

![Healing breakdown by unit](docs/screenshots/healing-breakdown.png)

Select different statistics in the unit graphs to inspect how a battle unfolded.

![Unit graphs and statistic selector](docs/screenshots/unit-graphs.png)

Follow fatigue points over time against fatigue-state thresholds.

![Fatigue points and state thresholds](docs/screenshots/fatigue-points.png)

Compare friendly fire across units.

<img src="docs/screenshots/friendly-fire.png" alt="Friendly fire column sorted by damage" width="117">

## Run

Extract the complete Windows build into a writable folder and run `WH3BattleLogger.exe`. Keep `_internal` beside the executable. Start it before your battle and leave it running through the results screen.

Right-click the LOG tray icon to **Open reports** or **Exit**. Reports and encrypted recordings are saved in `captures` beside the app. Keep `logger.key` with recordings you want to reopen. HTML reports work on their own.

Windows 64-bit and a supported game build are required. The logger reads game memory without modifying it. Statistics include sampled observations and calculated estimates; ammunition compares starting and ending totals, including ammunition lost with dead models and excluding replenishment accounting.

## Automated builds

Every push, pull request, or manual run starts **Build Windows app** in the repository's **Actions** tab. Open a successful run and download **WH3BattleLogger-Windows-x64** under **Artifacts**. Extract everything before launching the executable. These are downloadable test builds; the workflow does not publish a GitHub Release.

Cloud checks cover offline regression tests, report JavaScript syntax, executable icons/subsystem, bundled resources, encryption and report generation. Game executable reference checks, original asset export comparison, and interactive desktop/tray checks run locally.

## Build from source

Use Python 3.13 on 64-bit Windows:

```powershell
python -m pip install -r requirements-build.txt
python -B tools/test_ci.py
python -B tools/build_release.py
python -B tools/check_release.py --headless
```

Output: `release/WH3BattleLogger/`. For interactive tray validation, run `python -B tools/check_release.py` in a normal Windows desktop session. `Run-Battle-Logger.cmd` launches the source debugging interface.
