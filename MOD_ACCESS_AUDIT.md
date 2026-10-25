# Workshop data-access audit — 2026-10-23

Investigated every field emitted by the current normalized collector, plus its derived statistics. No collector/report behavior changed. No mod was installed or run. “Documented” means a named game interface exists, not that our Lua implementation has passed an in-game test.

Coverage: 67 unit fields, 9 army fields, 6 sample-envelope fields. The damage-source entry also covers all 18 source/relationship counters. The audit script checks complete coverage against the actual reader fixture and validates every cited interface in the supplied game documentation.

## Conclusion

A normal Workshop collector can plausibly preserve most basic tracking and total/gold damage. Full parity is not established: native damage-source/friendly/self counters, unclamped healing budget and its unlimited flag, flat secondary ammo, and exact signed leadership are the main gaps. Winds UI queries discard fractional precision. None requires kernel access; the difference is what the game exposes to Lua.

The live CcoBattleUnit.BattleResultUnitContext builds a context around the same UNIT+0x68 result object used externally (saved 141e5fe28, already matched in the installed profile). This is stronger evidence for live damage/gold access than merely finding result-screen fields. Exact Lua lookup and object lifetime still need a battle test.

## Every collected field

Statuses: **documented** = named getter exists; **partial** = access or precision is incomplete; **no interface** = no equivalent found; **blocked by input** = dependent calculation; **derived** = calculable from exposed inputs; **provider** = collector bookkeeping.

| Scope / fields | Status | Mod access | Qualification |
|---|---|---|---|
| unit: `id` | provider | Assign a battle-local id using Lua unique_ui_id and retained incarnation bookkeeping. | Native address strings are implementation identifiers, not a required game stat. UID recycling/lifetime needs a summon/reinforcement test. |
| unit: `unit_key`, `portrait_path` | documented | CcoBattleUnit.UnitRecordContext / IconPath | Revision5 adds database and portrait identity; raw portrait source is normalized to the unit-card path. Runtime Lua comparison remains pending. |
| unit: `uid` | documented | unit:unique_ui_id() / CcoBattleUnit.UniqueUiId | Documented unique within the battle; retain identity through temporary missing observations. |
| unit: `name` | documented | CcoBattleUnit.Name and CustomName | Preserve custom-name precedence. Lua unit:name() is a script name, not necessarily the localized UI label. |
| unit: `army`, `alliance`, `side` | documented | ArmyContext.UniqueID / AllianceIndex; compare against the local alliance. | Use stable logical ids instead of memory addresses; normalize Lua versus CCO index conventions. |
| unit: `controlled` | documented | CcoBattleUnit.IsUnderMyControl | Test unit gifting and multiplayer shared control; player-owned and locally controlled are distinct. |
| unit: `alive` | documented | CcoBattleUnit.IsAlive | A missing unit or invalid target must not be converted to death. |
| unit: `cache_eligible` | documented | CcoBattleUnit.IsVisible reads the same +0x6f4 flag used by the reader. | This flag gates UI cache updates. Do not use it alone as opposite-alliance visibility. Existing saved registration 140238b90 and verified getter anchor establish the match. |
| unit: `cache_active` | provider | No documented getter for the exact +0x6fb update gate was found. | Collection-quality flag, not a player stat. A Lua provider needs explicit availability/freshness handling; IsAlive is not a proven substitute. |
| unit: `damage`, `gold_damage`, `kills` | documented | BattleResultUnitContext.DamageDealt / DamageDealtCost / NumKills | Live-unit result-context constructor 141e5fe28 points to the same UNIT+0x68 result data read externally; its installed match is already anchored. Runtime Lua query/lifetime still needs testing. |
| unit: `damage_by_source` | no interface | No exposed equivalent found for native result+0x20 six-source × three-relationship counters. | Covers ability, melee, missile, charge, melee_collision and other, each against enemy/self/ally. Recent-damage windows, effect definitions, kills and firing flags cannot reproduce these cumulative counters. |
| unit: `damage_sources_consistent` | blocked by input | Sum/check the six enemy counters against damage, as now. | Unavailable if the source table is unavailable; never mark a missing breakdown consistent. |
| unit: `health_percent` | documented | CcoBattleUnit.HealthPercent | Same UI-facing data family as the native collector. Validate off-camera/hidden-unit freshness and unavailable/dead units. |
| unit: `hp_cached` | documented | CcoBattleUnit.HealthValue | Same UI-facing data family as the native collector. Validate off-camera/hidden-unit freshness and unavailable/dead units. |
| unit: `hp_max_cached` | documented | CcoBattleUnit.HealthMax | Same UI-facing data family as the native collector. Validate off-camera/hidden-unit freshness and unavailable/dead units. |
| unit: `models` | documented | CcoBattleUnit.NumEntities | Same UI-facing data family as the native collector. Validate off-camera/hidden-unit freshness and unavailable/dead units. Prefer matching CCO entity counts; Lua soldier counts can differ in meaning for artillery/mounts/handlers. |
| unit: `models_initial` | documented | CcoBattleUnit.NumEntitiesInitial | Same UI-facing data family as the native collector. Validate off-camera/hidden-unit freshness and unavailable/dead units. Prefer matching CCO entity counts; Lua soldier counts can differ in meaning for artillery/mounts/handlers. |
| unit: `barrier_hp` | documented | CcoBattleUnit.BarrierHp | Same UI-facing data family as the native collector. Validate off-camera/hidden-unit freshness and unavailable/dead units. |
| unit: `barrier_max` | documented | CcoBattleUnit.BarrierMaxHp | Same UI-facing data family as the native collector. Validate off-camera/hidden-unit freshness and unavailable/dead units. |
| unit: `firing` | documented | CcoBattleUnit.IsFiringMissiles | Same UI-facing data family as the native collector. Validate off-camera/hidden-unit freshness and unavailable/dead units. |
| unit: `flying` | documented | CcoBattleUnit.IsFlying | Same UI-facing data family as the native collector. Validate off-camera/hidden-unit freshness and unavailable/dead units. |
| unit: `idle` | documented | CcoBattleUnit.IsIdle | Same UI-facing data family as the native collector. Validate off-camera/hidden-unit freshness and unavailable/dead units. |
| unit: `melee` | documented | CcoBattleUnit.IsInMelee | Same UI-facing data family as the native collector. Validate off-camera/hidden-unit freshness and unavailable/dead units. |
| unit: `routing` | documented | CcoBattleUnit.IsRouting | Same UI-facing data family as the native collector. Validate off-camera/hidden-unit freshness and unavailable/dead units. |
| unit: `running` | documented | CcoBattleUnit.IsRunning | Same UI-facing data family as the native collector. Validate off-camera/hidden-unit freshness and unavailable/dead units. |
| unit: `walking` | documented | CcoBattleUnit.IsWalking | Same UI-facing data family as the native collector. Validate off-camera/hidden-unit freshness and unavailable/dead units. |
| unit: `withdrawing` | documented | CcoBattleUnit.IsWithdrawing | Same UI-facing data family as the native collector. Validate off-camera/hidden-unit freshness and unavailable/dead units. |
| unit: `under_missile` | documented | CcoBattleUnit.IsUnderMissileAttack | Same UI-facing data family as the native collector. Validate off-camera/hidden-unit freshness and unavailable/dead units. |
| unit: `fatigue_state` | documented | CcoBattleUnit.FatigueState | Same UI-facing data family as the native collector. Validate off-camera/hidden-unit freshness and unavailable/dead units. |
| unit: `morale_state` | documented | CcoBattleUnit.MoraleState | Same UI-facing data family as the native collector. Validate off-camera/hidden-unit freshness and unavailable/dead units. |
| unit: `shattered` | documented | CcoBattleUnit.IsShattered | Same UI-facing data family as the native collector. Validate off-camera/hidden-unit freshness and unavailable/dead units. |
| unit: `spawned` | documented | CcoBattleUnit.IsSpawnedUnit | Same UI-facing data family as the native collector. Validate off-camera/hidden-unit freshness and unavailable/dead units. |
| unit: `hidden_raw` | documented | CcoBattleUnit.IsHidden | Same UI-facing data family as the native collector. Validate off-camera/hidden-unit freshness and unavailable/dead units. |
| unit: `primary_ammo_fraction` | documented | CcoBattleUnit.PrimaryAmmoPercent | Same UI-facing data family as the native collector. Validate off-camera/hidden-unit freshness and unavailable/dead units. |
| unit: `secondary_ammo_fraction` | documented | CcoBattleUnit.SecondaryAmmoPercent | Same UI-facing data family as the native collector. Validate off-camera/hidden-unit freshness and unavailable/dead units. |
| unit: `healing_ceiling_fraction_raw` | documented | CcoBattleUnit.MaxHealthPercentCanReplenish | Exact legacy display value, including the multi-model clamp in 143034ca0. Does not expose the new unclamped native healing budget. |
| unit: `regen_base_raw` | documented | CcoBattleUnit.HealthReplenishRateBase | Base replenishment-rate value only; it is not verified actual HP received per second. |
| unit: `grounded` | derived | not flying, preserving unknowns. | Same calculation as the external provider. |
| unit: `character_level`, `has_character_rank` | documented | CcoBattleUnit.CharacterRank / HasCharacterRank | Revision6 reads the exact rank getters. A missing rank is not reconstructed; report valuation explicitly assumes level 1 when needed. |
| unit: `fatigue_state_native` | partial | CcoBattleUnit.FatigueState uses the UI cache of native averaged state. | External reads native +3c10 next to points, avoiding UI cache lag. The state is a truncated mean of model states, not a tier derived from mean points. |
| unit: `fatigue_points` | no interface | No equivalent continuous-fatigue getter found for native +0x3c14. | The native value is mean retained-model fatigue points. FatigueState and FatigueName are discrete states, not a points counter. |
| unit: `result_hp` | documented | CcoBattleResultUnit.NumHitPoints | Native result counts; final HP sums current surviving model health. Require initialized final results. |
| unit: `result_initial_hp` | documented | CcoBattleResultUnit.NumHitPointsInitial | Native result counts; final HP sums current surviving model health. Require initialized final results. |
| unit: `result_models` | documented | CcoBattleResultUnit.NumEntities | Native result counts; final HP sums current surviving model health. Require initialized final results. |
| unit: `result_initial_models` | documented | CcoBattleResultUnit.NumEntitiesInitial | Native result counts; final HP sums current surviving model health. Require initialized final results. |
| unit: `result_exit_reason` | no interface | Native result +0xe4 classification. | No equivalent documented getter verified; leave ambiguous exits unresolved. |
| unit: `left_battlefield` | documented | BattleResultUnitContext.DidLeaveBattlefield | Same result+0xe2 getter. Observed true for destroyed Vampire Counts units too: it does not identify retreat rather than death. Reports use Dead / retreated. |
| unit: `awaiting_order_after_rally_raw` | partial | CcoBattleUnit.IsAwaitingOrderAfterRally | External collector logs the underlying +0x725 state without the getter’s local-control display filter. The exposed getter therefore is not equivalent for every enemy unit. |
| unit: `xyz` | documented | unit:position(), then battle_vector:get_x/get_y/get_z; alternatively CCO Position. | Y is elevation; X/Z are ground coordinates. Keep flying altitude and all-army extrema. CCO Vector4-to-Lua conversion needs a test; battle_vector avoids that dependency. |
| unit: `out_of_opponents_vision` | derived | Combine unit:is_hidden() and is_visible_to_alliance() for all opposing alliances. | Same intended per-opponent LOS semantics; CCO IsVisible alone is local-player facing. Test all enemies, off-camera units and multiplayer. |
| unit: `healing_budget_remaining_hp`, `healing_budget_unlimited` | no interface | No matching getter found for native stats+0x264 remaining budget or +0x268 unlimited flag. | Do not substitute 75% of max HP, the clamped display ceiling, base regen or configured heal amounts. The fixed summon starting ceiling does not recover its current budget. |
| unit: `healing_budget_ceiling_hp`, `healing_budget_remaining_fraction` | blocked by input | HP + native remaining budget; native remaining budget / maximum HP. | Exact multi-model values depend on the unavailable native budget. Legacy single-entity display ceiling permits a limited estimate, without the unlimited-budget guard. |
| unit: `primary_ammo` | partial | unit:ammo_left() documents a live ammunition count. | Candidate for the primary pool; the docs do not identify pool or count units. Must compare to native pool+0 current across infantry/artillery/mixed-ammo units. |
| unit: `primary_ammo_start` | partial | unit:starting_ammo() is the native initial pool candidate. | External collector reads native primary pool +4, initialized alongside current/max. Compare Lua count units at runtime. |
| unit: `secondary_ammo_start` | no interface | Native secondary initial pool +4. | No verified secondary starting-count getter in the exposed interface. |
| unit: `primary_ammo_max` | partial | unit:starting_ammo() documents starting ammunition. | Starting ammunition is not proven identical to the current native pool maximum (+8), especially after modifiers or capacity changes. |
| unit: `secondary_ammo`, `secondary_ammo_max` | no interface | SecondaryAmmoPercent exists, but no live secondary count/maximum getter was found. | CcoUnitLandRecord.SecondaryAmmo is a database value, not the live pool capacity. Percent × guessed capacity is not an equivalent measurement. |
| unit: `leadership` | partial | Candidates: UnitDetailsContext.StatContextFromKey(...).Value and MoralePercent. | No direct signed-current-leadership getter was found. MoralePercent subtracts a threshold and normalizes to best morale; for unbreakable units it can return the best value instead of raw current. A stat-panel Value needs key/meaning/clamp verification. Campaign CurrentMorale and database Morale are not replacements. |
| army: `id`, `alliance`, `side` | documented | CcoBattleArmy.UniqueID / AllianceIndex; compare to local alliance. | Normalize identifiers; original addresses are unnecessary. |
| army: `current`, `reserve`, `maximum` | partial | ArmyContext.WindsOfMagicPoolContext.CurrentWind / ReserveWind / MaxWind | Known getter machine code converts each stored float to an integer (cvttss2si). Suitable for whole-point charts, not equivalent fractional pools or +0.1/s generation analysis. Documentation leaves these return types Void. |
| army: `recharge`, `recharge_seconds_per_point` | documented | WindsOfMagicPoolContext.CurrentRechargePerSecond | Despite its name, the verified getter computes 1 / native recharge rate: seconds per point. Zero/infinite/disabled cases must remain explicit. |
| army: `recharge_per_second` | partial | Invert the verified reciprocal getter for positive finite values. | Reconstructed Winds/s, not a direct read of the native float; guard zero/infinite/disabled values and preserve provenance. |
| sample: `schema`, `kind` | provider | Emit the existing schema-1 sample envelope. | Provider metadata; no game access required. |
| sample: `sim_s` | documented | battle:time_elapsed_ms() / 1000 | Documented model time, matching pause/speed semantics. Mod timers can use simulation cadence; current external polling uses wall cadence, so schedules may differ. |
| sample: `unreadable_units` | provider | Count failed/absent Lua/CCO readings. | Provider-specific diagnostics; not a native gameplay counter. |
| sample: `battle_result` | documented | CcoBattleRoot.IsResultsPhase / ResultContext.IsDraw / IsLocalPlayerWinner | Winner/loser/draw is accepted only in results phase. Lua output must preserve the unknown outcome when capture stops earlier. |
| sample: `fatigue_rules` | no interface | No exposed getter found for the initialized runtime fatigue threshold table. | Supplied _kv_fatigue_tables provides base thresholds, but a bundled static copy cannot promise the same values as a modified runtime rule table. |

## Consequences for report statistics

| Statistic | Feasibility | Reason |
|---|---|---|
| State durations, including grounded/hidden/routing/missile fire | available | Boolean state inputs + simulation time; same sampled overlap/gap caveats. |
| First observed engagement (retired) | available | Inputs remain exposed, but the external logger no longer computes this statistic. |
| Movement path, occupancy, elevation, shared map bounds | available | XYZ + clock; travel-distance totals retired. Retain extrema before history downsampling. |
| Observed rallies and landings | available | Routing/flying transitions with current alive/shattered/withdrawal guards; still sampled. |
| Idling time after rallies | partial | Idle plus awaiting-order state and routing/shattered/withdrawal/alive guards. Exposed CCO waiting getter has an additional local-control display filter. |
| HP/barrier net falls and rises | available | Current values + consecutive timestamps; model gains/losses retired. |
| Total damage, gold totals, DPS and damage tempo | available | Result-context totals + timestamps. Live query needs runtime validation. |
| Firing-state versus other-state damage estimate | available | Total damage + firing state; does not recover native damage categories. |
| Ability/melee/missile/charge/collision/other damage and percentages | blocked | Native source table has no known exposed equivalent. |
| Friendly fire and self damage | blocked | Enemy/ally/self source-table columns have no known exposed equivalent. |
| Calculated damage taken and healing received, all units | blocked | Full implementation depends on the unclamped healing budget. Legacy single entities permit only the existing restricted estimate. |
| Summon damage before first observation | blocked | Assumed initial 1.75 ceiling is available, but current unclamped ceiling still needs the native budget. |
| Flat ammo timelines | partial | Primary count candidate exists; current maximum and both secondary fields remain unverified/unavailable. |
| Signed leadership timeline | partial | Requires verifying a signed raw stat-panel query; morale state/normalized percentage are already exposed. |
| Winds versus reserves chart | partial | Whole-point pool chart available; fractional precision is lost through known CCO getters. |
| Trade: gold damage / unit value | available | Gold numerator exposed; keep current manual/unambiguous static-price denominator. Exact actual purchase value remains unverified. |
| Last observed status; HP/model counts; summon labels | available | Documented CCO flags/counts; missing units remain unknown. |

## Important distinctions

- `MaxHealthPercentCanReplenish` is the old UI ceiling. Writer 143034ca0 clamps it for multi-model units, so subtracting current HP does not recover the native budget. A hardcoded summon starting ceiling cannot repair the missing current ceiling.
- `MoralePercent` (141e83cf4) subtracts a configured threshold before normalizing; unbreakable units can report their best morale instead of signed current leadership. Do not multiply it by database leadership and call it raw leadership.
- `CurrentWind`, `ReserveWind` and `MaxWind` getter anchors use `cvttss2si`, truncating stored float pools to integers. `CurrentRechargePerSecond` returns a reciprocal (seconds/point); invert only positive finite values.
- `DamageInflictedRecently` covers a recent window; summing overlapping samples double counts. Ability phase damage, vortex damage and weapon damage are configured amounts, not measured applied totals. None reconstructs friendly/self or native source attribution.
- Soldier counts from Lua and CCO entity counts need comparison for handlers/mounts/artillery. Use matching CCO counters where available.
- UI getters can share the existing cache-refresh limitations. “Lua can query it” does not establish that hidden/off-camera values are fresh.

## Export and diagnostics

global:ModLog is documented for battle and writes lua_mod_log.txt. This establishes a text export candidate, not our binary compressed/AES-GCM format. Verify release-build output, flushing, file limits and shutdown before promising automatic export. External conversion may compress/encrypt afterwards.

performance.* (monotonic_s, process_cpu_s, cpu_one_core_percent, cpu_window_percent, cpu_window_s, working_set_mib, private_mib, read_ms, read_calls, bytes_read, rate), schema/header/footer/gaps and timestamps are provider diagnostics. A Lua mod cannot claim per-mod Windows CPU/RAM or ReadProcessMemory counts; use callback/query/export costs and errors instead.

A Workshop mod plus the existing external viewer remains a feasible design. Keep the neutral schema and explicit capability list. Do not advertise full-stat parity until the missing interfaces and runtime checks are resolved. A companion memory reader would still be external software, even if accompanied by a Workshop item.

## Additional interfaces found (not currently collected)

- Ability uses/cooldowns/readiness: `BattleAbilityList`, `CcoBattleAbility.RemainingUses`, `HasLimitedUses`, `RechargeTimeRemainingSecs`, `CanCurrentlyPerform`, `IsActive`. Unlimited activation transitions are sampled, not guaranteed complete cast counts.
- Buff/debuff uptime: `ActiveEffectList`, effect start/duration/remaining time and phase record. Configured phase damage is not proof of actual HP damage.
- Distinct crumble/unstable flags: Lua `is_crumbling` / `is_unstable`. Rally waiting is now collected externally; the exposed getter’s local-control display filter is documented in the table above.
- Friendly kills: `CcoBattleResultUnit.NumKillsFriendlies`, distinct from friendly HP damage.
- Commands: `battle:register_command_handler` exists, but actor/target attribution and repeated-order coverage need investigation; this is not yet verified per-unit orders/minute.

## Required in-game verification

1. Resolve all units through Lua unique_ui_id and CCO without selecting them.
2. Compare documented CCO totals to existing external reader during a battle and after death/removal.
3. Check hidden/off-camera/enemy cache freshness, including opposite-alliance LOS.
4. Check summons, reinforcements, gifted units, transformations and identity lifetime.
5. Compare ammo_left/starting_ammo to native primary/secondary pool counters.
6. Resolve morale stat-panel key and test negative leadership, unbreakable and crumble states.
7. Compare fractional Winds and reciprocal rate with pause/fast-forward and zero-rate cases.
8. Check export in release builds, large rosters, campaign/custom/replay/multiplayer; no gameplay-changing API calls.

## Sources

- Supplied game docs: `../Local-files/documentation/ui/documentation.html`; `../Local-files/documentation/script/battle/{battle,battle_unit,battle_vector,common,global}.html`.
- Existing verified evidence: `build/field-verification.json`, `build/damage-accounting-evidence.json`, `build/healing-budget-evidence.json`, `build/report-field-evidence.json`, supported profiles and named saved Ghidra exports. No new executable/xref scan.
- [CA scripting docs mirror: common context queries](https://chadvandy.github.io/tw_modding_resources/WH3/battle/common.html#function:common:get_context_value), [battle unit](https://chadvandy.github.io/tw_modding_resources/WH3/battle/battle_unit.html), [UI context definitions](https://chadvandy.github.io/tw_modding_resources/WH3/cco/documentation.html).
- Exact field evidence, document fingerprints and coverage: `build/mod-access-audit.json`. Regenerate with `py -3 -B tools/audit_mod_access.py`.
