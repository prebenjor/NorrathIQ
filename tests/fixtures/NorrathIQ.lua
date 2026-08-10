NorrathIQDB = {
    ["schemaVersion"] = 1,
    ["settings"] = { ["tooltip"] = true },
}

-- This table is parsed as inert data. It is never executed by the updater.
NorrathIQCaptureDB = {
    ["schemaVersion"] = 1,
    ["enabled"] = true,
    ["realms"] = {
        ["Test Realm"] = {
            ["meta"] = {
                ["realm"] = "Test Realm",
                ["clientVersion"] = "3.3.5",
                ["clientBuild"] = "12340",
                ["characters"] = { ["Collector"] = true },
            },
            ["items"] = {
                ["123"] = {
                    ["clientId"] = 123,
                    ["name"] = "Gnoll Fang",
                    ["itemType"] = "Quest",
                    ["vendorValue"] = 2,
                    ["sources"] = { ["loot"] = 2, ["bags"] = 1 },
                },
                ["456"] = {
                    ["clientId"] = 456,
                    ["name"] = "Rough Elm Recurve Bow",
                    ["itemType"] = "Weapon",
                    ["itemSubType"] = "Bows",
                    ["equipLoc"] = "INVTYPE_RANGED",
                    ["weaponDamageMin"] = 5,
                    ["weaponDamageMax"] = 11,
                    ["weaponSpeed"] = 2.8,
                    ["stats"] = { ["ITEM_MOD_AGILITY_SHORT"] = 2 },
                },
                ["900"] = {
                    ["clientId"] = 900,
                    ["name"] = "Rough Elm",
                    ["itemType"] = "Tradeskill",
                },
            },
            ["npcs"] = {
                ["77"] = {
                    ["entryId"] = 77,
                    ["name"] = "a gnoll hunter",
                    ["minLevel"] = 6,
                    ["maxLevel"] = 8,
                    ["classification"] = "normal",
                    ["contexts"] = { ["target"] = 4, ["killed"] = 3 },
                    ["observations"] = {
                        ["24:90:100"] = {
                            ["mapId"] = 24,
                            ["zone"] = "Qeynos Hills",
                            ["x"] = 0.45,
                            ["y"] = 0.50,
                            ["count"] = 3,
                            ["contexts"] = { ["target"] = 3 },
                        },
                    },
                },
            },
            ["quests"] = {
                ["42"] = {
                    ["questId"] = 42,
                    ["name"] = "The Broken Staff",
                    ["level"] = 8,
                    ["objectives"] = {
                        { ["text"] = "0/1 Top of Broken Staff", ["objectiveType"] = "item" },
                    },
                    ["interactions"] = {
                        ["77"] = { ["turnin"] = 1 },
                    },
                    ["requiredItems"] = { "123" },
                    ["rewards"] = { "456" },
                },
            },
            ["recipes"] = {
                ["88"] = {
                    ["recipeId"] = 88,
                    ["name"] = "Rough Elm Recurve Bow",
                    ["skill"] = "Fletching",
                    ["difficulty"] = "optimal",
                    ["resultItemId"] = "456",
                    ["components"] = {
                        { ["itemId"] = "900", ["name"] = "Rough Elm", ["quantity"] = 1 },
                    },
                },
            },
            ["loot"] = {
                ["77"] = {
                    ["windows"] = 4,
                    ["items"] = {
                        ["123"] = { ["count"] = 2, ["confidence"] = "medium" },
                    },
                },
            },
            ["spells"] = {
                ["1459"] = {
                    ["spellId"] = 1459,
                    ["name"] = "Arcane Intellect",
                    ["rank"] = "Rank 1",
                    ["tab"] = "Arcane",
                },
            },
        },
    },
}
