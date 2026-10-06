# Zelda Quest campaign expansion

## Current checkpoint, 2026-10-06
- **Roadmap:** all eight regions planned, with mandatory review after each complete region. See "Eight-region roadmap and stopping points" below.
- **Active scope:** Publish current 5m57s slice, then pause at Ryan's request. M1 remains incomplete; no further region authoring while paused.
- **Measured release content:** 5m57.48s at normal speed, zero deaths, including Sawmill and Watchwood. Remaining M1 gap: 14m02.52s. No padding or replay counted.
- **Current release:** Watchwood/Sawmill added to ZELDA WOODS. Focused tests, fresh-process stages, actual simulator autosaves, lint/compile and visual checks pass. Final shipping suite/review and push receipt are recorded at the end. Real local configuration remains preserved.
- **After the break:** Connected inner shrine is next, beginning with a constrained simultaneous-plate Seed Vault. Only temporary geometry experiments exist; no shrine content or later region implemented.
- **History below:** earlier durations and test totals describe their own snapshots, not current acceptance. M1 is not complete.

## Goal and release gate
At least 120 minutes of active autonomous adventuring before the completed campaign repeats. Eight distinct regions, designed progression and bosses, save/resume between carousel slots and restarts. Duration excludes other demos, idle waiting and repeated deaths. No two-hour-content claim until measured against finished content.

## Phase one, approved 2026-10-06
Build the campaign foundation locally, author one complete first region, then check in before authoring the other seven regions. Do not push the unfinished expansion. Preserve the published two-room demo and unrelated Skeleton/config changes.

### Referenced implementation plan
1. Data-driven areas and connected progression: extend QuestGame (src/display/zelda_quest/game.py) rather than duplicate its BFS, combat, timers and pickups. Follow Dungeon FloorMap (src/display/dungeon/worldgen.py) for map-local spawn and objective data.
2. Scrolling renderer: generalize Renderer (src/display/zelda_quest/render.py) to map-sized backgrounds, a clamped hero-following viewport and fixed HUD. Reuse original sprites and shared font utilities.
3. Campaign state: a small three-area development route proves transitions, persistent objective progress, active-time accounting and checkpoint recovery. It is NOT a finished region or two hours of content.
4. Versioned JSON saves: atomic same-directory temporary file plus replace, following src/display/living_world/persistence.py. Validate loaded state and keep unreadable/incompatible files intact. No pickle; no saves per frame.
5. Separate local preview runner with the existing run(matrix, duration) lifecycle (src/display/zelda_quest/__init__.py and src/app_state.py). Save on exit and periodically; resume in another process. Do not change published registry routing yet.
6. Tests: preserve the existing 118 demo tests, cover connected maps, camera edges, exact save/resume, checkpoint rollback, bad saves, interrupted writes and stop/duration handling.

### Verification
Run pytest SERIAL ONLY because tests/conftest.py rewrites real config. Snapshot config bytes before testing. Run full suite with input tests explicitly ordered first exactly once, not twice via overlapping paths. Flake8 and compileall, real simulator preview, independent review. No standalone build target exists.

## First-region implementation gate
- Forest village, branching woods and multi-room shrine must be visibly distinct, with exploration and a traversal-changing item rather than a repeated room or idle timer.
- A puzzle must require a real state transition to unlock a route; the boss must demand a mechanic beyond eight ordinary hits. Autonomous replay must finish without manual input.
- Save/resume mid-puzzle and at checkpoints, preserve route validation and map camera; test obstacle edges, objective ordering, progression and a full active-time measurement.
- Show the measured region and a real visual preview to Ryan before expanding the other seven. First milestone is 20 complete minutes; later regions have provisional 15-minute content allocations. A 90-150-second sequence is only a prototype, not a complete region. Published main remains on the short demo.

### Referenced first-region change plan
1. world.py: five authored forest areas (village, ordered lost-woods clearings, shrine root hall, vine court, treant lair), reachable-item validation, and a boots-gated vine tile.
2. game.py/campaign.py: autonomous puzzle goals, boots acquisition and persistence, treant phase change with one sapling reinforcement; preserve legacy QuestGame behavior.
3. persistence.py/render.py: validate every added flag, bump unpublished content version, draw vines/boots/treant and puzzle feedback.
4. tests/test_zelda_campaign.py: adjust route assertions for authored five areas and add objective order, locked passage, checkpoint/equipment, mid-puzzle save and autonomous-completion tests. Run configured lint, compileall, serial full suite, simulator preview and measure active seconds. If measured active gameplay is under the 20-minute first-region milestone, keep first region marked incomplete and expand designed content before seeking the promised quality check-in.

## Later phases
- Phase two: first complete region with exploration, puzzles, equipment and distinctive boss; visual/pacing review.
- Phase three: seven additional regions and campaign progression.
- Phase four: measured full-campaign runs, save/restart/soak verification, only then publishing.

## Status
- [x] Research and referenced plan
- [x] Phase-one implementation (development route only)
- [x] Phase-one verification and preview: 1,383 full-suite tests passed serially (input first); configured flake8, compileall and simulator preview pass. Three-area route 36.43 active seconds with no deaths. Config bytes unchanged; independent read-only review found two latent risks (undersized maps produce black padding; subclass phase-expiry depends on base dt clamp) and one full-map copy cost, to address before broader campaign authoring.
- [ ] First complete region
- [ ] Remaining regions
- [ ] Measured two-hour campaign and release

## Greenwood mechanics slice, measured 2026-10-06
- Implementer timed out; lead recovered and stabilized partial code directly. Five areas complete in 124.20 active seconds at fixed 60-Hz simulation, zero deaths, 230 distinct visited tiles. This is not a complete first region.
- 152 focused tests passed; configured lint and compileall pass after test-spacing correction. Independent JSON roundtrip every 137 frames passed 28 times; four fresh process resumes matched uninterrupted state exactly. Full suite with explicit unique input-first test list now running.
- Fixed 24-Hz repeated boss deaths at root via campaign-only fixed-step simulation with saved fractional time; legacy demo timing unchanged. Occupied reinforcement spawns now choose nearest free land instead of silently dropping the boss phase.
- Visual contact sheet inspected: village/shrine palettes distinct, but current scope is sparse. First-region gate remains open.
- Next authored batch: actual village quest interactions and persistent objective-driven branching routes, then real switch/block/hazard shrine mechanics. Content design notes: ~/.aki/tmp/greenwood-content-expansion.md. Do not multiply five short rooms to meet duration.

## Village and shrine content batch
- Corrected full suite completed: 1,416 tests passed in 179.66s with explicit unique input-first paths and unchanged config hashes, before this content batch.
- Added real village request/three supply pickups/delivery/map reward, prerequisite journal, autonomous objectives, visible interactions and exact save/resume. Village grew from 16 to 38 active seconds; total 146.40 seconds before stone puzzle.
- Added actual stone pushing and pressure plate in Root Hall, boots pedestal unreachable until solved. Legal push-state search, mid-push persistence and checkpoint rollback covered. 164 focused tests passed.
- Extracted phase-expiry dispatch to eliminate fragile base/subclass dt interception. New checkpointed content_seconds excludes replayed failed attempts while active_seconds remains viewing time.
- Still not complete: substantial designed exploration/branching dungeon content and 15-minute region budget remain. Other seven regions and publishing remain untouched.

## Next batch: Vine Court sluice routing
- Extend the authored Vine Court into two water-separated wings: boots reach the west wheel, draining the north canal exposes the east wheel, and the east wheel drains the treasury crossing and opens a return shortcut. Combat and pickups remain real and are not respawned. No movement/timer slowdown.
- References: world.Area map/landmark validation; campaign._objective and _contacts; puzzle.next_stone_action legal traversal; journal.VillageJournal prerequisite validation; persistence._state exact snapshot validation; preview.CampaignRenderer campaign-only art.
- Add campaign-only sluice state, reachable-threat objective selection, dynamic crossing art, and strict save/checkpoint validation. Keep five areas and the published run() unchanged.
- Verify legal control order, actual route changes, trapped-side prevention, unreachable-enemy progress, mid-control fresh-process resume, checkpoint rollback, autonomous completion at multiple frame rates, configured lint/compileall, simulator rendering, full serial input-first suite, and bytewise config audit.
- This remains a content batch, not completion of the 15-minute first-region gate.

### Sluice batch measured results
- Added two prerequisite water-wheel interactions, three physically blocked/drained crossings, a boots-only approach, treasury wing, and opened return shortcut in authored Vine Court. Inaccessible enemies now yield to a reachable puzzle objective instead of freezing the hero.
- 175 focused tests pass. Configured flake8, whole-source compileall, git diff --check, and a real RGBMatrix simulator resumed-preview run pass. No standalone build target exists in this Python application.
- Whole route: 174.70 active/content seconds (2m54.7s), zero deaths, 319 distinct tiles, 39 exact JSON roundtrips. Vine Court is 42.20 seconds. Three fresh processes at sluice stages 0/1/2 exactly matched uninterrupted execution.
- Published-game differential check against 4ff00b4: all legacy actor/progression fields match for 18,000 frames across ten seeded 60-second runs. Nothing pushed or deployed.
- Visual contact sheets regions.png and sluice-stages.png inspected; water changes and controls are visible beneath actors, HUD stays fixed. Artifacts: ~/.aki/tmp/zelda-region-verification/.
- External adversarial helper initially used a 30-Hz update across a 60-Hz respawn boundary and counted one legitimate resumed tick; corrected the helper to inspect the exact respawn tick. All three adversarial checks pass; no gameplay timing change needed.
- Independent review pending. First region remains incomplete; this is real mechanic progress, not a 15-minute region or a two-hour campaign.
- Full serial suite: 1,439 passed in 215.35s, config hashes unchanged. Subsequent adversarial probe found malformed but in-bounds saves could strand the hero on the far side of an undrained canal. Fix validates actual start-to-hero connectivity using the existing legal walking solver; add two preserve-invalid-save regressions, then verify the changed snapshot.
- Post-fix focused suite: 177 passed in 6.23s; configured lint and whole-source compileall pass. Fresh-process stage 0/1/2 state remains exact. Full-suite verification of this changed snapshot is running serially.

## Remaining first-region content, not yet implemented
- Connected return travel and persistent per-area state are the next structural prerequisite. Eleven-visit return travel is implemented without respawning cleared encounters; validation and visual review continue.
- Author three genuinely different Lost Woods branches, a telegraphed inner-shrine hazard/miniboss encounter, additional boots-enabled grove objectives and distinct shrine encounters. Tree and village restoration are implemented, but still too brief.
- Keep movement at 0.30 seconds per step, combat pacing unchanged, and monotonic unlocks. Measure unique objectives and non-replayed content time after each batch. Do not inflate the region by appending copies of rooms.
- Local preview content version is forest-return-7. Older unpublished saves are preserved and rejected, never overwritten; this is not a migration for a published campaign.
- Check in before expanding to the other seven regions or changing published carousel routing. No expansion commit, push or device deployment has occurred.

## Persistent return-travel batch, referenced plan
1. Close independent-review gaps: require the solved stone whenever boots are owned, and reject pickups on undrained crossings. Existing patterns: persistence._state position/flag checks and tests/test_zelda_sluice.py invalid-save preservation.
2. Replace campaign room+1 progression with an explicit authored journey through the SAME five area objects. Keep persistent room-local chest/gate/sigil/enemy/pickup state, while equipment, journal and content clock stay global. Reuse capture/restore actor serialization, not executable deserialization or copied room definitions. References: campaign.capture/restore/_advance_area and game._load_room.
3. Add purposeful return objectives using the journal Errand prerequisite pattern: recover forest spirits after boots, report grove restoration to the elder before entering the treant lair, then return the relic to restore Greenhollow. Walk to real exits; no respawn of cleared enemies/chests or lost equipment. Explicit arrival tiles and next-area labels replace inferred room+1 transitions. No duration claim from return traversal alone.
4. Store journey index and per-area state in checkpoint snapshots, validate visited-room cache and ordered journey against the authored route, and keep JSON roundtrips exact. Bump unpublished content version. References: SaveStore atomic writes, VillageJournal validation, CampaignRenderer world-layer scenery.
5. Add tests for cleared-room revisit persistence, distinct new return interactions, carried boots, checkpoint rollback on revisits, invalid cached state/route rejection, full autonomous completion and exact restart. Run focused tests/lint/compile after the batch, then serial full suite and offline render/time measurement. Preserve published QuestGame run and unrelated Skeleton/config. The current full-suite snapshot must finish before code edits.

### Return-travel batch results
- The pre-batch full suite passed 1,441 tests in 208.35s with unchanged config hashes.
- Implemented eleven explicit visits through the same five authored areas. Cleared encounters, open chests and lit sigils persist; boots unlock three spirit clearings. Elder teaching, tree restoration, treant victory, relic return and final village restoration form one non-repeating journey.
- Full route measured 243.53 active/content seconds (4m03.5s), zero deaths, 351 distinct tiles, 54 JSON roundtrips. Eleven fresh-process resumes matched exactly. Six interaction frames visually inspected in journey-returns.png. Duration remains well below the complete-region gate.
- Independent-review save gaps fixed: flooded pickups rejected and boots require solved stone. New journey tests exposed encode/decode ownership leakage of completed_areas/checkpoint; fixed with snapshot copies instead of weakening tests. Initial new suite: 12 failed, 189 passed; corrected focused verification passed: 202 tests, lint, compileall. Full suite running input-first with config audit.
- First region still incomplete: meaningful new branching exploration and shrine hazard/miniboss encounters remain, not more return loops. No other regions or published routing changed.

## Proposed next content: Greenwood branching obstacle, pending full-suite snapshot
- Do not author a second generic sigil tour. Make the outward Lost Woods route three mechanically distinct branches: an existing ordered runestone clue, a spring-fed bridge controlled by a reachable lever, and a movable fallen log solved by legal push actions. Keep final guardian clearing tied to clearing the two obstacles. The current sigil positions are cues, not repeated runestones.
- Use real woods tile connectivity (22x16, 216 gate-closed reachable tiles) and existing puzzle.next_stone_action, Area schema validation, CampaignGame.passable/_objective/_contacts, CampaignRenderer._scenery, and persistence._state. Add per-branch state to room cache and checkpoint so returns show changed terrain without replay.
- Before editing, confirm current serial full suite and read-only reviewer findings. Measure the altered route at unchanged 0.30s per tile and stop short of claiming completion if below the 15-minute region target.
- Map proof: sealing (11,14) cuts off east rune (18,1), and sealing (4,7) cuts off north-west rune (5,1); both sealings keep first rune (5,13) and near-side controls reachable. The initially proposed west log at (4,7) CANNOT be solved by a one-tile north push: (4,6) remains the sole passage, so moving it there keeps the branch shut. Do not ship that design. Adding lateral recesses at (3,7)/(5,7) creates an immediate bypass around the log, so that variant is also invalid. Choose a different obstacle or redesign the forest topology and prove no bypass with BFS. This is a graph-discovered design blocker for that candidate only, not the region goal.

### Independent read-only return-journey review, triage
- Confirmed actual data loss: finished game.wins=1, decode(encode(game)).wins=0. Preserve wins across saves; runs is always 1 for campaign sessions (not incremented by room travel), so avoid asserting historical run count beyond the first. Add direct post-boss regression.
- Clock split is intentional on deaths: active_seconds tracks total successful/failed play, content_seconds rolls back to checkpoint on death. On no-death runs they are equal; do not remove the second clock. Add explicit failed-attempt assertion if new tests touch it.
- SPIRIT_TILES derived from JOURNEY[5] is index-fragile; derive from rescue-kind Errands and validate positions, not from route order. Room-entry checkpoint rewind is current intentional contract: cover first-pass sigil/boots rollback and consider finer checkpoints only with a real design reason.
- Incompatible preview saves are deliberately preserved, never overwritten; logger.warning is the current signal, not a silent code path. Preview UI status for unsaved sessions is worth authoring before release, not auto-delete/auto-migrate unpublished saves.
- Reviewer log-raft proposal is a possible puzzle, but unverified and may conflict with the monotonic sluice solution. Do not implement without graph proof. Existing west-log design was rejected as unopenable or bypassed.
- Post-return full suite: 1,466 passed in 265.92s with unchanged config hashes. Independent review then identified and the lead reproduced wins resetting from 1 to 0 after a save/load. Fixed persistence and added direct regression, plus removed magic JOURNEY[5] spirit derivation. 203 focused tests, lint and compileall pass; final suite for these two fixes remains due after the next coherent content batch.

## Proposed Root Hall guardian pulse, design complete pending verified baseline
- Convert the existing Root Hall upper guard to an existing guardian actor (same sprite/health bar, no new art system), and add a campaign-only root pulse after the stone pressure plate has opened the boots pedestal. The pulse has explicit safe tiles on the actual central hall, lights before striking, and drops the guardian's bark shield only after the hero occupies a safe tile. The autonomous hero must intentionally route to safety, then attack during the short exposed window.
- It is distinct from a push puzzle, sluice state, sigil order and ordinary eight-hit combat: player logic depends on positioning and a telegraphed timing state. It does not insert an idle delay: pulse travel and safe routing alter tactical decisions. Guardian cannot be killed by ordinary path-to-adjacent attack until shield drops.
- Persist pulse clock/exposure and safe-tile result in the current Root Hall local cache/checkpoint, validate ranges and guardian-state consistency, then render roots/safe runes beneath actors. Tests: pulse cannot damage a safe hero, an unsafe hero takes exactly one hit per pulse, shield blocks before safety and permits damage after, full autonomous root-hall clearance, JSON mid-pulse/resume, death rollback, return room remains cleared.
- Keep 0.30-second movement and existing treant mechanics. Do not edit until the post-review full-suite result is available.

## First-region completion scope after guardian batch
- Current measured route is 4m03.5s, versus the 15-20 minute first-region gate. One more micro-mechanic cannot close that gap honestly. Do not attempt to do so with waits, high-health enemies, repeated return legs or room copies.
- After the Root Hall guardian pulse is stable, extend Greenwood itself with 4-6 authored shrine spaces, not new campaign regions: flooded archive (sluice ordering), root observatory (telegraphed hazard), seed vault (multi-object push/state puzzle), thorn gallery (boots route choice), guardian sanctum, and a post-boss restoration approach. Each needs distinct topology/objective/art state, persistent completion and restart tests.
- This is still inside phase-one first-region authorization. Do not publish or author the other seven named regions before an inspected, measured first-region check-in.

### Guardian activation refinement
- Avoid a circular dependency: Root Hall stone solver only operates after ordinary enemies are gone, so making an initial guard invulnerable until the stone is solved would deadlock. Instead keep initial guards; acquiring the boots awakens one dormant stationary guardian at (8,1), after guards/puzzle are cleared. Use existing guardian sprite, four HP, not HP inflation.
- Safe runes alternate (7,2)/(9,2). Each warning lasts 90 fixed ticks and exposes the guardian for 72 ticks only if the hero is on the indicated rune at impact. Failed positioning causes exactly one damage event, then another warning. Existing 60-Hz simulation makes save/resume exact. Guardian does not chase or deal incidental contact damage; its root pulse is the attack.
- Guardian fight state is global Root Hall progress like stone and sluice, saved in capture/checkpoint. Its actor is persisted in the existing room-local enemy cache. No additional rooms, waits or legacy-engine changes are needed for this batch.

- Verified pre-pulse baseline: 1,467 full-suite tests passed in 211.89s, config bytes unchanged. Isolated real-map tactical prototype completed four alternating safety/exposure cycles with zero deaths, 251.33 seconds total. Integrating now with strict state/actor consistency and save/resume tests.

### Guardian integration verification
- Initial 203 existing regression tests passed after integration. Added 25 targeted tests covering all eight warning/exposure stages, safe/unsafe damage, four shield cycles, real autonomous return persistence, malformed saves and death-clock rollback; all passed.
- Direct adversarial probe found dormant/cleared pulse cycles accepted impossible histories (dormant cycle 1, cleared cycle 0). Constrain mode-specific cycles in RootPulse, the single state-validation boundary, and add seven rejection cases. No timing or published-route changes. Full current-snapshot verification and offline pulse restart/render checks follow.

- Guardian baseline full suite passed 1,499 tests in 244.24s with unchanged config bytes. Pulse statement coverage 100% (32 tests); separate coverage run reported a pygame/NumPy reload warning, not reproduced by the non-coverage full suite.
- Offline route: 251.333 seconds, zero deaths, 355 distinct tiles, 56 exact JSON roundtrips; eight fresh-process pulse stages matched exactly, equal completion time at 24/30/60 Hz. Real 31-second simulator session completed periodic and final atomic saves. Legacy differential still matches 18,000 frames against 4ff00b4.
- Visual review confirmed guardian health bar was half-full at spawn (legacy max 8 versus campaign max 4). Shared GUARDIAN_HEALTH with campaign renderer override fixes scale while preserving legacy default; four real-pixel tests added.
- Independent reviewer found impact evaluated before same-tick movement. Lead reproduced from a valid save: arriving on safe rune still lost a heart. Resolve pulse after base movement/contact update, explicitly entering defeat on lethal impact. Added exact-arrival and same-tick fatal/frozen-defeat regressions. Final verification now required for these two fixes.

## Active milestone, Ryan confirmed 2026-10-06
Deliver the first **20 minutes of complete content** before fleshing out the full two-hour campaign. This supersedes the earlier 15-20 minute first-region budget: acceptance requires at least 1,200 measured seconds of normal-speed, non-replayed content, not a partial mechanics demo. Implementation of later regions stays deferred until its review gate; planning covers all eight now.

### Focused content plan
1. Finish guardian verification, then prioritize authored content over further foundation work unless a demonstrated defect blocks content. Current playable slice is approximately 4m11s, leaving approximately 15m49s of genuinely new content.
2. Build a coherent first chapter with an opening village problem, woodland exploration, connected multi-room shrine, meaningful equipment unlock, boss and visible resolution. Expand these connected chapters rather than assembling unrelated demonstrations.
3. Planning allocation, NOT measured content: village/outskirts 3 minutes; branching woodland 5 minutes; outer shrine and traversal unlock 5 minutes; inner shrine challenges 5 minutes; boss and resolution 2 minutes. Rebalance after actual runs, never slow movement or insert waits to meet these allocations.
4. Next authored batch: woodland branches with real topology-changing obstacles and visible consequences, followed by connected shrine spaces. Reuse Area reachability (world.py), explicit visits and local state (journey.py/campaign.py), prerequisite errands (journal.py), legal pushes (puzzle.py), and existing sluice/pulse examples. Prove each blocked/open route with connectivity checks before authoring its autonomous solution. Rejected bypassed/unopenable log layout remains rejected.
5. Each batch includes content, art feedback, saved state and meaningful tests together. Measure completed normal-speed route and report added content seconds. Keep cleared encounters cleared, death replay excluded, save/resume exact and normal carousel timing unchanged.
6. Complete means a coherent beginning-to-end 20-minute autonomous chapter, inspected visuals/pacing, tested checkpoints/restarts, full serial suite/lint/simulator verification, and no placeholder objectives. Stop for Ryan's chapter review before building the remaining campaign. No publication or deployment authorized by this milestone.

- Latest guardian focused verification: 241 tests passed, full-style campaign lint and source/test compileall passed. Full-suite verification for final health-bar and impact-order fixes is next; the prior 1,499-pass snapshot does not cover those fixes.

## Eight-region roadmap and stopping points, clarified 2026-10-06
Plan the entire adventure now; implement and review it in complete, bounded chapters. The 20-minute opening is the first milestone, not a reduction of the eight-region plan. Region themes below preserve the earlier campaign proposal. Equipment and encounter details are design proposals, not implemented or separately approved features.

### Campaign arc and progression
Restore the forest, follow the disrupted waterways into the wider world, recover the means to cross each damaged landscape, then use those accumulated abilities to reach and resolve the dark castle. Each region has an opening problem, exploration with changed routes, a multi-room dungeon, a mechanic-specific boss, and a visible local resolution. Later encounters combine earlier abilities instead of discarding them or merely increasing enemy health.

| Stop | Region | Authored content and distinctive mechanic | Progression proposal | New-content allocation | Cumulative target |
| --- | --- | --- | --- | --- | --- |
| M1 | Forest village and Lost Woods | Village recovery, branching woods, stone/sluice shrine, guardian positioning, treant and restoration | Vine boots open thorn routes; restored grove opens the river road | 20 min | 20 min |
| M2 | Riverlands and flooded ruins | Broken bridges, connected canal basins, controllable currents and a floodgate boss | Current charm enables deliberate water traversal, exposing the canyon approach | 15 min | 35 min |
| M3 | Desert canyon and buried temple | Split canyon paths, movable shade/reflected-light puzzles, buried chambers and a mirror-armor boss | Reflector opens light seals; temple exit reaches mountain foothills | 15 min | 50 min |
| M4 | Mountain passes and crystal mines | Elevation changes, anchor routes, redirected mine carts and a crystal guardian | Grapple creates actual shortcuts and chasm crossings; mine descent reaches marsh | 15 min | 65 min |
| M5 | Marsh and haunted crypt | Flooded causeways, revealed spirit paths, linked crypt chambers and a possession-based boss | Spirit lantern reveals traversable hidden paths; released spirits reveal the northern route | 15 min | 80 min |
| M6 | Frozen lake and ice fortress | Sliding movement, controllable ice barriers, reflected beams and a freeze/thaw boss | Frost cleats change stopping/traction choices; fortress opens volcanic pass | 15 min | 95 min |
| M7 | Volcanic caverns and foundry | Routed coolant, moving forge machinery, heat-safe crossings and a foundry titan | Heat ward opens specific hot crossings; restored forge provides castle access | 15 min | 110 min |
| M8 | Dark castle and final boss | Interconnected castle wings combine water, light, grapple and spirit abilities; distinct final boss phases and ending | Resolve the campaign with visible world consequences before any repeat | 15 min | 125 min |

These are planning allocations, not measured content. The 125-minute outline leaves a small margin above the 120-minute full-campaign minimum. M1 must independently deliver at least 20 minutes. Rebalance later allocations only at reviews while keeping the full campaign at least two measured hours. Never count alternate demos, failed-attempt replay, repeated cleared encounters, idle padding or slowed movement toward a milestone.

### Stop-and-review contract
- **Stop after every complete region (M1 through M8).** Do not automatically begin the next region. Present the measured cumulative content, a visual preview, completed objectives, equipment/route changes, test results and remaining defects, then wait for Ryan's feedback and go-ahead.
- **M1 is the current implementation boundary.** Complete and polish the first 20 minutes before implementing Riverlands or anything beyond it. Planning later regions and shared progression is allowed now; speculative machinery for unbuilt regions is not required.
- A checkpoint is a finished playable chapter, not a timer threshold: its opening, dungeon, boss, resolution, art feedback and save/checkpoint behavior must work end to end. Intermediate batches may report progress but are not substitutes for these stops.
- Technical acceptance at each stop: autonomous normal-speed completion, no replay padding, real topology/puzzle proof, exact mid-objective and fresh-process resume, death recovery, preserved earlier-region progress, inspected 64x64 visuals, full serial tests, lint/compile and actual simulator preview. Preserve ordinary carousel slot timing.
- Review can revise future equipment, room designs and allocations before the next chapter starts. Keep the outline coherent without treating every detail as immutable.
- **Release is a separate final stop.** After M8 approval, validate the integrated campaign duration, long-run stability, restart/carousel behavior and deployment readiness. No push, published-route switch or deployment without explicit approval.

### Existing implementation references for the roadmap
- world.Area and its connectivity checks define authored spaces, not randomly repeated content.
- journey.Visit / LOCAL_FIELDS and campaign capture/restore provide connected travel with cleared-room persistence.
- journal.Errand prerequisites model objective dependencies and meaningful rewards.
- puzzle.next_stone_action, sluice.crossing_open and pulse.RootPulse demonstrate actual spatial/state changes with deterministic autonomous solutions.
- persistence.SaveStore and preview.run supply validated atomic saves and ordinary carousel-compatible sessions.

## Next implementation batch: three connected woodland branches
- Add Brook Crossing, Old Sawmill and Watchwood between the first Lost Woods visit and Root Hall. These are subareas of Greenwood, not additional campaign regions. Retain original area IDs 0-4 and append 5-7, with the journey defining actual order.
- Geometry-first content: Brook repairs a dam and changes bridge access to separated banks; Sawmill requires a genuinely movable log/pressure plate with no bypass; Watchwood opens a tower through two cooperating light controls. Each gets distinct authored topology, reachable combat, visible state changes, treasure and a real exit. Draft design is delegated read-only to repository, temporary files only; lead must inspect and prove before integrating.
- Required integration references: journey.JOURNEY controls visit order; persistence._state currently incorrectly equates first Root Hall/Court visit indices with area IDs. Derive first-visit milestones from JOURNEY instead of weakening guardian/boots/sluice validation. Existing tests/test_zelda_journey.py has fixed visit indices; retain exact assertions but discover visits by area/errand identity.
- Append new map data through a campaign-only content module without changing legacy QuestGame defaults. Persist branch objectives and log position, validate bounds/prerequisites/actor reachability, checkpoint rollback and cleared return state. Reuse puzzle.next_stone_action and existing campaign passability/objective hooks, not a second combat engine.
- Tests must prove barriers really gate treasure, objectives cannot execute from the wrong tile or skip prerequisites, actual pushes change topology, autonomous completion works, mid-objective saves resume exactly, and malformed states stay preserved. Render inspected before calling the batch complete.
- No source edits until the guardian full-suite snapshot completes. Measure added unique content at unchanged STEP_TIME; this batch alone is not expected to meet 20 minutes. Continue substantial shrine content afterward, within M1 only.

- Guardian final snapshot verified: 1,505 tests passed in 227.80s; config hashes unchanged. Woodland integration may now proceed. First necessary expansion change derives milestone visit positions from JOURNEY and replaces test-only magic visit indices; existing area IDs remain stable.

- Expansion prerequisite verified: 95 focused campaign/journey/pulse tests passed. Full-style lint caught one 124-character test assertion, corrected by naming the rescue cache; changed journey suite then passed 23 tests, lint and whole-source/test compileall passed. No content-time increase from this prerequisite refactor.
- Detailed offline content-action audit remains 251.333s: 699 moves, 36 strikes, 17 defeats, 14 objective/control interactions, 355 unique tiles. The 20-minute gap is 948.667s. Nine extra short rooms alone will not close it; incoming designs must be measured, not assigned durations by name. Artifact: ~/.aki/tmp/zelda-region-verification/content-actions.json.
- Temporary two-stone feasibility prototype reused walking_route and legally replayed four pushes/15 total actions with both plates simultaneously occupied. Solver explored 625 states in approximately 61ms on this laptop; only 4.5s movement, NOT substantial authored content by itself. Any actual shrine integration needs constrained room geometry and measured frame cost, not full-map BFS every frame. Prototype only: ~/.aki/tmp/forest-two-stone-prototype.py.

### Inner-shrine design review, not yet accepted for implementation
- Draft received: ~/.aki/tmp/forest-inner-shrine-design.md. Useful causal ideas: simultaneous seed plates and light unlocking a stone lane. It is not executable map evidence and is not accepted verbatim.
- Correct integration order: preserve the existing spirit rescues/song/tree restoration before the Treant. Insert inner shrine after tree restoration and before Treant, or explicitly return from its exit to the existing recovery journey. The draft's immediate Vine Court-to-Treant chain would skip those objectives if followed literally.
- Keep appended woodland IDs 5-7; future shrine IDs start after them, not the conflicting 5-10 in the draft. Avoid implicit visit-index arithmetic, use the newly tested first_visit helper.
- Existing crossing_open is tied to COURT CROSSINGS, not generic. Existing RootPulse safe tiles/health are fixed, not automatically parameterized by a new instance. Do not claim unchanged reuse for either without an explicit small extension and regression tests.
- Area requires exactly one chest-or-sigil gate unlock, and cannot combine an optional chest with sigil unlocking as drafted. Preserve the existing schema or justify a narrow, tested content requirement; do not weaken validation just to fit an unproven sketch.
- Proposed Observatory light path is geometrically inconsistent (southbound x=8 beam cannot hit a mirror moved to x=6 without an upstream deflection), and Thorn Gallery exit approach is off its proposed 22x12 map. Actual grid and beam/no-bypass proofs are mandatory before adopting coordinates.
- 242 combined Zelda regression tests now pass on the route-index prerequisite. No additional playable seconds yet; first-region gate remains open.

### Brook Crossing implemented, woodland batch in progress
- Lead proved and integrated one 32x22 authored BROOK subarea: request, recover planks, repair dam to access island, operate winch to raise north-bank bridge, clear separated banks, recover treasury key and exit. Four visible objective transitions, five ordinary enemies, real initially inaccessible terrain. Draft scratch disconnected row 8 and unsupported enemy were not imported.
- Existing Zelda regressions: 243 passed in 22.83s; full-style lint and compileall pass. New Brook-specific geometry, order, stage-resume, death, invalid-save and renderer tests added next.
- Actual route now 298.450s (4m58.45s), zero deaths. Brook adds 47.117s, 132 moves, 94 new tiles, 8 strikes and 4 interactions. This is real new content, still 901.550s short of the complete 20-minute milestone. No speed changes, room loops or other-region work.
- Campaign-only WOODLAND_AREAS composition avoids world/game/puzzle circular imports and leaves published LEGACY_AREAS intact. Save content version forest-brook-9; older unpublished saves remain preserved/rejected.

### Brook verification checkpoint, 2026-10-06
- 17 Brook-specific tests passed separately from the 243 existing Zelda regressions. Coverage includes gating/order, five exact stage continuations, death rollback, cleared cache, malformed-save protection and bridge pixels.
- Fresh-process verification now passed all five Brook stages (0-4), with exact saved-state continuation. Complete route measured 298.450 seconds at 24, 30 and 60 FPS, zero deaths. These are equal simulation durations, not estimates.
- Inspected brook-stages.png: actual 64x64 stage frames show request/planks/repair/winch feedback and the raised bridge under the fixed HUD. Stage-zero helper caption retains the prior MAP label but gameplay does not display it outside interaction phase. Broader visual polish remains part of M1 acceptance.
- Full-style campaign/test flake8 and whole-source/test compileall passed. Actual 31-second RGBMatrix simulator preview passed with two successful atomic saves (periodic and final), reload and cleared guardian. No standalone build target exists in this Python application.
- Current-source full serial suite passed 1,524 tests in 221.19s, pytest exit 0 and config changes []. Complete-route visual/roundtrip audit also passed. This replaces the earlier guardian snapshot as the current full-suite evidence.
- This is an intermediate engineering checkpoint, not M1 acceptance. First chapter remains 15m01.55s short; Old Sawmill, Watchwood and substantive inner-shrine content are not implemented. All eight regions retain the stop-and-review roadmap above. No commit, push, published-route switch or deployment performed.

### Next-batch draft rejection, no new content integrated
- Inspected and executed the delegated temporary Sawmill draft once. Area schema construction passes, but the real next_stone_action solver returns None immediately; zero legal solution actions. Even forcing its crossing stage open leaves corridor, treasury and exit unreachable.
- Root cause: its one-cell alley has no reachable standing tile beneath the required northward log push. The entry itself connects through (11,10) to (11,11); the blocked turn, not entry connectivity, prevents the solution. The draft also uses unsupported enemy kind sawwraith. This is not accepted content and must not be copied into woodland.py.
- Next implementation must prove a connected entry, reachable turning bay behind the log, blocked treasury before the plate, legal push replay, and connected treasury/exit afterward. Use only implemented enemy kinds. Do not solve with teleportation or by opening the treasury before the push.
- Fresh whole-route audit after Brook: 449 distinct visited tiles, 66 exact JSON roundtrips, final SaveStore reload identical, zero deaths, approximately 0.396 ms per sampled rendered frame on this laptop. Refreshed regions.png contact sheet inspected; region.gif is regenerated from the actual route.

### Independent Brook review closed
- Reviewer found no concrete geometry, persistence-gating or autonomous-play defect. Accepted maintainability nit: Brook Errand.requires/item fields are descriptive only; actual ordering is enforced by brook_stage, not VillageJournal inventory/dependency logic. No behavior change needed for this linear chain.
- Rejected rendering concern after direct source check: preview.CampaignRenderer._brook (lines 63-71) explicitly paints closed crossings as water and open crossings as planks over the static background. Actual stage sheet was inspected; the reviewer omitted this overlay when reasoning from base render.py.
- Evidence caveats resolved: ~/.aki/tmp/verify-zelda-brook.py launches a literal subprocess for each of five stages, compares encoded continuation, and measures completion at 24/30/60 FPS. brook-metrics.json records 298.45000000005723 seconds for each rate. These offline checks supplement, not replace, the in-process pytest tests.
- No source changes from review, so the 1,524-pass current snapshot remains valid. Brook batch verification is closed; M1 content remains incomplete.

### Sawmill implementation plan, active M1 batch
- Corrected geometry is now proven using the real legal-push solver: 15 actions, three pushes through (12,11), (13,11), (14,11), (14,10). The southern turning bay allows a northward push; the plate opens the only shutter into the eastern mill. Treasury is unreachable before the plate and treasury/exit are connected after it. Solver replay approximately 9ms total on laptop, not per frame.
- Append SAWMILL as area 6 after Brook in woodland.py/journey.py. Keep existing IDs and published areas untouched. Add campaign sawmill_log state, use next_stone_action only after reachable western threats/pickups are cleared, and preserve ordinary combat across the opened shutter.
- Persistence follows Brook and Root Hall examples: exact integer log positions, before/after-visit constraints, no hero/actor/pickup inside log or closed shutter, start-to-hero connectivity, no treasury before solved plate. Checkpoints/cache retain solved geometry. Bump unpublished content version; preserve old saves.
- Render a brown log, gold pressure plate and closed/open mill shutter via campaign-only scenery. No shared legacy art edits.
- Tests follow test_zelda_puzzle.py, test_zelda_woodland.py and test_zelda_journey.py: legal pushes/no bypass, autonomous completion, exact mid-push resume, death rollback, malformed saves protected, cached resolution and changing shutter pixels. Run serial focused tests/lint/compile immediately, then current-snapshot full suite and fresh-process/visual checks. This small chamber is not claimed as multiple minutes.

## Interim live demo release, Ryan authorized 2026-10-06
- Ryan requested publishing what works now to the live matrix repo for Demos, then continuing. This supersedes the no-publication rule for this verified interim slice only, not approval of M1 or later regions.
- Publish the measured 4m58.45s forest as a separate ZELDA WOODS demo. Keep existing ZELDA QUEST short demo unchanged. Registry-driven Demos/Lock Demo/carousel discover it without shipping local config.
- Add a thin published runner using the existing preview lifecycle with opt-in repeat: resume unfinished saves, restart completed saves on next appearance, show completion briefly then restart during Lock Demo. Normal carousel duration remains unchanged. Preview defaults still end without looping.
- References: feature_registry zelda_quest entry, menu_data demo labels, preview.run autosave/final-save lifecycle, run_session duration/stop handling, test_zelda_quest registration test and test_zelda_campaign actual simulator/SaveStore tests. Test real registered runner, cross-slot resume, completed-save restart, continuous repeat, corrupt-save preservation, stop/error behavior.
- Stage only Zelda code/tests, demo registry hunk, menu label, ignore rules and plan. Exclude Skeleton, all config and unfinished Sawmill (integration script failed before creation, no Sawmill source edits). Verify serial full suite/lint/compile and offline simulator before fast-forward push to origin/main. Then continue M1 locally; no claim of device installation without evidence.

### Interim release verification
- Focused release/campaign checks: 43 tests passed, lint and compile passed. Added Lock Demo registration assertion afterward; full release snapshot is being verified once against all tests.
- Shipping tree deliberately excludes Skeleton source/test/registry entry and every local config change. Exported staged tree f4e3adc9bcacb81cc823e2c64862998256c753bd to a fresh temporary directory; final source/tests match it exactly, only README/plan documentation differs.
- Actual registered ZELDA WOODS runner passed a real 31-second simulator session with periodic and final saves and guardian resume. Actual main.run_feature dispatcher passed two slots with increasing saved progress. Two separate OS-process registered-demo sessions also resumed from 0.4833 to 0.9667 saved seconds.
- Independent read-only review found no release blockers in the wrapper, repeat/save lifecycle or menu/registry routing. Reviewer wording corrected: original short Zelda Quest has no save file; the separate new live-save file isolates development preview state. The pytest restart test is in-process, supplemented by the actual two-process check above.
- Release full-suite result and push receipt follow. No device-installed claim from a repository push alone.

- Release audit found tests/test_sequence_sync.py requires the shipped default config to contain every registered feature. Add only zelda_woods to the committed baseline via index-only blob, preserving the actual local config bytes and unrelated Skeleton entry. Existing device settings remain updater-preserved. This supersedes the earlier blanket exclusion of config/config.json: only this narrow new default is in the release, no local config edits. Test the corrected shipping tree before push.

### Continuation after interim publication
- Keep development on feat/zelda-campaign after pushing the verified checkpoint to main. Do not automatically push later M1 batches. Live woods save path remains isolated from local preview saves.
- Next concrete implementation resumes the proven Sawmill layout from ~/.aki/tmp/prove-sawmill.py (three legal pushes through a reachable turning bay). The earlier integration helper had a quoting SyntaxError before writing any repository source. No partially integrated Sawmill ships.
- Any next content-version bump must explicitly consider the now-published forest-brook-9 save. Preserve incompatible live save files; do not silently overwrite or call the expanded chapter ready until migration/reset behavior is decided and verified for its later release.

- Corrected exact shipping snapshot passed **1,525 tests in 241.42s**, lint and compile; config hashes unchanged. Count excludes eight unrelated local Skeleton tests and includes nine live-demo tests. First snapshot had precisely one failure, missing zelda_woods in shipped defaults; corrected without touching local config or weakening assertion.
- Final bridge/guardian/WOODS END contact sheet inspected from shipping source. Measured route still 298.450s, zero deaths. Full continuous two-playthrough simulator soak remains in flight before push.

### Interim publication receipt, pending push approval
- Release committed locally as a1b3b10 (feat: publish resumable Zelda Woods forest demo). Exact source/tests match the verified shipping snapshot; unrelated config/Skeleton hashes and registry hunk unchanged.
- Full registered Lock Demo soak passed: 18,300 rendered frames across 610 simulated wall seconds, two complete 298.450s playthroughs with zero deaths, then seven seconds of the third run saved correctly.
- Push preflight was blocked by the explicit Bash(*git push*) approval rule: its approval prompt expired unanswered. No remote mutation occurred; origin/main remains 4ff00b4. Need approval for git push origin a1b3b10c4cd43735d383c6e89af97029e0dbe7a6:refs/heads/main. Do not bypass the rule with another transport or tool.
- Only publication is blocked. Local M1 continuation remains authorized; keep future content out of the exact a1b3b10 release commit.

### Local Sawmill integration repair, not part of interim release
- Initial focused integration run failed (6 failed, 37 passed, 56 errors): campaign stalled in Sawmill before its first push, so downstream journey fixtures could not finish.
- Reproduced room 6, hero (6,6), HP 4, heart at (6,7), log (12,11), two unreachable eastern enemies. The Sawmill override deferred because a pickup was reachable, but base AI only pursues ordinary pickups when there are no threats anywhere. Neither layer chose a reachable action.
- Scoped repair: when no Sawmill enemy is reachable, collect a reachable pickup before solving the log. Keep base/legacy AI unchanged. Regress both pickup kinds at low/normal/full health, then rerun focused tests, lint, compile, fresh-process stage verification and serial full suite. No further publication or release-commit changes.

### Sawmill batch verification, local only
- Repaired focused suite: 71 passed in 4.01s, including six direct pickup-stall regressions. Two lint formatting errors were corrected; all Zelda-source/test full-style lint and whole-source compileall now pass. No standalone build target exists.
- Complete route: 321.266666667 content seconds (5m21.27s), zero deaths at 24/30/60 FPS. Sawmill adds 22.816666667 seconds, not multiple minutes. Remaining M1 gap: 878.733333333 seconds (14m38.73s).
- All four log-position saves resumed in actual fresh processes with exact state equality. Whole-route audit: 510 distinct tiles, 71 exact JSON roundtrips, final save reload exact, approximately 0.250ms per sampled rendered frame. Inspected sawmill-stages.png and regions.png; current region.gif regenerated.
- Actual 31-second RGBMatrix preview began mid-push, solved/departed the mill, and saved at 174.5667 and 175.5500 active seconds; final disk reload matched the final write. No live updater/device calls.
- A genuine 60-second forest-brook-9 save generated from the corrected release snapshot was rejected by the local forest-sawmill-10 build and preserved byte-for-byte; writes remain disabled for that file. Before publishing any later content, decide and verify a migration/reset path. Current checkpoint publication is independent and unchanged.
- Serial input-first full-suite verification and independent read-only review remain in progress. Do not equate earlier release test results with acceptance of this working tree.

### Sawmill final-review and verification qualification
- Independent read-only review found no blocking Sawmill correctness/save-safety defect. Its occupied-enemy reachability concern does not reproduce here: before the shutter opens all reachable western enemies are ordinary threats; if a path to a farther enemy crosses another, the first enemy on that route is itself reachable. No speculative legacy-AI rewrite is justified.
- Manual review corrected new regression health values from [2,4,6] to [2,4,MAX_HEARTS], where MAX_HEARTS is 5. All 20 Sawmill tests, lint and compile pass afterward; production source unchanged.
- Full working-directory suite returned 1 failed, 1,553 passed in 196.21s; config hashes unchanged. The only failure was the preserved local config lacking zelda_woods, although a1b3b10 already contains the correct shipping default. Do not overwrite unrelated local config to hide this discrepancy.
- An isolated exact-source snapshot is now running the full suite with only the committed zelda_woods default added to temporary config; retains local Skeleton source/test/config, audits both configs and compares source bytes afterward. This is candidate evidence, not an unqualified green working-directory suite.
- Remote refs/heads/main was checked directly and remains 4ff00b4ff574c6dd1be810989b18df10f3395c43. Release a1b3b10 is still not pushed; original tool approval expired. All unrelated config/Skeleton file hashes match the pre-release audit.

### Next local M1 batch: Watchwood proof before integration
- Keep the next batch inside Greenwood and reserve appended area ID 7. Preserve the exact a1b3b10 release and do not publish local Sawmill/Watchwood automatically.
- Intended causal chain: a sunlight source reaches a first adjustable reflector; its redirected beam lights a side-path sensor, physically opening access to a second reflector. Aligning the second reflector routes that same beam to the tower sensor and opens the treasury path. This must be visible light routing, not two labeled switches with a timer.
- Before implementation, prove on one actual rectangular Area grid: first control reachable initially, second blocked until first sensor, treasury blocked until both controls, every required interaction on a walkable adjacent tile, and an actual source-to-reflector-to-sensor beam path at each stage. Reject disconnected routes or coordinate-only sketches before touching campaign state.
- Use existing patterns: woodland.BROOK/SAWMILL for stable appended areas; journey.Visit/first_visit for route milestones; campaign._objective/_contacts for real-position interactions; preview._brook/_sawmill for world-layer state art; persistence._state/SaveStore for exact flags, connectivity and byte-preserved invalid saves. New beam geometry belongs in a small content-specific function only if proven necessary, no generic framework for later regions.
- Test prereqs/no-bypass, wrong-position interactions, changing beam pixels and physical passability, reachable combat/pickups, actual autonomous completion, checkpoint rollback, exact fresh-process stage resumes and preserved incompatible saves. Measure normal-speed action time and remaining M1 gap; do not assign minutes to this room by name.

- Final Sawmill candidate verification: 1,554 passed in 205.07s, exit 0, repository/snapshot config changes [], source_matches true. Snapshot sawmill-candidate-1exjmepc differs only by adding the already-committed zelda_woods default to temporary config. Together with lint, compile, simulator, exact resume and independent review, this closes the local Sawmill batch. No push or device update occurred. Watchwood proof helper is prepared but not executed or integrated.

### Watchwood integration plan, proof passed
- Executed temporary geometry proof: stage 0/1/2 reaches 220/401/561 tiles and beam lengths 9/34/33; second control is blocked until first sensor lights and treasury until tower sensor lights. Both controls are adjacent to their reflectors. This is feasibility, not delivered playtime.
- Add watchwood.py with authored rectangular map, two reflector orientations and finite beam tracing (walls stop light, the water aperture transmits light but blocks feet). Actual beam sensor hits determine shutter passability; stage alone must not directly open a shutter. Decorate rooms without blocking required beam lines; six ordinary encounters, not added HP or waves.
- Compose WATCHWOOD after stable woodland IDs (area 7) and insert its Visit after Sawmill. Persist watchwood_stage globally like brook_stage, capture checkpoints, and reject before/after-visit inconsistencies, closed-shutter actors/pickups, inaccessible hero and premature treasury. Shared watchwood_passable helper defines both gameplay and save geometry. Bump local content version, keep incompatible saves untouched.
- Campaign uses existing real-position objective/contact hooks to rotate reflectors. Renderer draws the actual traced beam, orientations, sensor glow and shutters under actors. Keep legacy game, release commit, normal cadence and unrelated Skeleton/config untouched.
- Add Watchwood tests modeled on test_zelda_woodland (stages/gates), test_zelda_sawmill (spatial validation/cache), test_zelda_journey (progression), test_zelda_campaign (save preservation) and renderer tests. Verify focused serial tests/lint/compile, measured route and fresh-process resumes, actual simulator, then isolated full suite with committed default only.

### Watchwood local implementation and measured verification
- Added authored 32x22 Watchwood with six ordinary enemies, two adjustable reflectors plus fixed elbow, a water light-aperture, side-path sensor and tower sensor. Shutters derive from actual traced beam hits; light and walking use different aperture rules. Stage0/1/2 geometry/no-bypass, correct-position/order/death contacts and renderer state changes are tested.
- Integration regression suite: 89 passed. New Watchwood suite: 27 passed, 100% statement coverage of watchwood.py; full-style Zelda lint and source/tests compileall pass. Coverage run emitted one NumPy reimport warning from pygame surfarray during fixture setup, not silenced; full-suite non-coverage check remains pending.
- Actual complete route at 24/30/60 FPS: 357.483333333 seconds (5m57.48s), zero deaths. Watchwood adds 36.216666667s. M1 still lacks 842.516666667 seconds (14m02.52s); no multi-minute-room claim.
- Three fresh-process stage continuations matched exactly. Full route has 602 distinct tiles and 79 JSON roundtrips, final disk reload exact, approximately 0.299ms per sampled frame. Actual stage contact sheet inspected; first/second reflector beams and labels visible. Actual simulator, isolated serial full suite and independent review remain running.
- Release a1b3b10 and real local config are untouched. Local content version forest-watchwood-11 rejects/preserves older content saves; later publication still requires a migration/reset decision. Next implementation is inner shrine after elder-tree restoration, before Treant, new stable IDs8 onward.

## Publish current slice and pause, Ryan requested 2026-10-06
- Ryan requested publishing/pushing what exists now and taking a break. Stop expansion and cancel speculative shrine design. Autonomous region-completion goal cleared, not completed; 20-minute M1 remains unmet.
- Publish the latest 357.483s Watchwood/Sawmill slice, not only the earlier a1b3b10 Brook checkpoint. Remote main confirmed still 4ff00b4, so no prior forest-save version was released through this repo; this release introduces forest-watchwood-11. Preserve any incompatible local development save, never delete or overwrite it.
- Stage only Zelda content/test files, README duration and this tracker. Keep original short ZELDA QUEST, baseline shipping defaults and unrelated local Skeleton/config intact. Finish active verification/review, test exact staged shipping snapshot excluding unrelated work, then normal fast-forward push (explicit git-push approval still applies). Stop after receipt; do not resume region work.

### Final shipping verification for requested pause release
- Exact shipping tree 890406dfc2d25ec90cd3bdaece660bedb2f565ef passed 1,574 tests in 201.11s, full Zelda lint and source/tests compilation, config hashes unchanged. Count excludes eight unrelated Skeleton tests; candidate with them passed 1,582. Later changes are tracker documentation only.
- Independent Watchwood review found no blocking geometry/navigation/persistence/rendering defects. Reviewer wording corrected: incompatible saves are preserved, not discarded; reachability is enforced for hero, passability for enemy/pickup positions. Actual 31-second stage1 simulator saved twice at 197.3667/198.3500 seconds and reloaded with Watchwood solved/departed.
- Scope audit confirms original short-demo source unchanged from earlier verified release, no unrelated registry/config/Skeleton staging, and all unrelated byte hashes preserved. Full registered two-loop soak is still running; push receipt follows separately. Development remains paused.
