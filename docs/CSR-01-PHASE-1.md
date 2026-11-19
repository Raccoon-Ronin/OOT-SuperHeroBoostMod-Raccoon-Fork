# CSR-01 · Classic Shield Restoration

**Phase 1 is ready for founder gameplay validation.** Two source-level regressions are reproducible on v0.8.0. The candidate passes the corresponding checks and builds for Hookshot. The visual cause on the founder's particular frames and the in-game acceptance criteria remain unconfirmed.

| Reference | Value |
| --- | --- |
| Repository | [Raccoon-Ronin/OOT-SuperHeroBoostMod-Raccoon-Fork](https://github.com/Raccoon-Ronin/OOT-SuperHeroBoostMod-Raccoon-Fork) |
| Development branch | `feat/csr-01-manual-guard-phase1` |
| Baseline | v0.8.0, `main` at `bebce6093dee0fb864d98eebc1fb5661573e8664` |
| Implementation and regression checks | [ee15ca6](https://github.com/Raccoon-Ronin/OOT-SuperHeroBoostMod-Raccoon-Fork/commit/ee15ca686cc45d7122dd37225ea2302604827758) |
| Verified stock main build ID | `E0F3CCFAF50065AE4EA01EB5AEB13B1A45DA3348` |

## Input and guard state

The founder's local INI and the HookshotBuilder v2.3.2 host enum establish the following mapping. Each shoulder's hold-toggle setting was zero. The staged module and the local game image both had SHB manual shield enabled and SHB's R3 target swap disabled.

| Physical input | Hookshot INI | Logical Switch input | Phase 1 role |
| --- | --- | --- | --- |
| L2 | `pad_zl=15` | ZL, `0x100` | Native targeting |
| L1 | `pad_r=9` | R, `0x80` | Founder's quick-swap |
| R2 | `pad_l=16` | L, `0x40` | Guard while targeting |
| R1 | `pad_zr=10` | ZR, `0x200` | Founder's selected item |

The game reads a post-remap Npad buffer. In the inspected HookshotBuilder, `tools/host/nn_hid.c::npad_states` fills every returned sample with the same logical button state for that read. SHB's site 3 release dispatcher calls `controls_on_input` before `manual_shield_on_input`. The optional controls hook can exchange R3 and ZL or handle target switching. Manual shield consumes logical L while targeting and retains ownership of a press through release. The ordinary physical L2 press is passed to native targeting. Existing R3 cancel and optional retarget paths can synthesize ZL separately. [Control hooks](https://github.com/Raccoon-Ronin/OOT-SuperHeroBoostMod-Raccoon-Fork/blob/ee15ca6/features/controls/controls.c#L127) · [HID definitions](https://github.com/Raccoon-Ronin/OOT-SuperHeroBoostMod-Raccoon-Fork/blob/ee15ca6/core/hid.h#L6)

In Toggle mode, a valid attention-system lock makes guard eligible. In Hold mode, a held logical ZL also qualifies without a locked actor. A `LockOn*` action name by itself does not authorize guard. Scheduler hook 0 rechecks targeting, gameplay, carrying, and busy actions. A successful guard sets the player's guard flag `0x80000`, component flag `0x20`, and animation Bool14. Release clears them while preserving the target bit `0x100`. [Target eligibility](https://github.com/Raccoon-Ronin/OOT-SuperHeroBoostMod-Raccoon-Fork/blob/ee15ca6/features/manual_shield/manual_shield.c#L183) · [Scheduler dispatch](https://github.com/Raccoon-Ronin/OOT-SuperHeroBoostMod-Raccoon-Fork/blob/ee15ca6/core/hud.c#L2723) · [Guard decision](https://github.com/Raccoon-Ronin/OOT-SuperHeroBoostMod-Raccoon-Fork/blob/ee15ca6/features/manual_shield/manual_shield.c#L466)

## A · Shield rises on target input

The stock target-entry and update paths can set the player's guard flag. SHB already intercepts both stores and the indexed animation bool setter at `main+0x37BA100`. The child player graph selects `LockOn_Wait_ShieldGuard` or `LockOn_Wait` using Bool14, named `IsEnableGuardAnim`. The graph also uses this bool on a transition into lock-on. The name-based setter resolves a parameter index in `w8` and writes the same bool array directly. It bypasses the indexed setter. In a stock-instruction replay with Bool14 resolved, an incoming true overwrote a false guard decision under baseline hook coverage. This is a verified way to produce a mismatch between the guard decision and the pose. Identifying the writer on an actual L2-only frame still requires gameplay evidence.

The added hook gates that name-based value at `main+0x37BA094` for the current player interface and index 14. It resumes at `+0x37BA098`, preserving the stock store and its change counter. The scheduler now publishes a resolved animation interface even when the guard component is temporarily missing. A separate input timing fix retains a targeted, sampled L press until the next scheduler frame, so a tap released between two frame callbacks can guard for one frame. A blocked or lost-target frame discards that tap. [New writer](https://github.com/Raccoon-Ronin/OOT-SuperHeroBoostMod-Raccoon-Fork/blob/ee15ca6/features/manual_shield/manual_shield.S#L47) · [Verified hook word](https://github.com/Raccoon-Ronin/OOT-SuperHeroBoostMod-Raccoon-Fork/blob/ee15ca6/tools/hook_sites.py#L76) · [Resume address](https://github.com/Raccoon-Ronin/OOT-SuperHeroBoostMod-Raccoon-Fork/blob/ee15ca6/core/link.ld#L92) · [Input edge](https://github.com/Raccoon-Ronin/OOT-SuperHeroBoostMod-Raccoon-Fork/blob/ee15ca6/features/manual_shield/manual_shield.c#L318)

## B · Young Link's Hylian Shield disappears on guard entry

When guard first becomes allowed, v0.8.0 sets Bool14 and explicitly calls `native_draw_equipment(equipment, 4)`. The host regression reproduced that extra draw for a child with the Hylian Shield. It asks the equipment system to draw a shield already on Link's back as the native turtle guard starts. That timing is a candidate cause of the visible gap. A rendered frame capture is needed to attribute the flicker conclusively.

The change skips this one request when the existing `hud_is_child()` GameData read returns exactly 1 and player AS Int2 is 2. Read-only inspection of the player graph confirmed Int2 is `ShieldType` and that value 2 selects Hylian-specific clips. The age check is explicit. Adult, unknown-age, and other-shield cases retain the baseline draw policy. The native guard pose, hit logic, locomotion, and animation transitions stay under game control. [Equipment decision](https://github.com/Raccoon-Ronin/OOT-SuperHeroBoostMod-Raccoon-Fork/blob/ee15ca6/features/manual_shield/manual_shield.c#L499) · [Existing age accessor](https://github.com/Raccoon-Ronin/OOT-SuperHeroBoostMod-Raccoon-Fork/blob/ee15ca6/core/hud.c#L2009)

## Verification and rebuild

| Check | Result |
| --- | --- |
| Production C input and scheduler handlers with simulated game objects | Passed Hold and Toggle targeting, target-only, sampled tap between frames, sustained guard, release, loss of target, child Hylian draw suppression, adult/other-shield/unknown-age draws, busy/carrying, pause/death, missing guard component, option off, and auto-target alone. The same host test against baseline stopped at the unexpected child Hylian draw. |
| Actual AArch64 instructions, synthetic registers and interface | 288 cases passed across indexed and named writes. The new wrapper preserved all checked registers except its stock destination and preserved condition flags. A separate stock name-writer replay wrote 1 under baseline coverage and 0 under candidate coverage, with the change counter incremented in both. |
| Hookshot standalone `build_core.py`, LLVM 23.1.5 | Passed stock instruction checks, module linking, symbol and tail-call checks, and IPS generation. The build verified five input sites, four slot sites, one store site and four manual-shield sites. |
| Repository hygiene | `git diff --check` passed. `tools/check_no_game_data.py` fails on 13 documentation PNGs already tracked in the baseline. The branch adds source, tests, and Markdown. The host compiler also reports two existing discarded-qualifier warnings in `refresh_target_mode`. |
| Playtest | Pending founder approval. A compiled module and synthetic tests cannot establish shield visibility, hit registration, or perceived tap duration. |

For a reproducible developer build, use a clean branch checkout, Python 3, LLVM with AArch64 support (`clang`, `ld.lld`, `llvm-objcopy`, `llvm-size`, `llvm-nm`), and read-only access to the matching **stock** main. Set `SHB_LLVM` to the LLVM bin directory and `SHB_STOCK_MAIN` to the matching file. The repo's compressed-main loader additionally imports `lz4` and `zbic` for compressed inputs. From the repository root run the following. The feature list matches the normal standalone payload composition. Runtime feature choices are controlled separately.

```sh
python tools/build_core.py --features controls,manual_shield,stamina,songbook,button_mapping,quick_select --slots
clang -std=c11 -O2 -fno-strict-aliasing tests/manual_guard.c features/manual_shield/manual_shield.c core/hid.c -o build/manual_guard_test
./build/manual_guard_test
# With Unicorn 2.1.4 available to this Python environment
python tests/guard_writers.py
```

The build produces a matched `subsdk9` and build-ID IPS under `build/native/exefs/`. Hookshot uses the standalone variant. To test after founder approval, stage the **new pair** into a development payload using the standalone staging convention in `tools/make_release.py` and rebuild a separate Hookshot game copy with its matching builder. A settings-only apply or packaging the old CI payload cannot incorporate the added executable hook. Keep the working install, saves and controller INI out of this step. [Release staging](https://github.com/Raccoon-Ronin/OOT-SuperHeroBoostMod-Raccoon-Fork/blob/ee15ca6/tools/make_release.py#L60) · [Hookshot variant selection](https://github.com/Raccoon-Ronin/OOT-SuperHeroBoostMod-Raccoon-Fork/blob/ee15ca6/app/recomp.py#L416)

## Founder acceptance checklist

- [ ] With existing mappings and manual shield enabled, test Hold and Toggle targeting. Press L2 alone from rest. Verify target acquisition and the targeting stance with the shield down. In Hold mode, also test the camera without a locked actor.
- [ ] While targeted, tap R2, hold R2 for several seconds, then release it. Verify a brief guard, a sustained guard, and a lowered guard respectively. Targeting must persist through R2 release. Drop targeting while holding R2 and check that the item selector does not open mid-press.
- [ ] With Young Link's Hylian Shield, capture guard entry, hold, release, and repeated taps. Step through the recording frame by frame. The shield should remain visible on his back and the existing turtle pose and movement should match baseline.
- [ ] Under comparable conditions, check an incoming hit while guarding and with L2 alone. Record pose and block reaction separately. Check another child shield and Adult Link if already available to the tester.
- [ ] Check L1 quick-swap, R1 selected item, menu navigation, a busy item action, and returning from pause. Compare manual shield disabled against stock-style shielding under the same settings.

If target-only still raises the shield, record the age, equipped shield, targeting mode, L2/R2 states, whether a target was acquired, and the first affected frame. If a diagnostic trace is available, correlate `g_ms_l_raw`, `g_ms_allowed`, the player interface, and the writer of Bool14. If the flicker persists with zero SHB draws on entry, trace native equipment visibility at that frame. Either result would narrow the next change without guessing a flag or changing animation transitions.

## Risks and rollback

The hook addresses and animation indices belong to the verified build. A physical tap must reach at least one HID read. A one-scheduler-frame request can still be visually subtle. Other animation or equipment writers could affect the final pose. Adult compatibility is covered at the decision level and awaits a gameplay comparison.

The development work only produced files in the workspace. To return a clean checkout to the baseline, switch to `main`. To retain branch history while backing out the source change, run `git revert ee15ca6` on the feature branch. If an approved test copy has been rebuilt, restore that copy's complete pretest build or rebuild it from the baseline module/IPS pair. Switching Git branches alone does not roll back a compiled Hookshot executable. Founder approval is required before merging, installing into the working game, or extending scope.
