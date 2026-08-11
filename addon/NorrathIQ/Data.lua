local NIQ = NorrathIQ
local Data = {
    entities = {}, exact = {}, aliases = {}, zones = {}, spawns = {},
    loadedSearchPacks = {}, loadedSearchPrefixes = {}, loadedDetailPacks = {},
}
NIQ.Data = Data
NIQ:RegisterModule("Data", Data)

function Data:Initialize()
    self.deferRebuild = true
    if NorrathIQ_BundledPack then NIQ:RegisterDataPack(NorrathIQ_BundledPack) end
    self.deferRebuild = nil
    self:Rebuild()
end

local SEARCH_STOPWORDS = {
    a = true, an = true, ["and"] = true, ["for"] = true, ["in"] = true,
    of = true, on = true, the = true, to = true,
}

local function searchPrefix(text)
    local fallback
    for term in string.gmatch(NIQ:Normalize(text), "%S+") do
        fallback = fallback or term
        if not SEARCH_STOPWORDS[term] then return string.sub(term, 1, 3) end
    end
    return fallback and string.sub(fallback, 1, 3) or nil
end

local function detailHash(value)
    local result = 0
    for index = 1, string.len(value or "") do
        result = (result * 33 + string.byte(value, index)) % 64
    end
    return string.format("%02x", result)
end

local function loadAddon(name)
    local loaded, reason = LoadAddOn(name)
    if not loaded and reason ~= "ALREADY_LOADED" then
        NIQ:Print("Could not load data pack " .. name .. ": " .. tostring(reason))
        return false
    end
    return true
end

local function removeIndexedId(index, key, id)
    local values = key and index[key]
    if not values then return end
    for position = #values, 1, -1 do
        if values[position] == id then table.remove(values, position) end
    end
    if #values == 0 then index[key] = nil end
end

local function insertIndexedId(index, key, id)
    if not key or key == "" then return end
    local values = index[key]
    if not values then
        index[key] = { id }
        return
    end
    for _, existingId in ipairs(values) do
        if existingId == id then return end
    end
    table.insert(values, id)
end

-- Apply a single captured record without walking every loaded data pack. This
-- is the normal path for bag, loot, target, and quest discovery.
function Data:ApplyOverlay(id, overlay)
    if not id or not overlay or not overlay.name then return false end
    self.entities = self.entities or {}
    self.exact = self.exact or {}
    self.aliases = self.aliases or {}
    self.questIds = self.questIds or {}

    local existing = self.entities[id]
    if existing then
        removeIndexedId(self.exact, NIQ:Normalize(existing.name), id)
        for _, alias in ipairs(existing.aliases or {}) do
            removeIndexedId(self.aliases, NIQ:Normalize(alias), id)
        end
        if existing.type == "quest" or overlay.type == "quest" then
            for questId, entityId in pairs(self.questIds) do
                if entityId == id then self.questIds[questId] = nil end
            end
        end
    end

    local merged = {}
    for key, value in pairs(existing or {}) do merged[key] = value end
    for key, value in pairs(overlay) do merged[key] = value end
    if existing then
        merged._detail = existing._detail
        merged.detailPack = existing.detailPack or merged.detailPack
    end
    merged.id = id
    merged._overlay = nil
    self.entities[id] = merged

    insertIndexedId(self.exact, NIQ:Normalize(merged.name), id)
    for _, alias in ipairs(merged.aliases or {}) do
        insertIndexedId(self.aliases, NIQ:Normalize(alias), id)
    end
    if merged.type == "quest" and (merged.questId or merged.clientId) then
        local questId = merged.questId or merged.clientId
        self.questIds[tonumber(questId) or questId] = id
    end
    if not existing then self.entityCount = (self.entityCount or 0) + 1 end
    self.revision = (self.revision or 0) + 1
    return true
end

function Data:LoadExternalPacks(query)
    if not GetNumAddOns or not GetAddOnInfo or not LoadAddOn then return false end
    local startedAt = GetTime and GetTime() or nil
    local before = self.entityCount or 0
    local prefix = searchPrefix(query or "")
    local shouldAnnounce = not self.externalLoaded or (prefix and not self.loadedSearchPrefixes[prefix])
    if shouldAnnounce then
        NIQ:Print("Loading the relevant offline EQWOW search data...")
    end
    self.loadingExternal = true
    local loadedAny = false

    if not self.externalLoaded then
        self.externalLoaded = true
        local indexes, legacy = {}, {}
        for index = 1, GetNumAddOns() do
            local name = GetAddOnInfo(index)
            if name and string.find(name, "^NorrathIQ_Data_") then
                if string.find(name, "_Index$") then table.insert(indexes, name)
                elseif not string.find(name, "_Search_") then table.insert(legacy, name) end
            end
        end
        local selected = #indexes > 0 and indexes or legacy
        for _, name in ipairs(selected) do
            if loadAddon(name) then loadedAny = true end
        end
    end

    local searchNames = {}
    if prefix then
        for _, pack in pairs(NIQ.dataPacks) do
            local name = pack.meta and pack.meta.searchPacks and pack.meta.searchPacks[prefix]
            if name then searchNames[name] = true end
        end
        for name in pairs(searchNames) do
            if not self.loadedSearchPacks[name] then
                if loadAddon(name) then
                    self.loadedSearchPacks[name] = true
                    loadedAny = true
                end
            end
        end
        self.loadedSearchPrefixes[prefix] = true
    end

    self.loadingExternal = nil
    if loadedAny then self:Rebuild() end
    if shouldAnnounce then
        local elapsed = startedAt and GetTime and math.max(0, GetTime() - startedAt) or nil
        local timing = elapsed and string.format(" in %.1f seconds", elapsed) or ""
        local added = math.max(0, (self.entityCount or 0) - before)
        local total = self.externalTotal and (" of " .. tostring(self.externalTotal) .. " total") or ""
        NIQ:Print("EQWOW search ready - " .. tostring(added) .. " relevant records loaded" .. timing .. total .. ".")
    end
    return loadedAny
end

function Data:Rebuild()
    self.entities, self.exact, self.aliases, self.questIds, self.zones, self.spawns = {}, {}, {}, {}, {}, {}
    local detailPacks, detailHashPacks, overlays = {}, {}, {}
    self.externalTotal = nil
    for _, pack in pairs(NIQ.dataPacks) do
        for key, value in pairs(pack.meta and pack.meta.detailPacks or {}) do detailPacks[tostring(key)] = value end
        for entityType, hashes in pairs(pack.meta and pack.meta.detailHashPacks or {}) do
            detailHashPacks[entityType] = detailHashPacks[entityType] or {}
            for hash, name in pairs(hashes) do
                detailHashPacks[entityType][hash] = detailHashPacks[entityType][hash] or {}
                table.insert(detailHashPacks[entityType][hash], name)
            end
        end
        if pack.meta and pack.meta.searchPacks and pack.meta.searchTotal then
            self.externalTotal = (self.externalTotal or 0) + pack.meta.searchTotal
        end
    end
    self.detailHashPacks = detailHashPacks
    for _, pack in pairs(NIQ.dataPacks) do
        for id, entity in pairs(pack.entities or {}) do
            entity.id = entity.id or id
            if entity.p then
                entity.detailPack = (pack.meta and pack.meta.detailPacks and pack.meta.detailPacks[tostring(entity.p)])
                    or detailPacks[tostring(entity.p)]
            end
            if entity._overlay then
                local previous = overlays[id]
                if not previous or (entity._priority or 0) >= (previous._priority or 0) then overlays[id] = entity end
            else
                local existing = self.entities[id]
                if not existing or entity._detail or not existing._detail then self.entities[id] = entity end
            end
        end
        for zone, value in pairs(pack.zones or {}) do self.zones[zone] = value end
        for id, value in pairs(pack.spawns or {}) do self.spawns[id] = value end
    end
    for id, overlay in pairs(overlays) do
        local existing = self.entities[id]
        local merged = {}
        for key, value in pairs(existing or {}) do merged[key] = value end
        for key, value in pairs(overlay) do merged[key] = value end
        if existing then
            merged._detail = existing._detail
            merged.detailPack = existing.detailPack or merged.detailPack
        end
        merged._overlay = nil
        self.entities[id] = merged
    end
    local entityCount = 0
    for id, entity in pairs(self.entities) do
        entityCount = entityCount + 1
        insertIndexedId(self.exact, NIQ:Normalize(entity.name), id)
        for _, alias in ipairs(entity.aliases or {}) do
            insertIndexedId(self.aliases, NIQ:Normalize(alias), id)
        end
        if entity.type == "quest" and (entity.questId or entity.clientId) then
            self.questIds[tonumber(entity.questId or entity.clientId) or entity.questId or entity.clientId] = id
        end
    end
    self.entityCount = entityCount
    self.revision = (self.revision or 0) + 1
end

function Data:GetQuestByRealmId(questId)
    local id = self.questIds[tonumber(questId) or questId]
    return id and self.entities[id] or nil
end

function Data:GetEntity(id)
    if not self.entities[id] then self:LoadEntityDetail(id) end
    return self:EnsureEntityDetail(self.entities[id])
end

function Data:ResolveExact(name, loadDetails, loadExternal)
    local normalized = NIQ:Normalize(name)
    local ids = self.exact[normalized] or self.aliases[normalized]
    -- Most bag items are already present in the live overlay. Avoid loading a
    -- search shard (and rebuilding every index) simply because their tooltip
    -- was shown. External data is only needed when the loaded indexes miss.
    if not ids and normalized ~= "" and loadExternal ~= false then
        self:LoadExternalPacks(normalized)
        ids = self.exact[normalized] or self.aliases[normalized]
    end
    if not ids then return nil, "missing" end
    if #ids == 1 then
        local entity = self.entities[ids[1]]
        if loadDetails ~= false then entity = self:EnsureEntityDetail(entity) end
        return entity, "exact"
    end
    local result = {}
    for _, id in ipairs(ids) do table.insert(result, self.entities[id]) end
    return result, "ambiguous"
end

function Data:LoadEntityDetail(id, entityType)
    if not id or not LoadAddOn then return false end
    if not self.externalLoaded then self:LoadExternalPacks("") end
    local first, second = string.match(id, "^([^:]+):([^:]+)")
    entityType = entityType or (self.detailHashPacks and self.detailHashPacks[first] and first or second)
    local hashes = entityType and self.detailHashPacks and self.detailHashPacks[entityType]
    local names = hashes and hashes[detailHash(id)]
    if not names then return false end
    local loadedAny = false
    self.loadingExternal = true
    for _, name in ipairs(names) do
        if not self.loadedDetailPacks[name] and loadAddon(name) then
            self.loadedDetailPacks[name] = true
            loadedAny = true
        end
    end
    self.loadingExternal = nil
    if loadedAny then self:Rebuild() end
    return loadedAny
end

function Data:EnsureEntityDetail(entity)
    if not entity or entity._detail then return entity end
    if not entity.detailPack then
        self:LoadEntityDetail(entity.id, entity.type)
        return self.entities[entity.id] or entity
    end
    if LoadAddOn and (not IsAddOnLoaded or not IsAddOnLoaded(entity.detailPack)) then
        local loaded, reason = LoadAddOn(entity.detailPack)
        if not loaded and reason ~= "ALREADY_LOADED" then
            NIQ:Print("Could not load detail shard " .. entity.detailPack .. ": " .. tostring(reason))
            return entity
        end
        self:Rebuild()
    end
    return self.entities[entity.id] or entity
end

function Data:GetRelations(entity, loadDetails)
    if type(entity) == "string" then entity = self.entities[entity] end
    if loadDetails ~= false then entity = self:EnsureEntityDetail(entity) end
    if not entity then return {} end
    local keys = { "related", "quests", "turnins", "recipes", "components", "vendors", "trainers", "givers" }
    local seen, output = {}, {}
    for _, key in ipairs(keys) do
        for _, id in ipairs(entity[key] or {}) do
            if self.entities[id] and not seen[id] then
                seen[id] = true
                table.insert(output, self.entities[id])
            end
        end
    end
    return output
end

function Data:DisplayName(id)
    return self.entities[id] and self.entities[id].name or id
end
