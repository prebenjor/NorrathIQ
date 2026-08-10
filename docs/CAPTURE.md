# Realm capture

NorrathIQ can collect realm-specific facts exposed by the WoW 3.3.5 addon API. It is opt-in, local-only, and performs no network requests. Its purpose is to add correct client IDs and useful observed locations to the offline P99 knowledge graph.

## First run

1. Install the `NorrathIQ` folder and the supplied `NorrathIQ_Data_*` folders under `World of Warcraft\Interface\AddOns`.
2. Enable **Load out of date AddOns** on the character-selection AddOns screen if the custom client reports the addon as out of date.
3. Enter the world and run `/niq capture on`.
4. Play normally. Target NPCs, open quest dialogs, loot corpses, open tradeskill windows, visit merchants and banks, and open the spellbook. Hovering items and carrying them in bags also records their client data.
5. Run `/niq capture status` to see record counts.
6. Run `/reload` or log out. SavedVariables are not guaranteed to be written while the client is still running.
7. Close WoW before installing a compiled update.

The account-wide capture is normally written to:

    <WoW>\WTF\Account\<ACCOUNT>\SavedVariables\NorrathIQ.lua

Character-specific SavedVariables paths are not used because `NorrathIQCaptureDB` is account-wide and separates observations by realm.

## Updater workflow

For normal use in the Windows updater:

1. Click **Install / Update Addon** once.
2. Click **Update Classic P99 Knowledge** when you want a fresh offline Classic knowledge pack.
3. Leave **Automatically process new capture data while this updater remains open** checked.
4. Run `/niq capture on` in WoW and play normally.
5. Run `/reload` or log out. The updater locates the account-wide file, selects the most recently active realm, waits for the save to stabilize, validates, merges, compiles, and installs it. If WoW is still running, the data is staged and applied after the client closes.

**Process Captured Game Data** performs the same operation immediately. File selection, realm selection, output directories, manifests, and compilation are no longer required for normal use. They remain available under **Show advanced options** for maintainers.

Without a selected base bundle, import creates a valid observation-only realm bundle. It is useful for IDs and discovered facts, but P99 descriptions and relationships can only be retained by merging with the P99/curated base first.

The equivalent CLI flow is:

    python -m updater.norrathiq.cli import-capture "<WoW>\WTF\Account\<ACCOUNT>\SavedVariables\NorrathIQ.lua" data\capture --realm "Realm Name"
    python -m updater.norrathiq.cli merge-realm data\p99 data\capture data\merged
    python -m updater.norrathiq.cli validate data\merged
    python -m updater.norrathiq.cli compile data\merged build\realm
    python -m updater.norrathiq.cli install build\realm "<WoW>"

## What is collected

- Realm name, client build/interface number, and character class/race/faction/level metadata.
- Item IDs, names, quality, item/required level, type, subtype, equip location, icon path, vendor value, client stat keys, and weapon damage/speed when the tooltip exposes them.
- NPC ID from the unit GUID when available, name, approximate level range, creature/classification data, observation context, zone, map ID, and the player's normalized map position at observation time.
- Quest IDs, titles, levels, objective text, completion state, giver/progress/turn-in NPC interactions, and visible required/reward items.
- Tradeskill names, recipe/spell IDs, difficulty color, result item, reagents, and quantities.
- Every known spell and rank exposed by every spellbook tab, including spell ID, icon, tooltip description, passive state, power cost/type, cast time/range, and which captured character knows it. These are explicitly labeled World of Warcraft data and never merged with P99/EverQuest spells by name.
- Loot items correlated to a recent `PARTY_KILL`, or at lower confidence to a recently targeted NPC, including observed item count and loot-window count.

Capture does not collect chat, account credentials, real-world identity, combat performance, group-member inventories, or arbitrary files. The updater parses the SavedVariables file as inert Lua literals and never executes it.

## Accuracy limits

The WoW 3.3.5 API generally exposes the player's map coordinates, not an NPC's exact coordinates. A recorded NPC point therefore means “the player was here while targeting or interacting with this NPC.” Repeated observations and quest interactions raise confidence, but the UI still labels them approximate.

Likewise, a few loot windows cannot establish an authoritative drop chance. NorrathIQ retains the numerator and observed loot-window count and labels the relationship with observation confidence. P99 facts and curated realm exports remain the preferred descriptive source.

Private realms can alter GUID layouts, map APIs, quest APIs, or hide item links. Records without stable numeric IDs fall back to conservative exact-name matching. Fuzzy matching is never accepted automatically.

## Control and removal

    /niq capture status
    /niq capture rescan
    /niq capture off
    /niq capture clear
    /niq capture clear confirm

`clear confirm` removes only the current realm's observations. Deleting `NorrathIQ.lua` while WoW is closed removes both addon settings and capture data; make a backup first if you want to retain either.
