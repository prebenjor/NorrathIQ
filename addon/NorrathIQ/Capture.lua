local NIQ = NorrathIQ
local Capture = {
    pendingBagScan = false, pendingQuestScan = false,
    bagElapsed = 0, questElapsed = 0, lastTarget = nil, lastKill = nil,
}
NIQ.Capture = Capture
NIQ:RegisterModule("Capture", Capture)

local CAPTURE_SCHEMA = 1
local MAX_NPC_POINTS = 80
local liveEvents = {
    "PLAYER_TARGET_CHANGED", "QUEST_DETAIL", "QUEST_PROGRESS",
    "QUEST_COMPLETE", "QUEST_GREETING", "QUEST_ACCEPTED", "LOOT_OPENED",
    "BANKFRAME_OPENED", "MERCHANT_SHOW",
}
local captureOnlyEvents = {
    "TRADE_SKILL_SHOW", "TRADE_SKILL_UPDATE", "ZONE_CHANGED_NEW_AREA",
    "COMBAT_LOG_EVENT_UNFILTERED", "SPELLS_CHANGED",
}

local function countKeys(value)
    local count = 0
    for _ in pairs(value or {}) do count = count + 1 end
    return count
end

local function increment(record, key)
    record[key] = (record[key] or 0) + 1
end

local function normalizedKey(value)
    local normalized = NIQ:Normalize(value)
    normalized = string.gsub(normalized, "%s+", "-")
    return normalized ~= "" and normalized or "unknown"
end

local function now()
    return time and time() or 0
end

local function entitySignature(value, parts, depth)
    parts = parts or {}
    depth = depth or 0
    local valueType = type(value)
    if valueType ~= "table" then
        table.insert(parts, valueType .. ":" .. tostring(value))
        return table.concat(parts, "\030")
    end
    if depth > 4 then
        table.insert(parts, "table:max")
        return table.concat(parts, "\030")
    end
    local keys = {}
    for key in pairs(value) do
        if key ~= "observedAt" and key ~= "_signature" and key ~= "_overlay" and key ~= "_priority" then
            table.insert(keys, key)
        end
    end
    table.sort(keys, function(left, right) return tostring(left) < tostring(right) end)
    table.insert(parts, "{")
    for _, key in ipairs(keys) do
        table.insert(parts, tostring(key))
        entitySignature(value[key], parts, depth + 1)
    end
    table.insert(parts, "}")
    return table.concat(parts, "\030")
end

local function itemIdFromLink(link)
    return link and tonumber(string.match(link, "item:(%-?%d+)")) or nil
end

local function spellIdFromLink(link)
    return link and tonumber(string.match(link, "spell:(%-?%d+)")) or nil
end

local function npcEntryFromGuid(guid)
    if not guid or type(guid) ~= "string" then return nil end
    if string.sub(guid, 1, 6) == "0xF130" or string.sub(guid, 1, 6) == "0xF150" then
        return tonumber(string.sub(guid, 7, 12), 16)
    end
    return nil
end

function Capture:Initialize()
    NorrathIQCaptureDB = NorrathIQCaptureDB or {
        schemaVersion = CAPTURE_SCHEMA,
        enabled = false,
        realms = {},
    }
    if NorrathIQCaptureDB.schemaVersion ~= CAPTURE_SCHEMA then
        NorrathIQCaptureDB = {
            schemaVersion = CAPTURE_SCHEMA,
            enabled = false,
            realms = {},
            migrationNotice = "Previous capture schema was incompatible and was reset.",
        }
    end
    self.db = NorrathIQCaptureDB
    self:InitializeLivePack()
    for _, event in ipairs(liveEvents) do NIQ.eventFrame:RegisterEvent(event) end
    self:SetCaptureOnlyEvents(self.db.enabled)
    self.timer = CreateFrame("Frame")
    self.timer:Hide()
    self.timer:SetScript("OnUpdate", function(_, elapsed)
        if self.pendingBagScan then self.bagElapsed = self.bagElapsed + elapsed end
        if self.pendingQuestScan then self.questElapsed = self.questElapsed + elapsed end
        if self.pendingBagScan and self.bagElapsed >= 0.4 then
            self.bagElapsed, self.pendingBagScan = 0, false
            self:ScanContainers("bags")
        end
        if self.pendingQuestScan and self.questElapsed >= 0.3 then
            self.questElapsed, self.pendingQuestScan = 0, false
            self:CaptureQuestLog()
        end
        if not self.pendingBagScan and not self.pendingQuestScan then self.timer:Hide() end
    end)
    if self.db.enabled then
        self:TouchRealmMetadata()
        self:ScheduleBagScan()
    end
end

function Capture:SetCaptureOnlyEvents(enabled)
    for _, event in ipairs(captureOnlyEvents) do
        if enabled then NIQ.eventFrame:RegisterEvent(event) else NIQ.eventFrame:UnregisterEvent(event) end
    end
end

function Capture:IsEnabled()
    return self.db and self.db.enabled == true
end

function Capture:IsObserving()
    return self:IsEnabled() or not NIQ.db or NIQ.db.liveDiscovery ~= false
end

function Capture:GetWorkingRealm()
    if self:IsEnabled() then return self:GetRealmDB() end
    self.sessionRealm = self.sessionRealm or {
        meta = { realm = self:GetRealmKey(), sessionOnly = true },
        items = {}, npcs = {}, quests = {}, recipes = {}, spells = {}, loot = {},
    }
    return self.sessionRealm
end

function Capture:GetRealmKey()
    local realm = GetRealmName and GetRealmName() or "Unknown Realm"
    if not realm or realm == "" then realm = "Unknown Realm" end
    return realm
end

function Capture:GetRealmDB()
    local realmKey = self:GetRealmKey()
    local realm = self.db.realms[realmKey]
    if not realm then
        realm = {
            meta = { realm = realmKey, firstSeen = now(), lastSeen = now(), characters = {} },
            items = {}, npcs = {}, quests = {}, recipes = {}, spells = {}, loot = {},
        }
        self.db.realms[realmKey] = realm
    end
    realm.meta = realm.meta or { realm = realmKey, firstSeen = now(), characters = {} }
    realm.meta.characters = realm.meta.characters or {}
    realm.items, realm.npcs, realm.quests = realm.items or {}, realm.npcs or {}, realm.quests or {}
    realm.recipes, realm.spells, realm.loot = realm.recipes or {}, realm.spells or {}, realm.loot or {}
    return realm
end

function Capture:PublishEntity(id, entity)
    if not self.livePack or not id or not entity or not entity.name then return end
    local signature = entitySignature(entity)
    local existing = self.livePack.entities[id]
    if existing and existing._signature == signature then
        existing.observedAt = now()
        return false
    end
    entity.id = id
    entity._overlay = true
    entity._priority = 400
    entity.observedAt = now()
    entity._signature = signature
    self.livePack.entities[id] = entity
    return NIQ.Data:ApplyOverlay(id, entity)
end

function Capture:PublishItem(record)
    if not record or not record.clientId or not record.name then return end
    self:PublishEntity("eqwow:item:" .. tostring(record.clientId), {
        type = "item", name = record.name, clientId = record.clientId, realmId = record.clientId,
        classification = record.itemSubType or record.itemType or "Observed Item",
        icon = record.icon, requiredLevel = record.requiredLevel, itemLevel = record.itemLevel,
        equipLoc = record.equipLoc, vendorValue = record.vendorValue, stats = record.stats,
        source = { name = "Game capture", sourceId = "game-capture", confidence = "observed" },
    })
end

function Capture:PublishNPC(key, record)
    if not record or not record.name then return end
    local id = record.entryId and ("eqwow:npc:" .. tostring(record.entryId)) or ("capture:npc:" .. normalizedKey(key))
    local newest
    for _, point in pairs(record.observations or {}) do
        if not newest or (point.lastSeen or point.firstSeen or 0) > (newest.lastSeen or newest.firstSeen or 0) then newest = point end
    end
    local level
    if record.minLevel and record.maxLevel then
        level = record.minLevel == record.maxLevel and tostring(record.minLevel) or (tostring(record.minLevel) .. "-" .. tostring(record.maxLevel))
    end
    self:PublishEntity(id, {
        type = "npc", name = record.name, clientId = record.entryId, realmId = record.entryId,
        classification = record.classification or record.creatureType or "Observed NPC",
        level = level, zone = (newest and newest.zone) or record.lastZone,
        map = newest and newest.x and { zone = newest.zone, mapId = newest.mapId, x = newest.x, y = newest.y, confidence = "observed" } or nil,
        source = { name = "Game capture", sourceId = "game-capture", confidence = "observed" },
    })
end

function Capture:PublishQuest(key, record)
    if not record or not record.name then return end
    local id = record.questId and record.questId > 0 and ("eqwow:quest:" .. tostring(record.questId))
        or ("capture:quest:" .. normalizedKey(key))
    local objectives = {}
    for _, objective in ipairs(record.objectives or {}) do
        table.insert(objectives, type(objective) == "table" and objective.text or tostring(objective))
    end
    self:PublishEntity(id, {
        type = "quest", name = record.name, questId = record.questId, clientId = record.questId,
        classification = "Observed Quest", level = record.level, objectives = objectives,
        source = { name = "Game capture", sourceId = "game-capture", confidence = "observed" },
    })
end

function Capture:InitializeLivePack()
    local realm = self.db.realms[self:GetRealmKey()] or {}
    self.livePack = {
        meta = {
            id = "capture-live:" .. normalizedKey(self:GetRealmKey()), schemaVersion = NIQ.schemaVersion,
            version = NIQ.version, source = "Observed in WoW client", captureTimestamp = tostring(now()),
        },
        entities = {}, spawns = {}, zones = {},
    }
    NIQ:RegisterDataPack(self.livePack)
    for _, record in pairs(realm.items or {}) do self:PublishItem(record) end
    for key, record in pairs(realm.npcs or {}) do self:PublishNPC(key, record) end
    for key, record in pairs(realm.quests or {}) do self:PublishQuest(key, record) end
end

function Capture:TouchRealmMetadata()
    if not self:IsEnabled() then return end
    local realm = self:GetRealmDB()
    realm.meta.lastSeen = now()
    local character = UnitName and UnitName("player")
    if character then
        local className, classToken = UnitClass and UnitClass("player")
        local raceName, raceToken = UnitRace and UnitRace("player")
        realm.meta.characters[character] = {
            class = className, classToken = classToken, race = raceName, raceToken = raceToken,
            faction = UnitFactionGroup and UnitFactionGroup("player") or nil,
            level = UnitLevel and UnitLevel("player") or nil, lastSeen = now(),
        }
    end
    if GetBuildInfo then
        local version, build, _, toc = GetBuildInfo()
        realm.meta.clientVersion = version
        realm.meta.clientBuild = build
        realm.meta.interface = toc
    end
end

function Capture:GetPosition(includeCoordinates)
    local position = {
        zone = GetRealZoneText and GetRealZoneText() or (GetZoneText and GetZoneText()) or "Unknown",
        subzone = GetSubZoneText and GetSubZoneText() or nil,
        observedAt = now(),
    }
    if not includeCoordinates then return position end
    local previousMap = GetCurrentMapAreaID and GetCurrentMapAreaID() or nil
    if SetMapToCurrentZone then pcall(SetMapToCurrentZone) end
    position.mapId = GetCurrentMapAreaID and GetCurrentMapAreaID() or previousMap
    if GetPlayerMapPosition then
        local x, y = GetPlayerMapPosition("player")
        if x and y and x > 0 and x <= 1 and y > 0 and y <= 1 then
            position.x, position.y = x, y
        end
    end
    if previousMap and position.mapId ~= previousMap and SetMapByID then pcall(SetMapByID, previousMap) end
    return position
end

function Capture:ObserveItem(link, source)
    if not self:IsObserving() or not link then return nil end
    local itemId = itemIdFromLink(link)
    if not itemId then return nil end
    local realm = self:GetWorkingRealm()
    local key = tostring(itemId)
    local record = realm.items[key]
    if record and source ~= "manual_rescan" and record.itemInfoCaptured then
        record.lastSeen = now()
        local sourceKey = source or "unknown"
        if not record.sources[sourceKey] then record.sources[sourceKey] = 1 end
        return key
    end
    if not record then
        record = { clientId = itemId, firstSeen = now(), sources = {}, stats = {} }
        realm.items[key] = record
    end
    local name, _, quality, itemLevel, requiredLevel, itemType, itemSubType,
        maxStack, equipLoc, texture, vendorValue = GetItemInfo(link)
    record.name = name or record.name or NIQ:ItemNameFromLink(link)
    if name then record.itemInfoCaptured = true end
    record.quality = quality or record.quality
    record.itemLevel = itemLevel or record.itemLevel
    record.requiredLevel = requiredLevel or record.requiredLevel
    record.itemType = itemType or record.itemType
    record.itemSubType = itemSubType or record.itemSubType
    record.maxStack = maxStack or record.maxStack
    record.equipLoc = equipLoc or record.equipLoc
    record.icon = texture or record.icon
    record.vendorValue = vendorValue or record.vendorValue
    if GetItemStats then
        local stats = GetItemStats(link)
        for stat, value in pairs(stats or {}) do record.stats[stat] = value end
    end
    if NIQ.Recommendation and NIQ.Recommendation.GetWeaponMetrics then
        local weapon = NIQ.Recommendation:GetWeaponMetrics(link)
        if weapon then
            record.weaponDamageMin = weapon.minimum
            record.weaponDamageMax = weapon.maximum
            record.weaponSpeed = weapon.speed
        end
    end
    record.lastSeen = now()
    increment(record.sources, source or "unknown")
    self:PublishItem(record)
    return key
end

function Capture:ScheduleBagScan()
    if self:IsObserving() then
        self.pendingBagScan, self.bagElapsed = true, 0
        if self.timer then self.timer:Show() end
    end
end

function Capture:ScheduleQuestScan()
    if self:IsObserving() then
        self.pendingQuestScan, self.questElapsed = true, 0
        if self.timer then self.timer:Show() end
    end
end

function Capture:ScanContainers(source)
    if not self:IsObserving() or not GetContainerNumSlots or not GetContainerItemLink then return end
    for bag = -1, 11 do
        local slots = GetContainerNumSlots(bag) or 0
        for slot = 1, slots do self:ObserveItem(GetContainerItemLink(bag, slot), source) end
    end
    if source == "bank" and GetInventoryItemLink then
        for slot = 39, 67 do self:ObserveItem(GetInventoryItemLink("player", slot), "bank") end
    end
    if GetInventoryItemLink then
        for slot = 1, 19 do self:ObserveItem(GetInventoryItemLink("player", slot), "equipment") end
    end
    if NIQ.Inventory then NIQ.Inventory:Schedule() end
end

function Capture:ScanMerchant()
    if not self:IsObserving() or not GetMerchantNumItems or not GetMerchantItemLink then return end
    for index = 1, GetMerchantNumItems() do self:ObserveItem(GetMerchantItemLink(index), "merchant") end
end

function Capture:ObserveNPC(unit, context)
    if not self:IsObserving() or not UnitExists or not UnitExists(unit) or (UnitIsPlayer and UnitIsPlayer(unit)) then return nil end
    local guid = UnitGUID and UnitGUID(unit)
    local name = UnitName and UnitName(unit)
    if not guid and not name then return nil end
    local entryId = npcEntryFromGuid(guid)
    local key = entryId and tostring(entryId) or (guid and "guid:" .. guid) or "name:" .. normalizedKey(name)
    local realm = self:GetWorkingRealm()
    local record = realm.npcs[key]
    if not record then
        record = { entryId = entryId, guidSamples = {}, firstSeen = now(), contexts = {}, observations = {} }
        realm.npcs[key] = record
    end
    record.name = name or record.name
    if guid and countKeys(record.guidSamples) < 8 then record.guidSamples[guid] = true end
    local level = UnitLevel and UnitLevel(unit)
    if level and level > 0 then
        record.minLevel = math.min(record.minLevel or level, level)
        record.maxLevel = math.max(record.maxLevel or level, level)
    end
    record.classification = UnitClassification and UnitClassification(unit) or record.classification
    record.creatureType = UnitCreatureType and UnitCreatureType(unit) or record.creatureType
    record.reaction = UnitReaction and UnitReaction("player", unit) or record.reaction
    record.lastSeen = now()
    increment(record.contexts, context or "target")
    local position = self:GetPosition(self:IsEnabled())
    record.lastZone = position.zone
    self:AddNPCPosition(record, position, context)
    self.lastTarget = { key = key, guid = guid, name = name, observedAt = now() }
    self:PublishNPC(key, record)
    return key
end

function Capture:AddNPCPosition(record, position, context)
    if not position or not position.x or not position.y then return end
    local gridX, gridY = math.floor(position.x * 200 + 0.5), math.floor(position.y * 200 + 0.5)
    local pointKey = tostring(position.mapId or position.zone) .. ":" .. gridX .. ":" .. gridY
    local point = record.observations[pointKey]
    if not point then
        if countKeys(record.observations) >= MAX_NPC_POINTS then return end
        point = {
            mapId = position.mapId, zone = position.zone, subzone = position.subzone,
            x = position.x, y = position.y, count = 0, firstSeen = now(), contexts = {},
        }
        record.observations[pointKey] = point
    else
        local nextCount = point.count + 1
        point.x = ((point.x * point.count) + position.x) / nextCount
        point.y = ((point.y * point.count) + position.y) / nextCount
    end
    point.count = point.count + 1
    point.lastSeen = now()
    increment(point.contexts, context or "observed")
end

function Capture:CaptureQuestLog()
    if not self:IsObserving() or not GetNumQuestLogEntries or not GetQuestLogTitle then return end
    local realm = self:GetWorkingRealm()
    for questIndex = 1, GetNumQuestLogEntries() do
        local title, level, tag, isHeader, _, isComplete, frequency, questId = GetQuestLogTitle(questIndex)
        if title and not isHeader then
            local key = questId and questId > 0 and tostring(questId) or "title:" .. normalizedKey(title)
            local temporaryKey = "title:" .. normalizedKey(title)
            local record = realm.quests[key]
            if not record and temporaryKey ~= key and realm.quests[temporaryKey] then
                record = realm.quests[temporaryKey]
                realm.quests[temporaryKey] = nil
            end
            record = record or { firstSeen = now(), objectives = {}, interactions = {} }
            realm.quests[key] = record
            record.questId, record.name, record.level = questId, title, level
            record.tag, record.frequency, record.complete = tag, frequency, isComplete
            record.lastSeen = now()
            record.objectives = {}
            local count = GetNumQuestLeaderBoards and GetNumQuestLeaderBoards(questIndex) or 0
            for objectiveIndex = 1, count do
                local description, objectiveType, complete = GetQuestLogLeaderBoard(objectiveIndex, questIndex)
                table.insert(record.objectives, {
                    text = description, objectiveType = objectiveType, complete = complete and true or false,
                })
            end
            self:PublishQuest(key, record)
        end
    end
end

function Capture:CurrentQuestRecord()
    local title = GetTitleText and GetTitleText()
    if not title or title == "" then return nil end
    local realm = self:GetWorkingRealm()
    local questId = GetQuestID and GetQuestID()
    if questId and questId > 0 then
        local key = tostring(questId)
        local temporaryKey = "title:" .. normalizedKey(title)
        local record = realm.quests[key] or realm.quests[temporaryKey]
        realm.quests[temporaryKey] = nil
        record = record or { firstSeen = now(), objectives = {}, interactions = {} }
        record.questId, record.name = questId, title
        realm.quests[key] = record
        return record
    end
    for _, record in pairs(realm.quests) do
        if record.name == title then return record end
    end
    local key = "title:" .. normalizedKey(title)
    realm.quests[key] = realm.quests[key] or { name = title, firstSeen = now(), objectives = {}, interactions = {} }
    return realm.quests[key]
end

function Capture:CaptureQuestInteraction(role)
    if not self:IsObserving() then return end
    local npcKey = self:ObserveNPC("target", role)
    local quest = self:CurrentQuestRecord()
    if quest and npcKey then
        quest.interactions[npcKey] = quest.interactions[npcKey] or {}
        increment(quest.interactions[npcKey], role)
        quest.interactions[npcKey].lastSeen = now()
    end
    if quest and GetQuestItemLink then
        local choices = GetNumQuestChoices and GetNumQuestChoices() or 0
        local rewards = GetNumQuestRewards and GetNumQuestRewards() or 0
        quest.choices, quest.rewards = {}, {}
        for index = 1, choices do
            local itemKey = self:ObserveItem(GetQuestItemLink("choice", index), "quest_reward")
            if itemKey then table.insert(quest.choices, itemKey) end
        end
        for index = 1, rewards do
            local itemKey = self:ObserveItem(GetQuestItemLink("reward", index), "quest_reward")
            if itemKey then table.insert(quest.rewards, itemKey) end
        end
        quest.requiredItems = {}
        for index = 1, 10 do
            local link = GetQuestItemLink("required", index)
            if link then
                local itemKey = self:ObserveItem(link, "quest_required")
                if itemKey then table.insert(quest.requiredItems, itemKey) end
            end
        end
    end
    if quest then
        local key = quest.questId and tostring(quest.questId) or "title:" .. normalizedKey(quest.name)
        self:PublishQuest(key, quest)
    end
end

function Capture:CaptureLoot()
    if not self:IsObserving() or not GetNumLootItems or not GetLootSlotLink then return end
    local candidate, confidence
    if self.lastKill and now() - self.lastKill.observedAt <= 20 then
        candidate, confidence = self.lastKill, "medium"
    elseif self.lastTarget and now() - self.lastTarget.observedAt <= 30 then
        candidate, confidence = self.lastTarget, "low"
    end
    local realm = self:GetWorkingRealm()
    if candidate then
        realm.loot[candidate.key] = realm.loot[candidate.key] or { windows = 0, items = {} }
        realm.loot[candidate.key].windows = realm.loot[candidate.key].windows + 1
        realm.loot[candidate.key].lastSeen = now()
    end
    for slot = 1, GetNumLootItems() do
        local link = GetLootSlotLink(slot)
        local itemKey = self:ObserveItem(link, "loot")
        if candidate and itemKey then
            local lootRecord = realm.loot[candidate.key]
            lootRecord.items[itemKey] = lootRecord.items[itemKey] or { count = 0, confidence = confidence }
            lootRecord.items[itemKey].count = lootRecord.items[itemKey].count + 1
            lootRecord.items[itemKey].lastSeen = now()
        end
    end
end

function Capture:CaptureTradeskills()
    if not self:IsEnabled() or not GetNumTradeSkills or not GetTradeSkillInfo then return end
    local realm = self:GetRealmDB()
    local skillName = GetTradeSkillLine and GetTradeSkillLine() or "Unknown Tradeskill"
    for index = 1, GetNumTradeSkills() do
        local name, difficulty = GetTradeSkillInfo(index)
        if name and difficulty ~= "header" then
            local recipeLink = GetTradeSkillRecipeLink and GetTradeSkillRecipeLink(index)
            local recipeId = spellIdFromLink(recipeLink)
            local key = recipeId and tostring(recipeId) or "name:" .. normalizedKey(skillName .. "-" .. name)
            local record = realm.recipes[key] or { firstSeen = now(), components = {} }
            realm.recipes[key] = record
            record.recipeId, record.name, record.skill, record.difficulty = recipeId, name, skillName, difficulty
            record.lastSeen = now()
            local resultLink = GetTradeSkillItemLink and GetTradeSkillItemLink(index)
            record.resultItemId = self:ObserveItem(resultLink, "tradeskill_result")
            record.components = {}
            local reagents = GetTradeSkillNumReagents and GetTradeSkillNumReagents(index) or 0
            for reagentIndex = 1, reagents do
                local reagentName, _, required = GetTradeSkillReagentInfo(index, reagentIndex)
                local reagentLink = GetTradeSkillReagentItemLink and GetTradeSkillReagentItemLink(index, reagentIndex)
                table.insert(record.components, {
                    itemId = self:ObserveItem(reagentLink, "tradeskill_reagent"),
                    name = reagentName, quantity = required,
                })
            end
        end
    end
end

function Capture:CaptureSpellbook()
    if not self:IsEnabled() or not GetNumSpellTabs or not GetSpellTabInfo or not GetSpellName then return end
    local realm = self:GetRealmDB()
    for tab = 1, GetNumSpellTabs() do
        local tabName, texture, offset, count = GetSpellTabInfo(tab)
        for index = offset + 1, offset + count do
            local name, rank = GetSpellName(index, BOOKTYPE_SPELL)
            local link = GetSpellLink and GetSpellLink(index, BOOKTYPE_SPELL)
            local spellId = spellIdFromLink(link)
            if name then
                local key = spellId and tostring(spellId) or "name:" .. normalizedKey(name .. "-" .. (rank or ""))
                local record = realm.spells[key] or { firstSeen = now() }
                realm.spells[key] = record
                record.spellId, record.name, record.rank = spellId, name, rank
                record.tab = tabName
                record.icon = (GetSpellTexture and GetSpellTexture(index, BOOKTYPE_SPELL)) or texture
                if GetSpellInfo then
                    local _, _, infoIcon, cost, isFunnel, powerType, castTime, minRange, maxRange = GetSpellInfo(spellId or name)
                    record.icon = infoIcon or record.icon
                    record.cost, record.powerType, record.castTime = cost, powerType, castTime
                    record.minRange, record.maxRange = minRange, maxRange
                    record.isFunnel = isFunnel and true or false
                end
                record.passive = IsPassiveSpell and IsPassiveSpell(index, BOOKTYPE_SPELL) and true or false
                record.knownBy = record.knownBy or {}
                local character = UnitName and UnitName("player")
                if character then record.knownBy[character] = true end
                if not self.spellTooltip then
                    self.spellTooltip = CreateFrame("GameTooltip", "NorrathIQSpellScanTooltip", UIParent, "GameTooltipTemplate")
                    self.spellTooltip:SetOwner(UIParent, "ANCHOR_NONE")
                end
                self.spellTooltip:ClearLines()
                if self.spellTooltip.SetSpellBookItem then
                    self.spellTooltip:SetSpellBookItem(index, BOOKTYPE_SPELL)
                    local description = {}
                    for lineIndex = 2, self.spellTooltip:NumLines() do
                        local line = _G["NorrathIQSpellScanTooltipTextLeft" .. lineIndex]
                        local text = line and line:GetText()
                        if text and text ~= "" and text ~= rank then table.insert(description, text) end
                    end
                    if #description > 0 then record.description = table.concat(description, " ") end
                end
                record.lastSeen = now()
            end
        end
    end
end

function Capture:CaptureCombatLog(...)
    if not self:IsEnabled() then return end
    local subEvent = select(2, ...)
    if subEvent ~= "PARTY_KILL" then return end
    local guid, name = select(6, ...), select(7, ...)
    if not guid and not name then return end
    local entryId = npcEntryFromGuid(guid)
    local key = entryId and tostring(entryId) or (guid and "guid:" .. guid) or "name:" .. normalizedKey(name)
    self.lastKill = { key = key, guid = guid, name = name, observedAt = now() }
    local realm = self:GetRealmDB()
    realm.npcs[key] = realm.npcs[key] or {
        entryId = entryId, name = name, guidSamples = {}, firstSeen = now(), contexts = {}, observations = {},
    }
    increment(realm.npcs[key].contexts, "killed")
    realm.npcs[key].lastSeen = now()
end

function Capture:OnEvent(event, ...)
    if event == "BAG_UPDATE" then self:ScheduleBagScan() end
    if not self:IsObserving() then return end
    if event == "PLAYER_LOGIN" then
        self:TouchRealmMetadata()
        self:ScheduleBagScan()
        self:CaptureQuestLog()
        self:CaptureSpellbook()
    elseif event == "ZONE_CHANGED_NEW_AREA" then
        self:TouchRealmMetadata()
    elseif event == "PLAYER_TARGET_CHANGED" then
        self:ObserveNPC("target", "target")
    elseif event == "QUEST_LOG_UPDATE" or event == "QUEST_ACCEPTED" then
        self:ScheduleQuestScan()
    elseif event == "QUEST_DETAIL" then
        self:CaptureQuestInteraction("giver")
    elseif event == "QUEST_PROGRESS" then
        self:CaptureQuestInteraction("progress")
    elseif event == "QUEST_COMPLETE" then
        self:CaptureQuestInteraction("turnin")
    elseif event == "QUEST_GREETING" then
        self:ObserveNPC("target", "quest_greeting")
    elseif event == "LOOT_OPENED" then
        self:CaptureLoot()
    elseif event == "TRADE_SKILL_SHOW" or event == "TRADE_SKILL_UPDATE" then
        self:CaptureTradeskills()
    elseif event == "SPELLS_CHANGED" then
        self:CaptureSpellbook()
    elseif event == "BANKFRAME_OPENED" then
        self:ScanContainers("bank")
    elseif event == "MERCHANT_SHOW" then
        self:ScanMerchant()
    elseif event == "COMBAT_LOG_EVENT_UNFILTERED" then
        self:CaptureCombatLog(...)
    end
end

function Capture:Status()
    local realm = self.db.realms[self:GetRealmKey()] or self.sessionRealm or {}
    return string.format(
        "%s for %s - %d items, %d NPCs, %d quests, %d recipes, %d spells, %d loot sources",
        self:IsEnabled() and "ON" or "OFF", self:GetRealmKey(),
        countKeys(realm.items), countKeys(realm.npcs), countKeys(realm.quests),
        countKeys(realm.recipes), countKeys(realm.spells), countKeys(realm.loot)
    )
end

function Capture:HandleCommand(argument)
    argument = string.lower(NIQ:Normalize(argument))
    if argument == "on" then
        self.db.enabled = true
        self:SetCaptureOnlyEvents(true)
        self:TouchRealmMetadata()
        self:ScheduleBagScan()
        self:CaptureQuestLog()
        self:CaptureSpellbook()
        NIQ:Print("Realm capture enabled. Data stays local in NorrathIQCaptureDB.")
    elseif argument == "off" then
        self.db.enabled = false
        self:SetCaptureOnlyEvents(false)
        NIQ:Print("Realm capture disabled. Existing observations were preserved.")
    elseif argument == "status" or argument == "" then
        NIQ:Print("Capture " .. self:Status())
    elseif argument == "rescan" then
        self:ScanContainers("manual_rescan")
        self:CaptureQuestLog()
        self:CaptureSpellbook()
        NIQ:Print("Bags, equipment, quests, and every visible spellbook rank were rescanned.")
    elseif argument == "clear" then
        NIQ:Print("This removes observations for " .. self:GetRealmKey() .. ". Use /niq capture clear confirm.")
    elseif argument == "clear confirm" then
        self.db.realms[self:GetRealmKey()] = nil
        if self.livePack then self.livePack.entities = {} end
        NIQ.Data:Rebuild()
        NIQ:Print("Captured observations for this realm were removed.")
    else
        NIQ:Print("/niq capture <on|off|status|rescan|clear>")
    end
end
