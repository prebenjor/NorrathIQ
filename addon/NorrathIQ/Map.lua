local NIQ = NorrathIQ
local Map = { markers = {}, pathDots = {} }
NIQ.Map = Map
NIQ:RegisterModule("Map", Map)

local function makeBackdrop(frame)
    frame:SetBackdrop({
        bgFile = "Interface\\DialogFrame\\UI-DialogBox-Background",
        edgeFile = "Interface\\DialogFrame\\UI-DialogBox-Border",
        tile = true, tileSize = 32, edgeSize = 24,
        insets = { left = 7, right = 7, top = 7, bottom = 7 },
    })
    frame:SetBackdropColor(0.08, 0.07, 0.05, 1)
end

function Map:Initialize()
    self:CreateAtlas()
    NIQ:RegisterMapProvider("native-3.3.5", {
        CanShow = function(provider, target)
            return target and target.nativeMap and target.nativeMap.mapId and target.nativeMap.x and target.nativeMap.y
        end,
        Show = function(provider, target)
            if SetMapByID then SetMapByID(target.nativeMap.mapId) end
            if WorldMapFrame_Show then WorldMapFrame_Show() elseif ToggleWorldMap then ToggleWorldMap() end
            if not WorldMapButton then return false end
            provider.pin = provider.pin or CreateFrame("Button", "NorrathIQNativeMapPin", WorldMapButton)
            provider.pin:SetSize(18, 18)
            provider.pin:SetNormalTexture("Interface\\Minimap\\POIIcons")
            provider.pin:SetPoint("CENTER", WorldMapButton, "TOPLEFT",
                WorldMapButton:GetWidth() * target.nativeMap.x,
                -WorldMapButton:GetHeight() * target.nativeMap.y)
            provider.pin:Show()
            return true
        end,
    })
end

function Map:CreateAtlas()
    if self.frame then return end
    local frame = CreateFrame("Frame", "NorrathIQAtlasFrame", UIParent)
    frame:SetSize(660, 520)
    frame:SetPoint("CENTER")
    frame:SetFrameStrata("DIALOG")
    frame:SetToplevel(true)
    frame:SetClampedToScreen(true)
    frame:SetMovable(true)
    frame:EnableMouse(true)
    frame:RegisterForDrag("LeftButton")
    frame:SetScript("OnDragStart", function(self) self:StartMoving() end)
    frame:SetScript("OnDragStop", function(self) self:StopMovingOrSizing() end)
    makeBackdrop(frame)
    frame:Hide()

    local header = frame:CreateTexture(nil, "ARTWORK")
    header:SetTexture("Interface\\DialogFrame\\UI-DialogBox-Header")
    header:SetSize(360, 64)
    header:SetPoint("TOP", 0, 13)
    local title = frame:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
    title:SetPoint("TOP", header, "TOP", 0, -14)
    title:SetText("NorrathIQ Atlas")
    frame.title = title

    local close = CreateFrame("Button", nil, frame, "UIPanelCloseButton")
    close:SetPoint("TOPRIGHT", -5, -5)

    local canvas = CreateFrame("Frame", nil, frame)
    canvas:SetPoint("TOPLEFT", 28, -52)
    canvas:SetPoint("BOTTOMRIGHT", -28, 64)
    canvas:SetBackdrop({
        bgFile = "Interface\\QuestFrame\\QuestBG",
        edgeFile = "Interface\\Tooltips\\UI-Tooltip-Border",
        edgeSize = 14,
        insets = { left = 4, right = 4, top = 4, bottom = 4 },
    })
    canvas:SetBackdropColor(0.72, 0.62, 0.43, 1)
    frame.canvas = canvas

    for index = 1, 9 do
        local vertical = canvas:CreateTexture(nil, "BACKGROUND")
        vertical:SetTexture(0.32, 0.20, 0.08, 0.30)
        vertical:SetWidth(1)
        vertical:SetPoint("TOP", canvas, "TOPLEFT", canvas:GetWidth() * index / 10, 0)
        vertical:SetPoint("BOTTOM", canvas, "BOTTOMLEFT", canvas:GetWidth() * index / 10, 0)
        local horizontal = canvas:CreateTexture(nil, "BACKGROUND")
        horizontal:SetTexture(0.32, 0.20, 0.08, 0.30)
        horizontal:SetHeight(1)
        horizontal:SetPoint("LEFT", canvas, "TOPLEFT", 0, -canvas:GetHeight() * index / 10)
        horizontal:SetPoint("RIGHT", canvas, "TOPRIGHT", 0, -canvas:GetHeight() * index / 10)
    end

    local note = frame:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    note:SetPoint("BOTTOMLEFT", 28, 26)
    note:SetPoint("BOTTOMRIGHT", -28, 26)
    note:SetJustifyH("LEFT")
    note:SetTextColor(0.85, 0.78, 0.58)
    frame.note = note
    self.frame = frame
end

function Map:ClearMarkers()
    for _, marker in ipairs(self.markers) do marker:Hide() end
    for _, dot in ipairs(self.pathDots) do dot:Hide() end
end

function Map:AddMarker(x, y, label, confidence)
    if not x or not y then return end
    local marker = table.remove(self.markers) or CreateFrame("Button", nil, self.frame.canvas)
    marker:SetSize(16, 16)
    marker:SetNormalTexture("Interface\\TargetingFrame\\UI-RaidTargetingIcon_2")
    marker:ClearAllPoints()
    marker:SetPoint("CENTER", self.frame.canvas, "TOPLEFT", self.frame.canvas:GetWidth() * x, -self.frame.canvas:GetHeight() * y)
    marker.label, marker.confidence = label, confidence
    marker:SetScript("OnEnter", function(self)
        GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
        GameTooltip:SetText(self.label or "Map marker")
        GameTooltip:AddLine("Confidence: " .. (self.confidence or "unknown"), 0.8, 0.8, 0.8)
        GameTooltip:Show()
    end)
    marker:SetScript("OnLeave", function() GameTooltip:Hide() end)
    marker:Show()
    table.insert(self.markers, marker)
end

function Map:AddPath(path)
    for _, point in ipairs(path or {}) do
        local dot = table.remove(self.pathDots) or self.frame.canvas:CreateTexture(nil, "ARTWORK")
        dot:SetTexture(0.35, 0.9, 0.75, 0.8)
        dot:SetSize(5, 5)
        dot:ClearAllPoints()
        dot:SetPoint("CENTER", self.frame.canvas, "TOPLEFT", self.frame.canvas:GetWidth() * point[1], -self.frame.canvas:GetHeight() * point[2])
        dot:Show()
        table.insert(self.pathDots, dot)
    end
end

function Map:TryProviders(target)
    for _, provider in pairs(NIQ.mapProviders) do
        local ok, canShow = pcall(provider.CanShow, provider, target)
        if ok and canShow then
            local shown, result = pcall(provider.Show, provider, target)
            if shown and result ~= false then return true end
        end
    end
    return false
end

function Map:ShowZone(zone, target)
    self:CreateAtlas()
    zone = zone and string.gsub(zone, "^%s*(.-)%s*$", "%1") or ""
    if zone == "" then zone = target and target.zone or "Unknown Zone" end
    self:ClearMarkers()
    self.frame.title:SetText(zone)
    local zoneData = NIQ.Data.zones[zone]
    local note = zoneData and zoneData.note or "Zone known, but no trustworthy exact coordinates are available."
    local shown = 0
    local selectedMarker = target and target.marker
    for markerId, spawn in pairs(NIQ.Data.spawns or {}) do
        if shown >= 80 then break end
        if markerId ~= selectedMarker and (spawn.zone == zone or (zoneData and spawn.zoneId == zoneData.zoneId)) then
            self:AddMarker(spawn.x, spawn.y, spawn.label, spawn.confidence)
            shown = shown + 1
        end
    end
    if target and target.map and target.map.zone == zone then
        self:AddMarker(target.map.x, target.map.y, target.name, target.map.confidence)
    end
    if target and target.marker and NIQ.Data.spawns[target.marker] then
        local spawn = NIQ.Data.spawns[target.marker]
        self:AddMarker(spawn.x, spawn.y, spawn.label, spawn.confidence)
        self:AddPath(spawn.path)
        shown = shown + 1
    end
    self.frame.note:SetText(note .. " Showing " .. tostring(shown) .. " exact pin(s) currently downloaded.")
    self.frame:Show()
end

function Map:ShowEntity(entity, purpose)
    if type(entity) == "string" then entity = NIQ.Data:GetEntity(entity) end
    if not entity then NIQ:Print("No map target is available.") return false end

    if purpose == "turnin" and entity.turnins and entity.turnins[1] then
        entity = NIQ.Data:GetEntity(entity.turnins[1]) or entity
    elseif purpose == "source" and entity.drops and entity.drops[1] then
        local drop = entity.drops[1]
        local target = { name = drop.npc, zone = drop.zone, marker = drop.marker }
        if drop.marker and NIQ.Data.spawns[drop.marker] then
            local spawn = NIQ.Data.spawns[drop.marker]
            target.map = { zone = spawn.zone, x = spawn.x, y = spawn.y, confidence = spawn.confidence }
        end
        entity = target
    end

    if self:TryProviders(entity) then return true end
    self:ShowZone((entity.map and entity.map.zone) or entity.zone, entity)
    return true
end
