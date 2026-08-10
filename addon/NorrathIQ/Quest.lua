local NIQ = NorrathIQ
local Quest = { entries = {}, rows = {} }
NIQ.Quest = Quest
NIQ:RegisterModule("Quest", Quest)

local function backdrop(frame)
    frame:SetBackdrop({
        bgFile = "Interface\\DialogFrame\\UI-DialogBox-Background",
        edgeFile = "Interface\\DialogFrame\\UI-DialogBox-Border", edgeSize = 24,
        tile = true, tileSize = 32,
        insets = { left = 7, right = 7, top = 7, bottom = 7 },
    })
    frame:SetBackdropColor(0.08, 0.07, 0.05, 1)
end

function Quest:Initialize()
    self:CreateFrame()
    if hooksecurefunc and QuestLog_SetSelection then
        hooksecurefunc("QuestLog_SetSelection", function() self:Refresh() end)
    end
end

function Quest:OnEvent(event)
    if event == "QUEST_LOG_UPDATE" or event == "PLAYER_LOGIN" then self:Refresh() end
end

function Quest:CreateFrame()
    local frame = CreateFrame("Frame", "NorrathIQQuestHelperFrame", UIParent)
    frame:SetSize(360, 270)
    frame:SetPoint("RIGHT", -35, 30)
    frame:SetClampedToScreen(true)
    frame:SetMovable(true)
    frame:EnableMouse(true)
    frame:RegisterForDrag("LeftButton")
    frame:SetScript("OnDragStart", function(self) self:StartMoving() end)
    frame:SetScript("OnDragStop", function(self) self:StopMovingOrSizing() end)
    backdrop(frame)
    frame:Hide()
    local header = frame:CreateTexture(nil, "ARTWORK")
    header:SetTexture("Interface\\DialogFrame\\UI-DialogBox-Header")
    header:SetSize(300, 64)
    header:SetPoint("TOP", 0, 13)
    local title = frame:CreateFontString(nil, "OVERLAY", "GameFontNormal")
    title:SetPoint("TOP", header, "TOP", 0, -15)
    title:SetText("NorrathIQ Quest Objectives")
    local close = CreateFrame("Button", nil, frame, "UIPanelCloseButton")
    close:SetPoint("TOPRIGHT", 2, 2)
    close:SetScript("OnClick", function()
        NIQ.db.showQuestHelper = false
        frame:Hide()
    end)
    for index = 1, 8 do
        local row = CreateFrame("Button", nil, frame)
        row:SetSize(330, 25)
        row:SetPoint("TOPLEFT", 14, -34 - ((index - 1) * 27))
        row:SetHighlightTexture("Interface\\QuestFrame\\UI-QuestTitleHighlight", "ADD")
        local text = row:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
        text:SetPoint("LEFT")
        text:SetPoint("RIGHT", -70, 0)
        text:SetJustifyH("LEFT")
        row.text = text
        local map = CreateFrame("Button", nil, row, "UIPanelButtonTemplate")
        map:SetSize(62, 21)
        map:SetPoint("RIGHT")
        map:SetText("Map")
        map:SetScript("OnClick", function()
            if row.entity then NIQ.Map:ShowEntity(row.entity, "source") end
        end)
        row.map = map
        row:Hide()
        self.rows[index] = row
    end
    self.frame = frame
end

function Quest:ResolveObjective(description, questId)
    local normalized = NIQ:Normalize(description)
    local candidates = {}
    local realmQuest = questId and NIQ.Data:GetQuestByRealmId(questId)
    if realmQuest then
        for _, entity in ipairs(NIQ.Data:GetRelations(realmQuest)) do
            if string.find(normalized, NIQ:Normalize(entity.name), 1, true) then
                table.insert(candidates, entity)
            end
        end
        if #candidates == 1 then return candidates[1], "realm quest id" end
        if #candidates > 1 then return candidates, "ambiguous" end
    end
    for _, entity in pairs(NIQ.Data.entities) do
        if entity.type == "item" or entity.type == "npc" then
            local name = NIQ:Normalize(entity.name)
            if name ~= "" and string.find(normalized, name, 1, true) then table.insert(candidates, entity) end
            for _, alias in ipairs(entity.aliases or {}) do
                if string.find(normalized, NIQ:Normalize(alias), 1, true) then table.insert(candidates, entity) break end
            end
        end
    end
    if #candidates == 1 then return candidates[1], "exact phrase" end
    if #candidates > 1 then return candidates, "ambiguous" end
    return nil, "missing"
end

function Quest:Refresh()
    self.entries = {}
    if not GetNumQuestLogEntries or not GetQuestLogTitle then return end
    local count = GetNumQuestLogEntries()
    for questIndex = 1, count do
        local title, level, tag, isHeader, isCollapsed, isComplete, frequency, questId = GetQuestLogTitle(questIndex)
        if title and not isHeader then
            local objectives = GetNumQuestLeaderBoards and GetNumQuestLeaderBoards(questIndex) or 0
            for objectiveIndex = 1, objectives do
                local description, objectiveType, complete = GetQuestLogLeaderBoard(objectiveIndex, questIndex)
                if description then
                    local entity, status = self:ResolveObjective(description, questId)
                    if status == "exact phrase" or status == "realm quest id" then
                        table.insert(self.entries, { quest = title, description = description, entity = entity, complete = complete })
                    end
                end
            end
        end
    end
    for index, row in ipairs(self.rows) do
        local entry = self.entries[index]
        if entry then
            row.entity = entry.entity
            row.text:SetText((entry.complete and "|cff66cc66" or "|cffffffff") .. entry.description .. "|r\n|cff65d6c7→ " .. entry.entity.name .. "|r")
            NIQ:SetEnabled(row.map, entry.entity.map or entry.entity.zone or entry.entity.drops)
            row:Show()
        else
            row.entity = nil
            row:Hide()
        end
    end
    if NIQ.db.showQuestHelper and #self.entries > 0 then self.frame:Show() end
end

function Quest:Toggle()
    if self.frame:IsShown() then
        NIQ.db.showQuestHelper = false
        self.frame:Hide()
    else
        NIQ.db.showQuestHelper = true
        self:Refresh()
        self.frame:Show()
    end
end
