# NorrathIQ

NorrathIQ is an offline EverQuest knowledge addon for World of Warcraft 3.3.5 custom realms, built for the EQWOW/EverQuest fusion client. It is intended to answer three questions wherever an item, NPC, quest, spell, or recipe appears:

- What is this?
- Why should I care about it?
- Where do I obtain or use it?

The project includes the in-game addon, load-on-demand knowledge packs, a Windows updater, a realm-data collector, and a deterministic Python data pipeline. The addon never connects to the internet while WoW is running.

## Features

- Search items, NPCs, quests, recipes, zones, keys, EverQuest spells, and WoW/EQWOW fusion spells.
- Add items, NPCs, and quests seen during normal play to the live lookup.
- Enrich item tooltips with uses, sources, drops, quest relations, recipes, recommendations, provenance, and map actions when those facts are available.
- Mark bags with subtle inventory badges:
  - `Q` — quest item
  - `T` — tradeskill component
  - `R` — research component
  - `K` — key or important progression item
  - `$` — safe vendor candidate under conservative rules
- Resolve known quest-objective names and connect them to source NPCs and zones.
- Show source and turn-in locations through a native map provider or the included coordinate-grid atlas.
- Compare mapped equipment with the currently equipped slot.
- Preserve EQWOW/WoW spells separately from historical EverQuest/P99 spells, even when names coincide.
- Collect optional realm observations locally without uploading account or character data.
- Update atomically with staging, backup, rollback, validation, and checksums.

NorrathIQ never sells, destroys, moves, equips, accepts, or turns in anything automatically.

## Requirements

### Players

- A WoW 3.3.5 client using Interface `30300`.
- Windows for the supplied updater application.
- No Python installation is required when using a packaged updater release.

### Maintainers

- Python 3.12 or newer.
- PowerShell for the supplied verification and packaging scripts.
- PyInstaller dependencies from [`updater/requirements.lock`](updater/requirements.lock) only when rebuilding the Windows executable.

## Quick start

### 1. Close WoW

Always close the game completely before installing active addon files. If WoW is running, NorrathIQ safely stages the update instead.

### 2. Open NorrathIQ Updater

The updater remembers the configured folders. Its normal workflow uses:

- **WoW or AddOns folder** — either the client directory or its `Interface\AddOns` directory.
- **Local addon source** — the packaged `NorrathIQ-release` directory.
- **Portable data bundle** — the packaged knowledge bundle used by advanced compilation tools.

The source and AddOns defaults are derived from the current Windows home directory. Packagers can override them with `NORRATHIQ_RELEASE_SOURCE` and `NORRATHIQ_ADDONS_TARGET` environment variables.

Click **Install / Repair Addon**. This installs the core `NorrathIQ` folder and the supplied `NorrathIQ_Data_*` packs.

If the updater says the update was staged because WoW was running:

1. Exit WoW completely.
2. Return to the updater.
3. Expand **Show advanced options**.
4. Click **Apply staged update**.
5. Start WoW again.

Do not judge a staged fix before applying it: the game continues using the older active files until it is restarted.

### 3. Enable the addon

At the character-selection screen, open **AddOns** and enable NorrathIQ. Enable **Load out of date AddOns** if the custom client labels Interface `30300` as out of date.

### 4. Open NorrathIQ

Enter the world and either:

- left-click the book icon around the minimap; or
- type `/niq` in chat and press Enter.

The minimap button controls are:

- **Left-click** — open or close the Knowledge Journal.
- **Right-click** — print capture status.
- **Left-drag** — move the icon around the minimap.

### 5. Search

Type a name such as `Gnoll Fang` in the journal search box. Select a category to restrict results to items, quests, NPCs, recipes, spells, zones, or keys.

The large offline database is sharded. Database packs are loaded only when a search explicitly needs them. Merely hovering an item never queues, loads, or indexes an offline database shard.

## Everyday use

### Item tooltips

Hover an item in a bag, equipment slot, merchant window, loot window, chat link, or quest reward. When knowledge is already available, NorrathIQ can display:

- classification and purpose;
- related quests and turn-ins;
- drop NPCs, levels, zones, camps, and approximate chances;
- recipe skill, trivial level, components, and quantities;
- related items and quest-chain steps;
- Keep, Vendor, Destroy, or Review guidance;
- source, record ID, snapshot date, and confidence;
- buttons for drops, recipes, source maps, and turn-in maps.

Recommendations are deliberately conservative:

1. Known key and active quest uses win.
2. Known research and tradeskill uses remain Keep even if they are not currently relevant to the character.
3. `$` appears only when no retained relationship or importance rule exists.
4. Destroy requires zero value, no known use, and strong evidence.
5. No recommendation performs an item action.

### Live discovery

Live discovery is enabled by default. During the current game session, NorrathIQ adds the following observations to its lookup:

- items hovered in bags or encountered during bag, bank, equipment, merchant, or loot scans;
- non-player NPCs targeted or used for quest interactions;
- accepted quests, visible objectives, required items, and rewards.

Live discoveries use incremental updates. One observation changes only that entity and its exact-name/alias entries; it does not rebuild the global index. Repeated unchanged observations take a cached fast path.

Session-only discovery is separate from persistent capture. It makes newly seen records searchable immediately, but it is not guaranteed to survive logout unless capture is enabled.

### Persistent game capture

Persistent capture is optional and disabled by default. Enable it with:

```text
/niq capture on
```

While enabled, normal play records client-visible realm facts including:

- item IDs, types, levels, icons, vendor values, stats, and equipment fields;
- NPC IDs, names, levels, zones, and sampled player positions;
- quest IDs, objectives, giver/turn-in interactions, required items, and rewards;
- tradeskill recipes, results, reagents, and quantities;
- visible spellbook tabs, spells, ranks, icons, descriptions, costs, ranges, and timings;
- loot observations correlated conservatively with recent kills or targets.

WoW normally writes SavedVariables on `/reload`, logout, or clean exit. The account-wide file is usually:

```text
World of Warcraft\WTF\Account\<ACCOUNT>\SavedVariables\NorrathIQ.lua
```

After WoW saves the file, the updater can locate and process it automatically:

1. Keep **Automatically process new capture data while this updater remains open** enabled; or
2. click **Process captured data now**.

Captured numeric realm IDs take precedence over external descriptions for matching records. The complete capture workflow and privacy details are in [`docs/CAPTURE.md`](docs/CAPTURE.md).

## Slash commands

| Command | Purpose |
| --- | --- |
| `/niq` | Open or close the Knowledge Journal. |
| `/niq <name>` | Open the journal and search for a name. |
| `/niq map <zone>` | Open a known zone in the selected map provider or atlas. |
| `/niq bags` | Rescan and refresh bag badges. |
| `/niq quest` | Toggle the quest helper. |
| `/niq version` | Report addon, EQWOW snapshot, capture overlay, and optional P99 reference versions. |
| `/niq help` | Print the command summary. |
| `/niq capture on` | Enable persistent local realm capture. |
| `/niq capture off` | Stop persistent capture without deleting observations. |
| `/niq capture status` | Show captured record counts for the current realm. |
| `/niq capture rescan` | Rescan bags, equipment, quests, and visible spellbook ranks. |
| `/niq capture clear` | Explain the confirmation required to clear the current realm. |
| `/niq capture clear confirm` | Remove captured observations for the current realm. |
| `/niqcapture ...` | Direct alias for capture commands. |

Slash commands execute only after pressing Enter. If `/niq` remains visible in the chat edit box, it has not been submitted yet.

## Updating knowledge

The updater displays three source cards.

### EQWOW Database — primary

The [EQWOW Database](http://50.6.248.85/dbviewer/) supplies realm IDs, custom fusion spells, item stats, drops, quest relations, NPC levels, and map coordinates.

1. Click **Check now** to rebuild lightweight source indexes and compare them with the installed snapshot.
2. Click **Review changes** to inspect additions, removals, and field-level changes.
3. Click **Continue detail download** to resume the rate-limited detail crawl. It can be paused safely and resumes from checkpoints.
4. Click **Apply validated update** only after validation succeeds.

The site is HTTP-only. NorrathIQ restricts requests to `50.6.248.85/dbviewer/`, rejects off-host redirects, caps responses, treats downloaded HTML/embedded records as inert data, and fingerprints normalized records. Fingerprints detect changes but cannot authenticate an HTTP server.

### Game capture — authoritative realm overlay

Click **Process captured data now** after `/reload`, logout, or exiting WoW. The updater reapplies the latest realm capture after external database updates so observed IDs, known spells, icons, stats, and coordinates survive.

### Project 1999 Wiki — optional reference

The [Project 1999 Wiki](https://wiki.project1999.com/) may supply lore and quest prose only when EQWOW and captured facts do not provide it. It is community-maintained and never overrides realm IDs or captured client facts.

## Data precedence

When facts conflict, NorrathIQ uses this order:

1. Client-captured facts for matching realm IDs.
2. EQWOW Database records.
3. Reviewed user corrections.
4. P99 descriptions where higher-priority sources are silent.

Every compiled fact can retain source, revision or snapshot, confidence, and field origin. Custom EQWOW/WoW spells occupy a separate namespace and are never merged with P99/EverQuest spells through fuzzy names.

## Maps and coordinates

NorrathIQ supports two navigation paths:

- **Native map pins** use realm map IDs and normalized coordinates supplied by a realm export or map-provider addon.
- **EQ atlas maps** use zone transforms, camps, spawn points, path lines, and a generated coordinate grid.

The WoW 3.3.5 API usually exposes the player's position, not an NPC's exact position. Captured NPC coordinates therefore mean “the player was here while observing this NPC.” When coordinates are uncertain, NorrathIQ opens the correct zone and displays text instead of inventing an exact pin.

## Performance model

The in-game addon is designed around a small core and load-on-demand data packs:

- the complete source snapshot is compiled outside WoW;
- the initially loaded global catalog remains small;
- searches load only the shard associated with the requested prefix;
- details load only after an explicit search or selection needs them;
- tooltip hovers never load search or detail shards;
- live discoveries use constant-scope incremental index updates;
- bag scans are coalesced and unchanged items use cached metadata;
- the full 190,000+ record source is never parsed or indexed in one in-game operation.

The first explicit search for a new prefix can load a shard. Later searches reuse it for the remainder of the session.

## Troubleshooting

### `/niq` does nothing

- Press Enter after typing the command.
- Confirm NorrathIQ is enabled on the character-selection AddOns screen.
- Enable **Load out of date AddOns** if required by the custom client.
- Run `/niq version` and look for `capture module: loaded`.

### The journal opens but results stay empty

- Wait for the chat message reporting that the relevant EQWOW search data is ready.
- Search an exact name first.
- Confirm the `NorrathIQ_Data_*` directories are beside `NorrathIQ` under `Interface\AddOns`.
- Run **Install / Repair Addon** with WoW fully closed.

### Hovering items says database data is loading

Current builds prohibit all database-pack loading from tooltip hovers. This message means WoW is still using an older active copy:

1. Exit WoW completely.
2. Open the updater.
3. Click **Apply staged update** under advanced options, or run **Install / Repair Addon**.
4. Restart WoW; `/reload` alone cannot replace addon files already loaded from disk at startup.

### Hovering causes low FPS

- Apply the latest staged update using the steps above.
- Verify `/niq version` matches the packaged release.
- Use `/niq capture status` to confirm the capture module loaded correctly.
- If the problem persists, disable **Tooltips** in the journal temporarily and report the exact item name and chat messages shown during the hover.

### Capture data is missing from the updater

- Enable capture with `/niq capture on`.
- Run `/reload` or log out so WoW writes SavedVariables.
- Confirm the updater points to the correct client or AddOns directory.
- Click **Process captured data now**.
- See [`docs/CAPTURE.md`](docs/CAPTURE.md) for manual paths and advanced import commands.

### An update is staged but not active

Staging is intentional when WoW is detected. Close every WoW client process, then use **Apply staged update**. The installer keeps a backup and restores it automatically if replacement fails.

## Installing manually

Copy the following directories into `World of Warcraft\Interface\AddOns` while WoW is closed:

```text
NorrathIQ
NorrathIQ_Data_<snapshot>_Index
NorrathIQ_Data_<snapshot>_Search_...
NorrathIQ_Data_<snapshot>_<entity>_...
```

The resulting layout must be:

```text
Interface\AddOns\NorrathIQ\NorrathIQ.toc
Interface\AddOns\NorrathIQ_Data_...\NorrathIQ_Data_....toc
```

A common mistake is creating an extra nesting level such as `Interface\AddOns\NorrathIQ-1.3.0\NorrathIQ\NorrathIQ.toc`. WoW will not recognize that layout.

## Updater CLI

Run commands from the repository root with Python 3.12+:

```powershell
python -m updater.norrathiq.cli validate data\seed
python -m updater.norrathiq.cli compile data\seed build
python -m updater.norrathiq.cli install addon "C:\Games\World of Warcraft 3.3.5\Interface\AddOns"
python -m updater.norrathiq.cli apply-staged "C:\Games\World of Warcraft 3.3.5\Interface\AddOns"
python -m updater.norrathiq.cli gui
```

EQWOW source operations:

```powershell
python -m updater.norrathiq.cli check-source --cache .cache\eqwow.sqlite3
python -m updater.norrathiq.cli source-status --cache .cache\eqwow.sqlite3
python -m updater.norrathiq.cli crawl-source --cache .cache\eqwow.sqlite3
python -m updater.norrathiq.cli review-update --cache .cache\eqwow.sqlite3
python -m updater.norrathiq.cli apply-update "C:\Games\WoW\Interface\AddOns" --cache .cache\eqwow.sqlite3 --confirm
```

Capture import and realm merge:

```powershell
python -m updater.norrathiq.cli import-capture "C:\Games\WoW\WTF\Account\ACCOUNT\SavedVariables\NorrathIQ.lua" data\my-realm --realm "My Realm"
python -m updater.norrathiq.cli merge-realm data\seed data\my-realm data\merged
python -m updater.norrathiq.cli validate data\merged
python -m updater.norrathiq.cli compile data\merged build\my-realm
python -m updater.norrathiq.cli install build\my-realm "C:\Games\WoW\Interface\AddOns"
```

Optional P99 reference refresh:

```powershell
python -m updater.norrathiq.cli refresh-p99 data\p99 --title "Moonstones Quest" --title "A Gnoll Hunter" --category Items --cache .cache\p99.sqlite3
```

The crawler uses one request at a time, waits at least one second between requests, checkpoints every detail, resumes after interruption, partitions indexes at the site's 8,000-row cap, and quarantines candidates when validation or mass-change thresholds fail.

## Portable realm bundle

Portable bundles contain:

```text
manifest.json
items.jsonl
npcs.jsonl
quests.jsonl
recipes.jsonl
zones.jsonl
containers.jsonl
spells.jsonl
edges.jsonl
spawns.jsonl
aliases.jsonl
maps.json
```

The versioned JSON Schema is [`schema/norrathiq-bundle.schema.json`](schema/norrathiq-bundle.schema.json). Realm records may include realm/client IDs, quest IDs, P99 page IDs, class/skill/slot mappings, native maps, coordinates, paths, WoW stats, icons, and field-level provenance.

Fuzzy matches are review candidates only and are never accepted silently.

## Public Lua API

Third-party addons can use the read-only global `NorrathIQ_API`:

```lua
local results = NorrathIQ_API.Search("Gnoll Fang", "item", 20)
local item = NorrathIQ_API.GetEntity("eqwow:item:95750")
local relations = NorrathIQ_API.GetRelations(item)
NorrathIQ_API.ShowOnMap(item, "source")
```

Integration hooks are also available:

```lua
NorrathIQ_API.RegisterBagAdapter("MyBagAddon", adapter)
NorrathIQ_API.RegisterMapProvider("MyMapAddon", provider)
```

See [`addon/NorrathIQ/API.lua`](addon/NorrathIQ/API.lua) for the current call signatures.

## Repository layout

| Path | Contents |
| --- | --- |
| [`addon/NorrathIQ`](addon/NorrathIQ) | Dependency-free WoW 3.3.5 Lua addon. |
| [`updater/norrathiq`](updater/norrathiq) | GUI, CLI, importers, crawler, compiler, validator, and installer. |
| [`data/seed`](data/seed) | Checked deterministic starter fixtures. |
| [`schema`](schema) | Portable bundle JSON Schema. |
| [`tests`](tests) | Python pipeline, installer, security, and Lua contract tests. |
| [`docs`](docs) | Capture, realm export, in-client testing, and source documentation. |
| [`scripts`](scripts) | Verification, updater build, and release packaging scripts. |

## Development and verification

Run the full deterministic verification suite:

```powershell
python -m pytest -q
.\scripts\verify.ps1
```

Build the updater and release archives:

```powershell
.\scripts\build-updater.ps1
.\scripts\package-release.ps1 -Version 1.3.0
```

The current contract tests cover:

- WoW Interface `30300` and Lua file loading order;
- tooltip safety and no automatic item actions;
- incremental live discovery and minimap controls;
- load-on-demand search behavior;
- capture parsing as inert Lua literals;
- exact-ID realm merging and WoW/EQ spell separation;
- deterministic compilation and reserved-word-safe Lua output;
- atomic installation, staging, backups, rollback, and zip-slip rejection;
- golden Gnoll Fang, Tasarin's Grimoire, broken-staff, and Rough Elm Recurve Bow relationships.

The required manual client checks are in [`docs/IN_CLIENT_TESTS.md`](docs/IN_CLIENT_TESTS.md). Realm-export details are in [`docs/REALM_EXPORT.md`](docs/REALM_EXPORT.md).

## Privacy and security

- The in-game addon has no networking capability.
- Capture is local and opt-in for persistence.
- Capture does not collect chat, credentials, real-world identity, arbitrary files, group-member inventories, or combat performance.
- The updater parses SavedVariables and downloaded source records as inert data and never executes them.
- Remote responses are sanitized, size-limited, host-restricted, and Lua-escaped during compilation.
- Updates are compiled into a candidate directory, validated, checksummed, and installed atomically with backup and rollback.
- No captured data is uploaded automatically.

## Known limitations

- English only in v1.
- The updater is Windows-focused.
- Exact native-map precision depends on realm exports and map-provider support.
- Captured NPC points represent sampled player positions and may not be exact spawns.
- Observed loot windows are evidence, not authoritative drop rates.
- P99 is community-maintained and may contain inaccuracies.
- EQWOW's primary database is HTTP-only and therefore cannot provide authenticated transport.

## License and data policy

Code in this repository is covered by [`LICENSE`](LICENSE). Verify redistribution rights before publishing third-party text, icons, or map artwork. NorrathIQ defaults to realm-provided item icons and a neutral generated coordinate grid; it does not require redistributed third-party map art.
