# Warhammer III Battle Logger — main directory

Release: release/WH3BattleLogger/WH3BattleLogger.exe (tray only). Debug: Run-Battle-Logger.cmd. Checkpoint: PROJECT_STATUS.md. Test steps: RUN.md.

| Location | Purpose |
|---|---|
| src/native_reader.py | External native adapter; returns schema-1 samples for a future Lua adapter to reproduce |
| src/roster.py, inspector_reader.py, memory.py | Copied meter/inspector foundations; never import or modify siblings |
| profiles/ | Supported game fingerprints, instruction anchors and verified field offsets |
| src/result_types.py, tools/verify_result_types.py | Native per-alliance result classification, guarded label mapping and bounded field verification |
| src/aggregate.py, damage_taken.py | Sampled durations, ceiling-based calculated damage taken with baseline/validity metadata, observed changes and totals |
| src/engagement.py | Archived first-engagement implementation; no longer used by the logger |
| src/logfile.py, recorder.py | Compressed AES-256-GCM stream, bounded disk queue, integrity checks |
| src/report.py, report_template.html, report_view.js, report.css | Encrypted log to standalone Main/category and Unit workspace report |
| MOD_ACCESS_AUDIT.md, tools/audit_mod_access.py | Complete Lua/CCO feasibility audit; exact query evidence and coverage in build/mod-access-audit.json |
| assets/game-assets.json, assets/game/, assets/unit-values.json, src/report_assets.py | Copied original-game PNGs, source hashes and offline embedding |
| tools/package_report_assets.py, tools/verify_unit_identity.py | Complete unit PNG/name catalog; bounded type-key and portrait-path verification for custom names |
| tools/verify_workspace_fields.py, tools/probe_workspace_fields.py | Bounded fatigue/rank/result/departure verification and one read-only supported-game sample |
| src/app.py, widgets.py, animation.py | Separate live debugging window; collection independent of redraw |
| src/release_app.py, tray.py, icons.py, paths.py | Windowless release lifecycle, native tray, LOG branding, packaged resources/capture paths |
| tools/build_release.py, check_release.py | Standalone Windows release build and packaged tray/report/encryption checks |
| src/worker.py, combat_window.py | Battle lifecycle, native combat boundary, one deployment baseline, cadence and CPU/RAM/read measurements |
| src/demo.py | Deterministic synthetic workload and demo report |
| tools/verify_fields.py | Small bounded reference-to-installed getter verification; no broad scan |
| tools/verify_damage_fields.py, probe_damage.py | Verify traced source/relationship counters and read one supported live-game sample |
| tools/benchmark_reader.py, startup_check.py | Bounded reader/aggregation/encryption fixture workload and real Windows startup check |
| build/field-verification.json | Exact getter/source matches for added fields |
| tests/ | Focused correctness, encryption, lifecycle and cadence checks |
| captures/ | Runtime encrypted logs, generated reports and private local logger.key |

Reference only: ../damage-meter/safe/ (release UI and safe LOS path); ../breaking-the-game/ (magic, position and raw healing ceiling); ../Ghidra Static/Function Exports/ghidra_function_exports/functions/ (targeted exports); ../Local-files/documentation/ui/documentation.html.

Active goal: validate logging efficiency and trustworthy field semantics externally before a mod collector. No in-game interface, spell damage attribution, charge count or objective contribution. Planned later fields remain listed in aggregate.UNSUPPORTED instead of guessed.

## Implementation decisions

| Proposal | Treatment |
|---|---|
| Bound uses: beginning minus end | Good sparse net-use measure once bound. Replenished uses need a separate adjustment; unlimited uses require activation/cooldown transitions. Ability lists are not yet bound externally. |
| Walk/run/idle/charge/limber | Use actual state fields. Combine idle animation variants through IsIdle. Limbering is artillery packing/unpacking, not a walking synonym. Charging, climbing and working lack a verified field here and remain unknown. |
| Damage while firing versus other states | Keep timing estimates under their literal labels. New captures also read native ability/melee/missile/charge/melee-collision/other HP credits by enemy/self/ally relationship; these do not depend on firing states. |
| First engagement | Retired at user request. Native firing/melee flags remain for activity timing. |
| Travel distance | Distance totals retired. Raw XYZ remains at the common sampling cadence for movement, occupancy and elevation graphs. |
| Healing ceiling minus HP | Raw ceiling fraction logged. Source143034ca0 uses (current HP + healing-budget value)/max HP, then an additional multi-model clamp. This is not proof that ceiling changes alone always measure incoming damage. Resurrection/model loss/max-HP changes need controlled tests. |
| Regeneration rate times duration | The base-rate getter exists and is logged raw. Units, affected-model scaling, caps, actual received healing and mitigation modifiers remain unvalidated. Dropping an entire interval when rate changes systematically undercounts; retain transitions and label any later integration an estimate. |
| Winds starting + generated - ending | Correct conservation idea only with both usable power and reserves and all external gains/losses accounted for. Reserve-to-power recharge cancels between those pools; positive sampled reserve changes miss simultaneous consumption. Raw pools/recharge and chart implemented; generated/spent totals remain unknown. |
| Models lost/resurrected | Derived gains/losses retired. Raw model counts remain for health/model timelines and native final results. |
| Friendly fire and barrier | Native source counters now include ally/self HP damage. Friendly kills remain unbound. The verified credit path absorbs barrier damage before updating enemy damage/gold credit. Retain barrier HP/max and observed changes; a controlled barrier-only hit test is still needed. |
| Crumbling/debuff damage | Uptime × configured rate can at best estimate potential effect damage, subject to resistance, target counts, caps, ticks and overlapping effects. Native effect lists and distinct undead/daemon states remain unbound. Never subtract guessed effect damage from actual HP loss. |
| Summons | Direct IsSpawnedUnit source verified and logged; later first appearance alone is not proof of a summon. Reinforcements are retained without relabeling them as summoned. |
| Landing count | Prefer observed flying-to-grounded transitions over elevation drops, which also occur on slopes. Flight durations and observed transitions implemented. |
| Rallies / waiting / cooldown ready | Routing exits estimate rallies. Revision6 logs the underlying awaiting-order-after-rally flag without the CCO local-control display filter. View7 idle-after-rally requires idle/alive and excludes route/shatter/withdrawal. Cooldown ready time remains unbound. |
| Orders/minute and targets | A target change is only a target change; it misses repeated orders and can be AI-driven. Exact orders need an actual command source. Not implemented from polling guesses. |
| Battle result | Revision7 reads winner/draw in results phase8 through roster +0xa0 (ResultContext +8); revision6 used the wrong pointer. Old outcomes need explicit corrections or stay unknown. Revision8 also reads native final HP/models and exit reason from the existing result block. Coherent initialized results across two simulation-time observations distinguish Dead/Retreated and preserve partial survivor HP; unresolved exits show Dead / retreated with last readable HP/models. DidLeaveBattlefield alone is true for deaths too. Missing roster rows alone never establish an exit cause. |

The report defaults to Main/category view. Unit view has a sticky card/name header and seven views: four graphs, chronological movement/occupancy, Winds, and time in state. Up to four mini graph windows can compare units; main graph slots avoid duplicate choices within that workspace; mini windows choose independently of the main graphs and one another. Popouts are regular independent windows; each originating graph slot allows one open popout and disables its plus button until that window closes. Graphs show the full recorded range and snap hover readouts to actual sample times/values; zooming is disabled. Values round to whole numbers except elevation. Graph choices and the Hide graph explanations checkbox persist in browser storage when allowed; all seven panels remain visible in fixed order. Detailed observations remain collapsible. Native totals, raw fields and derived estimates stay distinct. Encryption protects the capture at rest; it is not a delayed-release lock against its local owner. The separate local HTML report is readable.

## Verified damage-accounting trace

Saved-build14325bbc4 handles attacker/victim credit: applied HP after barrier absorption143070adc/14300fde8 is multiplied by victim-native+0x90, then142d77504 accumulates enemy damage at result+0xc4 and gold at+0xc8. It also accumulates a six-source × three-relationship table at result+0x20 (12-byte rows). Source names142d61924: ability, melee, missile, charge, melee_collision, other; relationships142d61854: enemy, same_unit, ally. Reader checks the enemy-column sum against the total and leaves inconsistent breakdowns unknown. Exact upstream construction of the cached gold-per-HP weight remains untraced.

Per-opponent candidates exist at native-unit+0x3490, histories+0x130/+0x170. However BOTH outgoing142f4bdd8 and incoming142f4bfa8 update per-opponent bucket+0x14; global incoming uses+0x10. Confirmed in machine code on both builds.142f55044/142f55478 rotate/clear buckets and prune opponents. The outgoing path also uses damage before barrier absorption while incoming uses damage after it. These records cannot be presented as a directional lifetime damage matrix. No guessed matrix implemented. Eleven routine matches and installed bytes: build/damage-accounting-evidence.json; read-only running-game anchor check: build/live-damage-check.json. Development-only decoder is local to build/decoder; runtime dependencies unchanged.

Winds unit correction from real capture: the existing CCO reciprocal named CurrentRechargePerSecond is actually seconds/point (10 corresponds to ~10s/power gain;6.25 to ~6.25s). Army+0xb4 holds the per-second rate. Revision2 emits explicit recharge_per_second and recharge_seconds_per_point; the old recharge key retains its reciprocal value for compatibility. Legacy external-native captures derive the rate during report conversion, labeled as derived; raw files stay unchanged. This verifies transfer-rate units, not generation/spending or battle-phase activation guards.

Revision-3 healing: verified143047e04,1430c8e98 and1430ae3b4 against both builds in bounded windows. Native+0x3d48 -> remaining healing budget+0x264; flags+0x268 mask0x01 disables budget consumption. Log remaining HP budget, unlimited flag and (when current HP/max are valid) unclamped HP+budget and budget/max-HP. Two additional reads /13 bytes per unit. Do not replace missing values with75% or turn budget changes into actual healing/damage taken without validating other writers. Existing UI ceiling+0x6cc has an additional multi-model clamp in143034ca0. New budget fields cannot be reconstructed from older logs.

Compact report revision: Simple is the first/default category; status is included there instead of a separate category. Damage breakdown percentages reference native enemy damage dealt; friendly/self can exceed100%. Other displays the sum of native charge/collision/other while preserving raw categories. Gold is beside damage dealt; DPS hidden. DamageTaken calculates C_initial−C_current, C=HP+remaining budget, with a fixed maximum-HP reference for fractions. Legacy multi-model UI fractions are excluded. Missing readings stay unknown; observed capacity/max-HP/source changes invalidate comparisons. Reference scripted heal paths can bypass budget spending, so this is an estimate. The revision3 real-capture reconciliation has small unexplained residuals (PROJECT_STATUS.md), not proof of exact attribution. No extra memory reads.

Revision4 graphs: four shared graph slots (view1/2/4/5), saved metric choices, with six raw damage counter options kept separate. Leadership is signed and centered on0; elevation_min is retained over all raw friendly/enemy samples. Native ammo pools and UI morale adapter verified in build/report-field-evidence.json; no broad scans. Healing received is derived as HP + calculated damage taken - starting max HP with a full-health baseline, algebraically budget spent. Trade uses explicit capture/manual unit_gold_value or an unambiguous base multiplayer price; exact battle upgrades are not guessed. Editable report values persist per battle. Report scope is shared by both views; original game trade icon included.

Revision11 deployment boundary: phases0/4 refresh one RAM snapshot without logging deployment. Conflict5..7 starts the capture, with initial values attached once; phase8 results remain recorded. Deployment positions and activity flags never seed movement, map/elevation bounds or durations. Identity-matched initial HP/models/healing ceiling/ammo and army pools remain available. Direct combat attachment uses its first valid combat readings.

Revision12: result-phase-only classification reads retain raw alliance/DB enums and qualify the colored result label after initialization, consistency and outcome checks. Unit cards follow main -> land-unit variants (including vehicle drivers); the complete9,384-PNG unit/portrait library is local, with only used images embedded per report.
