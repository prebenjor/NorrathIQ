# NorrathIQ

NorrathIQ is an offline EverQuest knowledge addon for WoW 3.3.5 EQWOW/custom realms. It provides searchable item, NPC, quest, recipe, spell, zone, and map information without networking from the game client.

## Features

- Item, NPC, quest, recipe, zone, key, EverQuest spell, and EQWOW/WoW spell search.
- Tooltip uses, drops, quest relations, recipes, recommendations, provenance, and map actions.
- Live lookup for items, NPCs, and quests encountered during play.
- `Q`, `T`, `R`, `K`, and `$` bag badges.
- Quest-objective resolution and source/turn-in navigation.
- Equipment comparison when mapped realm stats are available.
- Optional local realm capture for IDs, stats, spells, quests, loot, and sampled locations.
- Windows updater with validation, staging, backup, and rollback.

NorrathIQ never sells, destroys, moves, equips, accepts, or turns in anything automatically.

## Requirements

Players need a WoW 3.3.5 client using Interface `30300`. The packaged Windows updater does not require Python.

Maintainers need Python 3.12+, PowerShell, and the pinned dependencies in [`updater/requirements.lock`](updater/requirements.lock) when rebuilding the updater.

## Install

1. Close WoW.
2. Open **NorrathIQ Updater**.
3. Confirm the WoW/AddOns and local `NorrathIQ-release` folders.
4. Click **Install / Repair Addon**.
5. Enable NorrathIQ on the character-selection AddOns screen. Enable **Load out of date AddOns** if required.
6. Enter the world and open NorrathIQ with the minimap book icon or `/niq`.

If WoW is running, installation is staged. Close WoW, expand **Show advanced options**, click **Apply staged update**, then restart the game. `/reload` does not apply files that were staged outside the active addon directory.

Default updater paths are based on the current Windows home directory. Packagers can override them with `NORRATHIQ_RELEASE_SOURCE` and `NORRATHIQ_ADDONS_TARGET`.

## Use

### Minimap button

- **Left-click:** open or close the Knowledge Journal.
- **Right-click:** show capture status.
- **Left-drag:** move the button.

### Search

Type a name such as `Gnoll Fang` in the journal. Use the category selector to restrict results.

The database is sharded. Explicit searches load only the required shard. Item hovers never queue, load, or index database shards.

### Tooltips

When data is available, item tooltips can show:

- classification and uses;
- quests, giver/turn-in relations, and rewards;
- drop NPCs, levels, zones, camps, and approximate chances;
- tradeskill, trivial level, components, and quantities;
- related items and chain steps;
- Keep, Vendor, Destroy, or Review guidance;
- source, record ID, snapshot, and confidence;
- drop, recipe, source-map, and turn-in-map buttons.

Recommendation precedence is conservative:

1. Keys and active quest uses are Keep.
2. Known research and tradeskill uses remain Keep.
3. `$` requires no retained use or importance rule.
4. Destroy requires zero value, no known use, and strong evidence.

### Bag badges

| Badge | Meaning |
| --- | --- |
| `Q` | Quest item |
| `T` | Tradeskill component |
| `R` | Research component |
| `K` | Key or important progression item |
| `$` | Conservative vendor candidate |

## Live discovery and capture

Live discovery is enabled by default. Items hovered or scanned, non-player NPCs targeted, and accepted quests are added to the current session's lookup. Updates are incremental; unchanged observations do not rebuild the index.

Persistent capture is separate and disabled by default. Enable it with:

```text
/niq capture on
```

Capture records client-visible realm facts:

- item IDs, levels, icons, vendor values, stats, and equipment fields;
- NPC IDs, levels, zones, and sampled player positions;
- quest IDs, objectives, interactions, required items, and rewards;
- tradeskill results, reagents, and quantities;
- visible spellbook spells, ranks, icons, descriptions, costs, ranges, and timings;
- loot observations linked conservatively to recent kills or targets.

WoW writes SavedVariables on `/reload`, logout, or clean exit, normally to:

```text
World of Warcraft\WTF\Account\<ACCOUNT>\SavedVariables\NorrathIQ.lua
```

Use **Process captured data now** in the updater after the file is saved, or leave automatic capture processing enabled. Captured numeric IDs take precedence over external data for matching records.

See [`docs/CAPTURE.md`](docs/CAPTURE.md) for capture details and accuracy limits.

## Commands

| Command | Action |
| --- | --- |
| `/niq` | Open the journal. |
| `/niq <name>` | Open and search. |
| `/niq map <zone>` | Open a zone map or atlas entry. |
| `/niq bags` | Refresh bag badges. |
| `/niq quest` | Toggle the quest helper. |
| `/niq version` | Show addon and data versions. |
| `/niq help` | Show command help. |
| `/niq capture on` | Enable persistent capture. |
| `/niq capture off` | Disable capture without deleting data. |
| `/niq capture status` | Show current-realm capture counts. |
| `/niq capture rescan` | Rescan bags, equipment, quests, and spellbook. |
| `/niq capture clear confirm` | Delete current-realm capture data. |

`/niqcapture` is a direct alias for capture commands. Slash commands run only after pressing Enter.

## Update knowledge

The updater separates three sources:

### EQWOW Database - primary

The [EQWOW Database](http://50.6.248.85/dbviewer/) supplies realm IDs, fusion spells, stats, drops, quests, NPC levels, and coordinates.

1. **Check now** compares lightweight indexes.
2. **Review changes** shows entity and field changes.
3. **Continue detail download** resumes the checkpointed crawl.
4. **Apply validated update** compiles and installs the reviewed candidate.

The site is HTTP-only. Requests are restricted to `50.6.248.85/dbviewer/`; redirects, response sizes, parsing, and fingerprints are validated. Fingerprints detect changes but cannot authenticate HTTP transport.

### Game capture - realm overlay

**Process captured data now** imports the latest SavedVariables observations. The overlay is reapplied after external updates.

### Project 1999 Wiki - optional

The [Project 1999 Wiki](https://wiki.project1999.com/) can fill missing prose. It never overrides EQWOW or captured realm facts.

Data precedence is:

1. Captured facts for matching realm IDs.
2. EQWOW Database.
3. Reviewed corrections.
4. P99 descriptions where other sources are silent.

Custom EQWOW/WoW spells remain separate from P99/EverQuest spells even when names match.

## Maps

- Native providers use realm map IDs and normalized coordinates.
- The built-in atlas uses zone transforms, camps, spawn points, paths, and a coordinate grid.

Captured NPC coordinates are the player's position while observing the NPC, not guaranteed spawn coordinates. Uncertain records open the correct zone with explanatory text instead of an invented pin.

## Performance

- Source data is compiled outside WoW.
- The initial catalog is small and details are load-on-demand.
- Searches load one prefix shard at a time.
- Tooltips never load search or detail shards.
- Live discoveries update one entity and its name indexes.
- Bag scans are coalesced and unchanged items use cached metadata.
- The full source database is never indexed in one in-game operation.

The first explicit search for a prefix may pause briefly while its shard loads. Later searches reuse it for the session.

## Troubleshooting

### `/niq` does not open

- Press Enter after typing the command.
- Confirm the addon is enabled.
- Enable **Load out of date AddOns** if required.
- Run `/niq version` and confirm `capture module: loaded`.

### Search results are empty

- Search an exact name first.
- Wait for the EQWOW search-ready chat message.
- Confirm `NorrathIQ_Data_*` folders are beside `NorrathIQ` in `Interface\AddOns`.
- Run **Install / Repair Addon** with WoW closed.

### Hovering loads data or reduces FPS

Current builds do not load database shards from hovers. Apply the staged update with WoW closed, restart the client, and verify `/niq version`. `/reload` alone does not replace staged files.

### Capture is missing

Run `/niq capture on`, then `/reload` or log out. Confirm the updater targets the correct client and click **Process captured data now**.

### A staged update is not active

Close all WoW processes and click **Apply staged update**. The installer restores its backup automatically if replacement fails.

## Manual installation

Copy `NorrathIQ` and all supplied `NorrathIQ_Data_*` folders directly into `Interface\AddOns` while WoW is closed:

```text
Interface\AddOns\NorrathIQ\NorrathIQ.toc
Interface\AddOns\NorrathIQ_Data_...\NorrathIQ_Data_....toc
```

Do not add an extra release-folder nesting level.

## Maintainer CLI

Run from the repository root:

```powershell
python -m updater.norrathiq.cli validate data\seed
python -m updater.norrathiq.cli compile data\seed build
python -m updater.norrathiq.cli install addon "C:\Games\WoW\Interface\AddOns"
python -m updater.norrathiq.cli apply-staged "C:\Games\WoW\Interface\AddOns"
python -m updater.norrathiq.cli gui
```

EQWOW update commands:

```powershell
python -m updater.norrathiq.cli check-source --cache .cache\eqwow.sqlite3
python -m updater.norrathiq.cli source-status --cache .cache\eqwow.sqlite3
python -m updater.norrathiq.cli crawl-source --cache .cache\eqwow.sqlite3
python -m updater.norrathiq.cli review-update --cache .cache\eqwow.sqlite3
python -m updater.norrathiq.cli apply-update "C:\Games\WoW\Interface\AddOns" --cache .cache\eqwow.sqlite3 --confirm
```

Capture import:

```powershell
python -m updater.norrathiq.cli import-capture "C:\Games\WoW\WTF\Account\ACCOUNT\SavedVariables\NorrathIQ.lua" data\capture --realm "Realm"
python -m updater.norrathiq.cli merge-realm data\seed data\capture data\merged
python -m updater.norrathiq.cli compile data\merged build\realm
```

Bundle schema: [`schema/norrathiq-bundle.schema.json`](schema/norrathiq-bundle.schema.json). Realm-export documentation: [`docs/REALM_EXPORT.md`](docs/REALM_EXPORT.md).

## Lua API

```lua
local results = NorrathIQ_API.Search("Gnoll Fang", "item", 20)
local item = NorrathIQ_API.GetEntity("eqwow:item:95750")
local relations = NorrathIQ_API.GetRelations(item)
NorrathIQ_API.ShowOnMap(item, "source")

NorrathIQ_API.RegisterBagAdapter("MyBagAddon", adapter)
NorrathIQ_API.RegisterMapProvider("MyMapAddon", provider)
```

See [`addon/NorrathIQ/API.lua`](addon/NorrathIQ/API.lua) for current signatures.

## Verify and package

```powershell
python -m pytest -q
.\scripts\verify.ps1
.\scripts\build-updater.ps1
.\scripts\package-release.ps1 -Version 1.3.1
```

Manual client checks are in [`docs/IN_CLIENT_TESTS.md`](docs/IN_CLIENT_TESTS.md).

## Privacy and limitations

- The addon has no networking capability.
- Persistent capture is opt-in, local, and never uploaded automatically.
- Capture excludes chat, credentials, real-world identity, arbitrary files, group inventories, and combat performance.
- SavedVariables and downloaded records are parsed as inert data.
- Updates are sanitized, validated, checksummed, and installed with rollback.
- V1 is English-only and the updater is Windows-focused.
- Captured coordinates and loot rates are observations, not authoritative server data.
- P99 is community-maintained; EQWOW uses unauthenticated HTTP.

## License

Code is covered by [`LICENSE`](LICENSE). Confirm redistribution rights before publishing third-party text, icons, or map artwork.
