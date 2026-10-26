<p align="center">
  <a href="https://www.patreon.com/c/Americanyutao">
    <img src="https://img.shields.io/badge/Support%20on-Patreon-FF424D?style=for-the-badge&logo=patreon&logoColor=white" alt="Support on Patreon">
  </a>
  <a href="https://www.youtube.com/@Americanyutao">
    <img src="https://img.shields.io/badge/Watch%20on-YouTube-FF0000?style=for-the-badge&logo=youtube&logoColor=white" alt="Watch on YouTube">
  </a>
  <a href="https://www.twitch.tv/americanyutao">
    <img src="https://img.shields.io/badge/Watch%20on-Twitch-9146FF?style=for-the-badge&logo=twitch&logoColor=white" alt="Watch on Twitch">
  </a>
  <a href="https://discord.com/invite/v27y7AW7Kz">
    <img src="https://img.shields.io/badge/Join%20our-Discord-5865F2?style=for-the-badge&logo=discord&logoColor=white" alt="Join our Discord">
  </a>
</p>
<p align="center">
  <img src="assets/app/battle_logger-128.png" width="96" alt="Battle Logger icon">
</p>

# WARHAMMER III Full Battle Details

An external battle logger for **Total War: WARHAMMER III**. It runs quietly in the Windows notification tray and creates interactive HTML reports after your battles.

Compare unit performance, explore damage breakdowns, and inspect graphs of health, leadership, fatigue, movement and Winds of Magic.

[View an example battle report](https://examplebattle.yutaohi.workers.dev/)

## Download and run

1. Open the [latest release](https://github.com/Americanyutao/Warhammer-Post-Battle-Logger/releases/latest).
2. Under **Assets**, download the Windows application ZIP. Do not download the **Source code** archives.
3. Right-click the ZIP and choose **Extract All**. Extract it into a folder you can write to.
4. Open the extracted folder and run **WH3BattleLogger.exe**. Keep the **_internal** folder beside the executable.
5. Start the logger before your battle and leave it running through the results screen.

**No application window will appear.** Look for the **LOG** icon in the Windows notification tray, including the hidden icons menu next to the clock.

Right-click the tray icon:

- **Open reports** opens the folder containing your recordings and reports. Open an **HTML** report in your browser.
- **Check for updates** checks GitHub for a newer stable version and offers to download and install it. Available in v1.1.0 and later.
- **About** shows the installed version and opens its GitHub release notes.
- **Exit** finishes saving the current recording and closes the logger.

The packaged application does not require Python. It requires **64-bit Windows** and a supported build of **Total War: WARHAMMER III**. Game updates may require an updated logger.

## Updating (v1.1.0 and later)

Right-click the **LOG** tray icon and choose **Check for updates**. The logger compares its installed version with the latest stable GitHub Release. It checks only when you choose this option; it does not automatically check or install updates.

From v1.1.2 onward, the logger checks which application files changed and downloads only those portions of the release ZIP. The confirmation shows the actual download size. A progress window shows checking, downloading and installation; you can cancel before installation. Recording continues during the download. The logger verifies each downloaded file and tests the new application, then asks before saving, closing, installing and restarting. **Install updates between battles** so your recording is not interrupted.

Your **captures** folder, existing reports and **logger.key** stay in place. Successful updates keep one installed copy: temporary replacement files are removed, and backups created by older logger versions are cleaned up. Temporary copies of changed files are used only during installation to recover from a failed copy.

**Coming from v1.1.0 or v1.1.1:** one full download is needed to obtain the new updater. Smaller downloads and download progress are available for subsequent updates. Large downloads are still possible when many files, game images or runtime dependencies change.

**Upgrading from v1.0.0:** download v1.1.0 or a later release manually using the steps above. Exit the old logger first. Keep your existing **captures** folder, including **logger.key**; if you extract the new app into a separate folder, copy the captures folder beside the new executable. After this upgrade, future updates can be installed from the tray menu.

## What the reports show

- **Battle overview:** victory or defeat, with the result classification when captured.
- **Unit comparisons:** damage dealt, gold damage, kills, friendly fire, self damage, calculated damage taken, calculated healing received, HP and models.
- **Damage breakdowns:** melee, missiles and spells, direct damage abilities and effects, plus separate source details.
- **Ranged statistics:** initial primary and secondary ammunition and the net decrease in each ammunition pool.
- **Unit graphs:** health, models, damage, ammunition, fatigue state and points, leadership, healing information and elevation.
- **Movement and occupancy:** sampled paths and time spent in different areas, using a shared map frame for the battle.
- **Winds of Magic:** usable winds and reserves over time.
- **Activity:** time spent in observed activities and states, idle time after rallying, and sampled rally and landing counts.

Choose allied, enemy or all units. Unit graphs can also be opened in separate mini windows, with up to four pop-outs.

## How recording works

The logger reads supported game data from the running game's memory without modifying it. It is an external application rather than a Steam Workshop mod.

Sampling defaults to once per second. Deployment supplies initial unit values, while combat timelines begin when the battle starts. Duration measurements use battle simulation time, so pauses and speed changes do not count as normal-speed elapsed time.

Reports and encrypted recordings are saved in the **captures** folder beside the application:

- **.html:** a standalone report you can open or share without running the logger.
- **.wh3log:** an encrypted battle recording.
- **logger.key:** the private key needed to read your encrypted recordings. Keep it with recordings you want to reopen.

## Interpreting the statistics

Some statistics are sampled observations or calculations rather than complete event histories. Events between samples may be missed.

- **Ammunition:** compares beginning and ending ammunition. Replenishment is not accounted for separately, and dead models take their remaining ammunition with them. The decrease is not a verified count of projectiles fired.
- **Healing and damage taken:** calculated using HP and healing-budget data where available. Healing-cap changes and other capacity changes can affect the calculation. The base healing budget is 75% of maximum HP; healing-cap increases multiply that base. For example, +100% increased healing cap gives 2x75 = 150% of maximum HP as healing budget.
- **Damage categories:** follow the game's recorded source categories. Some spells, including vortex effects, can appear under missiles and spells.
- **Lords and heroes:** the default unit value is 500 gold per level. Treat trade comparisons using that value as estimates.
- **Movement, rallies and landings:** derived from sampled positions and state changes.
- **Barrier statistics:** remain work in progress.

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

## Build from source

Use Python 3.13 on 64-bit Windows:

```powershell
python -m pip install -r requirements-build.txt
python -B tools/test_ci.py
python -B tools/build_release.py
python -B tools/check_release.py --headless
python -B tools/package_update.py
```

The application is built into `release/WH3BattleLogger/`. Keep the complete folder together. Run `python -B tools/check_release.py` in a normal Windows desktop session for the additional tray checks. `Run-Battle-Logger.cmd` opens the source debugging interface.

GitHub Actions builds and tests on pushes, pull requests and manual runs. Download the **WH3BattleLogger-release-files** artifact and extract it. It contains the application ZIP and its update manifest. Attach **both files** to the GitHub Release; do not attach the outer Actions artifact ZIP. The workflow does not publish releases automatically.


For each public update, increase `src/version.py` and use the matching `vMAJOR.MINOR.PATCH` release tag (for example, `1.1.2` in the source and `v1.1.2` on GitHub). After building, `tools/package_update.py` produces these two files in `build/publish/`:

- **`WH3BattleLogger-Windows-x64.zip`** — the complete, clean app for new users and older updaters.
- **`WH3BattleLogger-update.json.gz`** — the compressed inventory of version, file sizes, checksums and byte locations used for smaller updates.

Always attach both files from the **same build**, with these exact names. The ZIP is generated from app-owned files only, excluding captures, keys, logs and backup folders. Do not recompress or change the ZIP afterward: the manifest describes the exact generated bytes.

Publish as the latest stable release; drafts and prereleases are not offered. The updater verifies GitHub's manifest checksum, verifies each changed file against that manifest, and checks that the packaged version matches the release tag. Missing metadata or a server that cannot supply partial downloads produces an error rather than silently downloading the full app. Publish a new version rather than replacing a package under an existing version. Pushing source alone does not distribute an app update. No GitHub token is bundled or required.

## Feedback

Report bugs through [Discord](https://discord.gg/v27y7AW7Kz) @Americanyutao
