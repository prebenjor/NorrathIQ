# WoW 3.3.5 in-client smoke tests

Run these checks on the target custom realm before publishing a release. Automated tests stub static contracts, but only the client can confirm FrameXML interactions and realm-specific IDs.

## Loading and persistence

1. Install NorrathIQ and the generated Index/detail addon folders.
2. Confirm the addon appears with Interface 30300 and loads without Lua errors.
3. Run /reload and confirm account settings and per-character settings persist.
4. Search before hovering an item; confirm only the Index pack and the selected detail shard load.

## No gameplay observation

1. Hover items, target NPCs, accept quests, loot, trade, and open the spellbook.
2. Confirm no capture chat messages appear and no `NorrathIQCaptureDB` is written.
3. Confirm only NorrathIQ UI settings persist after `/reload`.
4. Confirm tooltips never trigger data-pack loading or database indexing.

## Search and tooltips

1. Run /niq gnoll fang and select the result.
2. Verify Moonstones, Blackburrow, Captain Tillin, KEEP, source confidence, and map actions.
3. Hover mapped items in bags, equipment, merchant frames, loot, quest rewards, and chat links.
4. Confirm original tooltip content remains visible if NorrathIQ has no record or encounters incomplete data.
5. Verify ambiguous exact aliases open the search chooser instead of attaching arbitrary facts.

## Inventory

1. Open every stock bag and verify Q, T, R, K, and $ badge placement at multiple UI scales.
2. Move, split, loot, vendor, bank, and destroy unrelated items; badges must refresh without moving or acting on items.
3. Disable bag badges in the browser and verify overlays clear.
4. Exercise one third-party adapter through NorrathIQ_API.RegisterBagAdapter.

## Quest helper

1. Track a mapped realm quest with questId data and confirm ID resolution precedes text matching.
2. Track an objective containing Top of Broken Staff and confirm the gnoll hunter/Qeynos Hills resolution.
3. Confirm ambiguous and unmatched objectives are not guessed.
4. Close or disable the helper and ensure QUEST_LOG_UPDATE does not reopen it.

## Equipment

1. Import a realm bow record with weaponDamageMin, weaponDamageMax, and weaponSpeed.
2. Compare against an equipped ranged weapon and verify average damage, faster/slower speed, and DPS deltas.
3. Remove realm-normalized weapon fields and confirm the result becomes Unknown rather than inventing a score.

## Maps

1. Register a native map provider and verify it wins for a record with nativeMap.
2. Disable the provider and confirm the EQ atlas fallback opens.
3. Verify Captain Tillin, McNeal Jocub, and the gnoll hunter approximate markers.
4. Open Blackburrow with no coordinates and confirm zone/camp text appears without a fabricated pin.

## Safety and compatibility

1. Enter combat and exercise tooltips/search; no protected-action or taint errors should occur.
2. Confirm NorrathIQ never calls selling, deletion, quest-acceptance, movement, targeting, or combat APIs.
3. Test common resolutions, UI scales, and window positions.
4. Inspect addon memory before search, after index load, and after several detail shards. The initial NorrathIQ core should remain below the 25 MB budget.
