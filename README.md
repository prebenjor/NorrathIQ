# NorrathIQ

NorrathIQ is an offline EverQuest knowledge addon for WoW 3.3.5 EQWOW realms. The Windows updater downloads and compiles realm data; the in-game addon performs no network requests and no longer observes or stores gameplay activity.

## Features

- Search items, NPCs, quests, recipes, spells, zones, and keys.
- Show uses, drops, quests, recipes, recommendations, source records, and map actions in item tooltips.
- Mark bags with `Q` quest, `T` tradeskill, `R` research, `K` key/important, and `$` conservative vendor badges.
- Resolve quest objectives and compare mapped equipment stats.
- Navigate through native map providers or the built-in EQ atlas fallback.
- Update atomically with validation, backup, rollback, and staging while WoW is running.

NorrathIQ never sells, destroys, moves, equips, accepts, or turns in anything automatically.

## Requirements

Players need a WoW 3.3.5 client using Interface `30300`. The packaged updater does not require Python.

Maintainers need Python 3.12+, PowerShell, and [`updater/requirements.lock`](updater/requirements.lock).

## Install

1. Close WoW.
2. Open **NorrathIQ Updater**.
3. Confirm the AddOns and local `NorrathIQ-release` folders under **Show advanced options** if needed.
4. Click **Install / Repair Addon**.
5. Enable NorrathIQ on the character-selection AddOns screen.
6. Open it with the minimap book icon or `/niq`.

If WoW is running, the updater stages the files. Close WoW and the open updater applies the staged update automatically; **Apply staged update** is also available under advanced options.

Default paths use the current Windows home directory. Packagers can override them with `NORRATHIQ_RELEASE_SOURCE` and `NORRATHIQ_ADDONS_TARGET`.

## Use

- Click the minimap book to open or close the Knowledge Journal; drag it to reposition it.
- Search an exact or partial name and use the category selector to narrow results.
- Hover an item to show knowledge already loaded for it. Hovering never queues or loads database shards.
- Click **Source Map**, **Turn-in**, **Related**, **Recipe**, or **Database URL** on a selected record when available.

Inventory guidance is deliberately conservative: keys, quests, recipes, research, and tradeskill relations block discard advice. `$`, Vendor, and Destroy require a full record explicitly marked `verifiedNoUse`; a vendor price alone is never enough.

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

## Update knowledge

The [EQWOW Database](http://50.6.248.85/dbviewer/) is the primary source for realm IDs, fusion spells, stats, drops, quests, NPC levels, and coordinates.

1. **Check now** compares source indexes.
2. **Review changes** shows added, changed, and missing records.
3. **Complete all database details** resumes the checkpointed detail crawl. NPCs are prioritized. The source allows one request per second, so a complete first crawl takes roughly 54 hours and can be paused safely.
4. **Download one zone map** accepts an EQWOW zone ID and fetches that zone's listed NPC/object coordinate pages without waiting for the complete crawl.
5. **Apply validated update** compiles and installs the reviewed snapshot.

The database is HTTP-only. Requests are restricted to `50.6.248.85/dbviewer/`; redirects, response sizes, parsing, and fingerprints are validated. Fingerprints detect changes but cannot authenticate the server.

The [Project 1999 Wiki](https://wiki.project1999.com/) is an optional source for missing prose and never overrides EQWOW fields. Custom EQWOW/WoW spells remain separate from P99/EverQuest spells even when names match.

## Performance

- Source data is compiled outside WoW.
- Search data is split into prefix shards and details are load-on-demand.
- Tooltips never load search or detail shards.
- Bag scans are coalesced and reuse cached item metadata.
- The full source database is never indexed in one in-game operation.
- No gameplay observer, capture event listeners, or capture SavedVariables are installed.

The first explicit search for a prefix may pause briefly while its shard loads. Later searches reuse it for that session.

## Troubleshooting

### `/niq` does not open

Press Enter after typing the command, confirm NorrathIQ is enabled, and enable **Load out of date AddOns** if required.

### Search results are empty

- Search an exact name first.
- Wait for the EQWOW search-ready chat message.
- Confirm `NorrathIQ_Data_*` folders are beside `NorrathIQ` in `Interface\AddOns`.
- Run **Install / Repair Addon** with WoW closed.

### Hovering loads data or reduces FPS

Version 1.3.7 does not load or observe data from hovers. Apply any staged update with WoW closed, restart the client, and check `/niq version`. `/reload` does not replace staged files.

### A staged update is not active

Close all WoW processes and click **Apply staged update**. The installer restores its backup automatically if replacement fails.

## Manual installation

Copy `NorrathIQ` and every supplied `NorrathIQ_Data_*` folder directly into `Interface\AddOns` while WoW is closed. Do not add an extra release-folder nesting level.

## Maintainer CLI

```powershell
python -m updater.norrathiq.cli validate data\seed
python -m updater.norrathiq.cli compile data\seed build
python -m updater.norrathiq.cli install addon "C:\Games\WoW\Interface\AddOns"
python -m updater.norrathiq.cli apply-staged "C:\Games\WoW\Interface\AddOns"
python -m updater.norrathiq.cli gui

python -m updater.norrathiq.cli check-source --cache .cache\eqwow.sqlite3
python -m updater.norrathiq.cli source-status --cache .cache\eqwow.sqlite3
python -m updater.norrathiq.cli crawl-source --cache .cache\eqwow.sqlite3
python -m updater.norrathiq.cli crawl-zone 5218 --cache .cache\eqwow.sqlite3
python -m updater.norrathiq.cli review-update --cache .cache\eqwow.sqlite3
python -m updater.norrathiq.cli apply-update "C:\Games\WoW\Interface\AddOns" --cache .cache\eqwow.sqlite3 --confirm
```

Bundle schema: [`schema/norrathiq-bundle.schema.json`](schema/norrathiq-bundle.schema.json). Realm-export contract: [`docs/REALM_EXPORT.md`](docs/REALM_EXPORT.md).

## Lua API

```lua
local results = NorrathIQ_API.Search("Gnoll Fang", "item", 20)
local item = NorrathIQ_API.GetEntity("eqwow:item:95750")
local relations = NorrathIQ_API.GetRelations(item)
NorrathIQ_API.ShowOnMap(item, "source")
NorrathIQ_API.RegisterBagAdapter("MyBagAddon", adapter)
NorrathIQ_API.RegisterMapProvider("MyMapAddon", provider)
```

See [`addon/NorrathIQ/API.lua`](addon/NorrathIQ/API.lua).

## Verify and package

```powershell
python -m pytest -q
.\scripts\verify.ps1
.\scripts\build-updater.ps1
.\scripts\package-release.ps1 -Version 1.3.7
```

Manual client checks are in [`docs/IN_CLIENT_TESTS.md`](docs/IN_CLIENT_TESTS.md).

## Privacy and limitations

- The addon has no networking or gameplay-observation functionality.
- Only UI settings are stored in SavedVariables.
- Downloaded records are sanitized and parsed as inert data.
- Updates are validated, checksummed, and installed with rollback.
- V1 is English-only and the updater is Windows-focused.
- P99 is community-maintained; EQWOW uses unauthenticated HTTP.

## License

Code is covered by [`LICENSE`](LICENSE). Confirm redistribution rights before publishing third-party text, icons, or map artwork.
