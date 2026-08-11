local ADDON_NAME = ...

NorrathIQ = NorrathIQ or {}
local NIQ = NorrathIQ

NIQ.name = ADDON_NAME or "NorrathIQ"
NIQ.version = "1.3.5"
NIQ.schemaVersion = 1
NIQ.modules = NIQ.modules or {}
NIQ.moduleOrder = NIQ.moduleOrder or {}
NIQ.dataPacks = NIQ.dataPacks or {}
NIQ.bagAdapters = NIQ.bagAdapters or {}
NIQ.mapProviders = NIQ.mapProviders or {}

local function copyDefaults(target, defaults)
    for key, value in pairs(defaults) do
        if target[key] == nil then
            if type(value) == "table" then
                target[key] = {}
                copyDefaults(target[key], value)
            else
                target[key] = value
            end
        elseif type(value) == "table" and type(target[key]) == "table" then
            copyDefaults(target[key], value)
        end
    end
end

local accountDefaults = {
    schemaVersion = 1,
    showTooltips = true,
    showBagBadges = true,
    showQuestHelper = true,
    showConfidence = true,
    atlasScale = 1,
    searchFilter = "all",
    minimap = { hidden = false, angle = 220 },
}

local characterDefaults = {
    schemaVersion = 1,
    goals = {},
    skills = {},
    confirmedMappings = {},
    dismissedAdvice = {},
}

function NIQ:RegisterModule(name, module)
    if not self.modules[name] then table.insert(self.moduleOrder, name) end
    self.modules[name] = module
    module.name = name
end

function NIQ:Print(message)
    local prefix = "|cff65d6c7NorrathIQ:|r "
    if DEFAULT_CHAT_FRAME and DEFAULT_CHAT_FRAME.AddMessage then
        DEFAULT_CHAT_FRAME:AddMessage(prefix .. tostring(message))
    end
end

function NIQ:Normalize(value)
    if not value then return "" end
    value = string.lower(tostring(value))
    value = string.gsub(value, "&amp;", "&")
    value = string.gsub(value, "[^%w%s']", " ")
    value = string.gsub(value, "%s+", " ")
    value = string.gsub(value, "^%s+", "")
    value = string.gsub(value, "%s+$", "")
    return value
end

function NIQ:ItemNameFromLink(link)
    if not link then return nil end
    return string.match(link, "%[(.-)%]") or link
end

function NIQ:SetShown(region, shown)
    if shown then region:Show() else region:Hide() end
end

function NIQ:SetEnabled(button, enabled)
    if enabled then button:Enable() else button:Disable() end
end

function NIQ:RegisterDataPack(pack)
    if type(pack) ~= "table" or not pack.meta or not pack.entities then
        self:Print("Rejected an invalid data pack.")
        return false
    end
    if pack.meta.schemaVersion ~= self.schemaVersion then
        self:Print("Data pack schema " .. tostring(pack.meta.schemaVersion) .. " is not supported.")
        return false
    end
    self.dataPacks[pack.meta.id] = pack
    if self.Data and self.Data.Rebuild and not self.Data.loadingExternal and not self.Data.deferRebuild
        and next(pack.entities) then self.Data:Rebuild() end
    return true
end

function NIQ:RegisterBagAdapter(id, adapter)
    assert(type(id) == "string", "bag adapter id must be a string")
    assert(type(adapter) == "table", "bag adapter must be a table")
    self.bagAdapters[id] = adapter
end

function NIQ:RegisterMapProvider(id, provider)
    assert(type(id) == "string", "map provider id must be a string")
    assert(type(provider) == "table", "map provider must be a table")
    self.mapProviders[id] = provider
end

function NIQ:MigrateSavedVariables()
    NorrathIQDB = NorrathIQDB or {}
    NorrathIQCharDB = NorrathIQCharDB or {}
    copyDefaults(NorrathIQDB, accountDefaults)
    if not NorrathIQDB.minimap.visibleMigration then
        NorrathIQDB.minimap.hidden = false
        NorrathIQDB.minimap.visibleMigration = true
    end
    copyDefaults(NorrathIQCharDB, characterDefaults)
    NorrathIQDB.schemaVersion = self.schemaVersion
    NorrathIQCharDB.schemaVersion = self.schemaVersion
    self.db = NorrathIQDB
    self.charDB = NorrathIQCharDB
end

function NIQ:Initialize()
    self:MigrateSavedVariables()
    for _, name in ipairs(self.moduleOrder) do
        local module = self.modules[name]
        if module.Initialize then
            local ok, err = pcall(module.Initialize, module)
            if not ok then self:Print(module.name .. " failed to initialize: " .. tostring(err)) end
        end
    end
    self.initialized = true
end

function NIQ:GetSourceVersions()
    local eqwow, p99 = "none", "disabled"
    for _, pack in pairs(self.dataPacks or {}) do
        local meta = pack.meta or {}
        if meta.eqwowSnapshot and meta.eqwowSnapshot ~= "" then eqwow = meta.eqwowSnapshot end
        if meta.p99ReferenceVersion and meta.p99ReferenceVersion ~= "" then p99 = meta.p99ReferenceVersion end
    end
    return eqwow, p99
end

function NIQ:DispatchEvent(event, ...)
    for _, name in ipairs(self.moduleOrder) do
        local module = self.modules[name]
        if module.OnEvent then
            local ok, err = pcall(module.OnEvent, module, event, ...)
            if not ok then self:Print(module.name .. " event error: " .. tostring(err)) end
        end
    end
end

local eventFrame = CreateFrame("Frame", "NorrathIQEventFrame")
NIQ.eventFrame = eventFrame
eventFrame:RegisterEvent("ADDON_LOADED")
eventFrame:RegisterEvent("PLAYER_LOGIN")
eventFrame:RegisterEvent("BAG_UPDATE")
eventFrame:RegisterEvent("QUEST_LOG_UPDATE")
eventFrame:SetScript("OnEvent", function(self, event, ...)
    if event == "ADDON_LOADED" then
        local loaded = ...
        if loaded == NIQ.name then NIQ:Initialize() end
    end
    if NIQ.initialized then NIQ:DispatchEvent(event, ...) end
end)

SLASH_NORRATHIQ1 = "/niq"
SLASH_NORRATHIQ2 = "/norrathiq"
SlashCmdList.NORRATHIQ = function(message)
    message = message or ""
    local command, rest = string.match(message, "^(%S*)%s*(.-)$")
    command = string.lower(command or "")
    if command == "map" and NIQ.Map then
        NIQ.Map:ShowZone(rest)
    elseif command == "bags" and NIQ.Inventory then
        NIQ.Inventory:Refresh()
        NIQ:Print("Bag badges refreshed.")
    elseif command == "quest" and NIQ.Quest then
        NIQ.Quest:Toggle()
    elseif command == "version" then
        local eqwow, p99 = NIQ:GetSourceVersions()
        NIQ:Print("Version " .. NIQ.version .. "; EQWOW snapshot: " .. eqwow .. "; P99 reference: " .. p99)
    elseif command == "help" then
        NIQ:Print("/niq [search], /niq map <zone>, /niq bags, /niq quest, /niq version")
    elseif NIQ.UI then
        NIQ.UI:Show(command ~= "" and message or nil)
    end
end
