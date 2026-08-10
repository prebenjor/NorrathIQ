local NIQ = NorrathIQ
local UI = {
    filter = "all",
    rows = {},
    filters = { "all", "item", "quest", "npc", "recipe", "eqspell", "wowspell", "zone", "object", "key", "inventory" },
}
NIQ.UI = UI
NIQ:RegisterModule("UI", UI)

local TYPE_ICONS = {
    item = "Interface\\Icons\\INV_Misc_Bag_10",
    quest = "Interface\\Icons\\INV_Misc_Note_01",
    npc = "Interface\\Icons\\Ability_Hunter_BeastCall",
    recipe = "Interface\\Icons\\INV_Scroll_03",
    spell = "Interface\\Icons\\INV_Misc_Book_09",
    zone = "Interface\\Icons\\INV_Misc_Map_01",
    object = "Interface\\Icons\\INV_Crate_01",
    key = "Interface\\Icons\\INV_Misc_Key_03",
    inventory = "Interface\\Icons\\INV_Misc_Bag_08",
}

local FILTER_LABELS = {
    all = "All records", item = "Items", quest = "Quests", npc = "NPCs",
    recipe = "Recipes", eqspell = "EverQuest spells", wowspell = "WoW spells",
    zone = "Zones", object = "Objects / containers", key = "Keys", inventory = "Inventory advice",
}

local function pretty(value)
    if FILTER_LABELS[value] then return FILTER_LABELS[value] end
    return string.upper(string.sub(value, 1, 1)) .. string.sub(value, 2)
end

local function iconFor(entity)
    return entity and (entity.icon or TYPE_ICONS[entity.type]) or TYPE_ICONS.item
end

local function makeWindowBackdrop(frame)
    frame:SetBackdrop({
        bgFile = "Interface\\DialogFrame\\UI-DialogBox-Background",
        edgeFile = "Interface\\DialogFrame\\UI-DialogBox-Border",
        tile = true, tileSize = 32, edgeSize = 32,
        insets = { left = 9, right = 9, top = 9, bottom = 9 },
    })
    frame:SetBackdropColor(0.08, 0.07, 0.05, 1)
end

local function makeInset(frame, parchment)
    frame:SetBackdrop({
        bgFile = parchment and "Interface\\QuestFrame\\QuestBG" or "Interface\\Tooltips\\UI-Tooltip-Background",
        edgeFile = "Interface\\Tooltips\\UI-Tooltip-Border",
        tile = not parchment, tileSize = 16, edgeSize = 14,
        insets = { left = 4, right = 4, top = 4, bottom = 4 },
    })
    if parchment then
        frame:SetBackdropColor(0.72, 0.62, 0.43, 1)
    else
        frame:SetBackdropColor(0.025, 0.025, 0.025, 0.94)
    end
end

local function append(lines, label, value)
    if value == nil or value == "" then return end
    table.insert(lines, "|cffffd100" .. label .. ":|r |cff2b1b0e" .. tostring(value) .. "|r")
end

function UI:Initialize()
    self.searchTimer = CreateFrame("Frame")
    self.searchTimer:Hide()
    self.searchTimer:SetScript("OnUpdate", function(_, elapsed)
        UI.searchElapsed = (UI.searchElapsed or 0) + elapsed
        if UI.searchElapsed >= 0.30 then
            UI.searchTimer:Hide()
            UI:RunSearch(UI.pendingSearch or "")
        end
    end)
    self:CreateFrame()
end

function UI:QueueSearch(text)
    self.pendingSearch = text or ""
    self.searchElapsed = 0
    self.searchTimer:Show()
end

function UI:CreateFrame()
    local frame = CreateFrame("Frame", "NorrathIQBrowserFrame", UIParent)
    frame:SetSize(860, 600)
    frame:SetPoint("CENTER")
    frame:SetFrameStrata("DIALOG")
    frame:SetToplevel(true)
    frame:SetClampedToScreen(true)
    frame:SetMovable(true)
    frame:EnableMouse(true)
    frame:RegisterForDrag("LeftButton")
    frame:SetScript("OnDragStart", function(self) self:StartMoving() end)
    frame:SetScript("OnDragStop", function(self) self:StopMovingOrSizing() end)
    makeWindowBackdrop(frame)
    frame:Hide()
    table.insert(UISpecialFrames, "NorrathIQBrowserFrame")

    local header = frame:CreateTexture(nil, "ARTWORK")
    header:SetTexture("Interface\\DialogFrame\\UI-DialogBox-Header")
    header:SetSize(420, 64)
    header:SetPoint("TOP", 0, 13)

    local title = frame:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
    title:SetPoint("TOP", header, "TOP", 0, -14)
    title:SetText("NorrathIQ Knowledge Journal")

    local portrait = frame:CreateTexture(nil, "ARTWORK")
    portrait:SetTexture("Interface\\Icons\\INV_Misc_Book_09")
    portrait:SetSize(54, 54)
    portrait:SetPoint("TOPLEFT", 13, -12)
    local portraitBorder = frame:CreateTexture(nil, "OVERLAY")
    portraitBorder:SetTexture("Interface\\Minimap\\MiniMap-TrackingBorder")
    portraitBorder:SetSize(82, 82)
    portraitBorder:SetPoint("CENTER", portrait, "CENTER", 11, -12)

    local version = frame:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
    version:SetPoint("TOPRIGHT", -42, -18)
    version:SetText("v" .. NIQ.version)
    local close = CreateFrame("Button", nil, frame, "UIPanelCloseButton")
    close:SetPoint("TOPRIGHT", -5, -5)

    local searchLabel = frame:CreateFontString(nil, "OVERLAY", "GameFontNormal")
    searchLabel:SetPoint("TOPLEFT", 82, -51)
    searchLabel:SetText("Search the journal")
    local search = CreateFrame("EditBox", "NorrathIQSearchBox", frame, "InputBoxTemplate")
    search:SetSize(330, 26)
    search:SetPoint("LEFT", searchLabel, "RIGHT", 10, 0)
    search:SetAutoFocus(false)
    search:SetMaxLetters(80)
    search:SetScript("OnTextChanged", function(self) UI:QueueSearch(self:GetText()) end)
    search:SetScript("OnEscapePressed", function(self) self:ClearFocus() end)
    search:SetScript("OnEnterPressed", function(self) self:ClearFocus() end)
    frame.search = search

    local categoryLabel = frame:CreateFontString(nil, "OVERLAY", "GameFontNormal")
    categoryLabel:SetPoint("LEFT", search, "RIGHT", 24, 0)
    categoryLabel:SetText("Category")
    local dropdown = CreateFrame("Frame", "NorrathIQCategoryDropDown", frame, "UIDropDownMenuTemplate")
    dropdown:SetPoint("LEFT", categoryLabel, "RIGHT", -5, -2)
    UIDropDownMenu_SetWidth(dropdown, 125)
    frame.dropdown = dropdown
    UIDropDownMenu_Initialize(dropdown, function()
        for _, filter in ipairs(UI.filters) do
            local info = UIDropDownMenu_CreateInfo()
            info.text = pretty(filter)
            info.value = filter
            info.arg1 = filter
            info.checked = UI.filter == filter
            info.func = function(button, value) UI:SetFilter(value) end
            UIDropDownMenu_AddButton(info)
        end
    end)
    UIDropDownMenu_SetSelectedValue(dropdown, self.filter)

    local listPane = CreateFrame("Frame", nil, frame)
    listPane:SetPoint("TOPLEFT", 18, -88)
    listPane:SetPoint("BOTTOMLEFT", 18, 76)
    listPane:SetWidth(356)
    makeInset(listPane, false)
    frame.listPane = listPane

    local listTitle = listPane:CreateFontString(nil, "OVERLAY", "GameFontNormal")
    listTitle:SetPoint("TOPLEFT", 12, -10)
    listTitle:SetText("Search Results")
    local rule = listPane:CreateTexture(nil, "ARTWORK")
    rule:SetTexture("Interface\\Buttons\\WHITE8X8")
    rule:SetVertexColor(0.55, 0.42, 0.18, 0.65)
    rule:SetHeight(1)
    rule:SetPoint("TOPLEFT", 10, -29)
    rule:SetPoint("TOPRIGHT", -10, -29)

    for index = 1, 13 do
        local row = CreateFrame("Button", nil, listPane)
        row:SetSize(330, 31)
        row:SetPoint("TOPLEFT", 12, -34 - ((index - 1) * 31))
        local shade = row:CreateTexture(nil, "BACKGROUND")
        shade:SetAllPoints()
        shade:SetTexture("Interface\\Buttons\\WHITE8X8")
        if index % 2 == 0 then shade:SetVertexColor(0.12, 0.10, 0.07, 0.42) else shade:SetVertexColor(0, 0, 0, 0) end
        local selected = row:CreateTexture(nil, "BACKGROUND")
        selected:SetAllPoints()
        selected:SetTexture("Interface\\QuestFrame\\UI-QuestTitleHighlight")
        selected:SetBlendMode("ADD")
        selected:Hide()
        row.selected = selected
        row:SetHighlightTexture("Interface\\QuestFrame\\UI-QuestTitleHighlight", "ADD")
        local icon = row:CreateTexture(nil, "ARTWORK")
        icon:SetSize(24, 24)
        icon:SetPoint("LEFT", 3, 0)
        row.icon = icon
        local text = row:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
        text:SetPoint("TOPLEFT", icon, "TOPRIGHT", 7, -1)
        text:SetPoint("RIGHT", -5, 0)
        text:SetJustifyH("LEFT")
        row.text = text
        local kind = row:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
        kind:SetPoint("BOTTOMLEFT", icon, "BOTTOMRIGHT", 7, 1)
        row.kind = kind
        row:SetScript("OnClick", function()
            if row.entity then UI:ShowEntity(row.entity) end
        end)
        row:Hide()
        self.rows[index] = row
    end

    local empty = listPane:CreateFontString(nil, "OVERLAY", "GameFontDisable")
    empty:SetPoint("CENTER")
    empty:SetText("Type an item, NPC, quest, recipe, or zone above.")
    empty:SetWidth(290)
    frame.empty = empty

    local detailPane = CreateFrame("Frame", nil, frame)
    detailPane:SetPoint("TOPLEFT", listPane, "TOPRIGHT", 12, 0)
    detailPane:SetPoint("BOTTOMRIGHT", -18, 76)
    makeInset(detailPane, true)
    frame.detailPane = detailPane

    local detailIcon = detailPane:CreateTexture(nil, "ARTWORK")
    detailIcon:SetSize(40, 40)
    detailIcon:SetPoint("TOPLEFT", 16, -14)
    detailIcon:SetTexture(TYPE_ICONS.item)
    frame.detailIcon = detailIcon
    local iconBorder = detailPane:CreateTexture(nil, "OVERLAY")
    iconBorder:SetTexture("Interface\\Buttons\\UI-Quickslot2")
    iconBorder:SetSize(64, 64)
    iconBorder:SetPoint("CENTER", detailIcon, "CENTER")

    local detailName = detailPane:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
    detailName:SetPoint("TOPLEFT", detailIcon, "TOPRIGHT", 10, -1)
    detailName:SetPoint("RIGHT", -18, 0)
    detailName:SetJustifyH("LEFT")
    detailName:SetText("Select a journal entry")
    frame.detailName = detailName
    local detailType = detailPane:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    detailType:SetPoint("TOPLEFT", detailName, "BOTTOMLEFT", 0, -5)
    detailType:SetTextColor(0.35, 0.20, 0.08)
    detailType:SetText("Knowledge details appear here")
    frame.detailType = detailType

    local detailRule = detailPane:CreateTexture(nil, "ARTWORK")
    detailRule:SetTexture("Interface\\Buttons\\WHITE8X8")
    detailRule:SetVertexColor(0.45, 0.28, 0.08, 0.7)
    detailRule:SetHeight(1)
    detailRule:SetPoint("TOPLEFT", 14, -65)
    detailRule:SetPoint("TOPRIGHT", -14, -65)

    local scroll = CreateFrame("ScrollFrame", "NorrathIQDetailScrollFrame", detailPane, "UIPanelScrollFrameTemplate")
    scroll:SetPoint("TOPLEFT", 16, -74)
    scroll:SetPoint("BOTTOMRIGHT", -32, 48)
    local scrollChild = CreateFrame("Frame", nil, scroll)
    scrollChild:SetWidth(410)
    scrollChild:SetHeight(1)
    scroll:SetScrollChild(scrollChild)
    frame.detailScrollChild = scrollChild
    local detail = scrollChild:CreateFontString(nil, "ARTWORK", "GameFontHighlight")
    detail:SetPoint("TOPLEFT", 0, 0)
    detail:SetWidth(400)
    detail:SetJustifyH("LEFT")
    detail:SetJustifyV("TOP")
    detail:SetSpacing(3)
    detail:SetTextColor(0.16, 0.09, 0.035)
    frame.detail = detail
    frame.detailLinks = {}

    local actions = {}
    local labels = { "Source Map", "Turn-in", "Related", "Recipe", "Database URL" }
    for index, label in ipairs(labels) do
        local button = CreateFrame("Button", nil, detailPane, "UIPanelButtonTemplate")
        button:SetSize(80, 24)
        button:SetPoint("BOTTOMLEFT", 14 + (index - 1) * 84, 14)
        button:SetText(label)
        actions[index] = button
    end
    actions[1]:SetScript("OnClick", function() if UI.current then NIQ.Map:ShowEntity(UI.current, "source") end end)
    actions[2]:SetScript("OnClick", function() if UI.current then NIQ.Map:ShowEntity(UI.current, "turnin") end end)
    actions[3]:SetScript("OnClick", function()
        if not UI.current then return end
        local relations = NIQ.Data:GetRelations(UI.current)
        if relations[1] then UI:ShowEntity(relations[1]) else NIQ:Print("No related record is available.") end
    end)
    actions[4]:SetScript("OnClick", function()
        if UI.current and UI.current.recipes and UI.current.recipes[1] then
            UI:ShowEntity(NIQ.Data:GetEntity(UI.current.recipes[1]))
        end
    end)
    actions[5]:SetScript("OnClick", function() UI:CopySourceURL() end)
    frame.actions = actions

    local optionDefinitions = {
        { "Tooltips", "showTooltips", function() end },
        { "Bag badges", "showBagBadges", function() NIQ.Inventory:Refresh() end },
        { "Quest helper", "showQuestHelper", function(value)
            if not value then NIQ.Quest.frame:Hide() else NIQ.Quest:Refresh() end
        end },
        { "Confidence", "showConfidence", function() end },
    }
    frame.options = {}
    for index, definition in ipairs(optionDefinitions) do
        local check = CreateFrame("CheckButton", nil, frame, "UICheckButtonTemplate")
        check:SetSize(24, 24)
        check:SetPoint("BOTTOMLEFT", 20 + (index - 1) * 115, 38)
        check:SetChecked(NIQ.db[definition[2]])
        local label = check:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
        label:SetPoint("LEFT", check, "RIGHT", 0, 1)
        label:SetText(definition[1])
        check:SetScript("OnClick", function(self)
            local value = self:GetChecked() and true or false
            NIQ.db[definition[2]] = value
            definition[3](value)
        end)
        frame.options[index] = check
    end

    local footer = frame:CreateFontString(nil, "OVERLAY", "GameFontDisableSmall")
    footer:SetPoint("BOTTOMLEFT", 22, 18)
    footer:SetText("Offline journal - EQWOW primary + captured realm overlay - never auto-sells or destroys")
    self.frame = frame
end

function UI:SetFilter(filter)
    self.filter = filter or "all"
    NIQ.db.searchFilter = self.filter
    UIDropDownMenu_SetSelectedValue(self.frame.dropdown, self.filter)
    UIDropDownMenu_SetText(self.frame.dropdown, pretty(self.filter))
    self:RunSearch(self.frame.search:GetText())
end

function UI:RunSearch(text)
    local results = NIQ.Search:Query(text or "", self.filter, #self.rows)
    for index, row in ipairs(self.rows) do
        local result = results[index]
        if result then
            row.entity = result.entity
            row.icon:SetTexture(iconFor(result.entity))
            local flag = NIQ.Recommendation:PrimaryFlag(result.entity)
            row.text:SetText((flag and "|cffffd100[" .. flag .. "]|r " or "") .. result.entity.name)
            local kind = pretty(result.entity.type)
            if result.entity.type == "spell" then
                kind = (result.entity.game == "wow" and "World of Warcraft" or "EverQuest")
                    .. " spell" .. (result.entity.rank and " - " .. result.entity.rank or "")
            end
            row.kind:SetText(kind)
            NIQ:SetShown(row.selected, self.current and self.current.id == result.entity.id)
            row:Show()
        else
            row.entity = nil
            row:Hide()
        end
    end
    NIQ:SetShown(self.frame.empty, #results == 0)
end

function UI:CopySourceURL()
    local url = self.current and self.current.source and self.current.source.url
    if not url or not string.find(url, "^https?://") then
        NIQ:Print("This record is a local client observation and has no external database page.")
        return
    end
    if ChatFrame_OpenChat then
        ChatFrame_OpenChat(url)
        NIQ:Print("The source URL is in the chat edit box. Press Ctrl+A, Ctrl+C to copy it; Escape cancels without sending.")
    else
        NIQ:Print(url)
    end
end

function UI:ClearDetailLinks()
    for _, button in ipairs(self.frame.detailLinks) do
        button:Hide()
        button:SetScript("OnClick", nil)
    end
end

function UI:AddDetailLink(label, callback, y)
    local index = 1
    while self.frame.detailLinks[index] and self.frame.detailLinks[index]:IsShown() do index = index + 1 end
    local button = self.frame.detailLinks[index]
    if not button then
        button = CreateFrame("Button", nil, self.frame.detailScrollChild, "UIPanelButtonTemplate")
        button:SetSize(382, 22)
        self.frame.detailLinks[index] = button
    end
    button:ClearAllPoints()
    button:SetPoint("TOPLEFT", 2, y)
    button:SetText(label)
    button:SetScript("OnClick", callback)
    button:Enable()
    button:Show()
    return y - 25
end

function UI:BuildDetailLinks(entity, relations)
    self:ClearDetailLinks()
    local y = -self.frame.detail:GetStringHeight() - 14
    local count = 0
    for _, related in ipairs(relations or {}) do
        if count >= 8 then break end
        local target = related
        y = self:AddDetailLink("Open: " .. related.name .. " [" .. related.type .. "]", function() UI:ShowEntity(target) end, y)
        count = count + 1
    end
    for _, drop in ipairs(entity.drops or {}) do
        if count >= 12 then break end
        local target, status = NIQ.Data:ResolveExact(drop.npc)
        if status == "exact" and target then
            local npc = target
            y = self:AddDetailLink("Dropped by: " .. drop.npc .. " - " .. (drop.zone or "unknown zone"), function() UI:ShowEntity(npc) end, y)
        else
            y = self:AddDetailLink("Show drop location: " .. drop.npc .. " - " .. (drop.zone or "unknown zone"), function()
                NIQ.Map:ShowEntity(entity, "source")
            end, y)
        end
        count = count + 1
    end
    if count == 0 then
        y = self:AddDetailLink("No mapped quests, recipes, drops, or related records yet", function()
            NIQ:Print("Continue the EQWOW detail download in the updater, then apply the validated update.")
        end, y)
    end
    self.frame.detailScrollChild:SetHeight(math.max(1, -y + 8))
end

function UI:Show(searchText)
    self.frame:Show()
    self.filter = NIQ.db.searchFilter or "all"
    UIDropDownMenu_SetSelectedValue(self.frame.dropdown, self.filter)
    UIDropDownMenu_SetText(self.frame.dropdown, pretty(self.filter))
    if searchText then self.frame.search:SetText(searchText) else self:RunSearch(self.frame.search:GetText()) end
    self.frame.search:SetFocus()
end

function UI:ShowEntity(entity)
    if type(entity) == "string" then entity = NIQ.Data:GetEntity(entity) end
    entity = NIQ.Data:EnsureEntityDetail(entity)
    if not entity then return end
    self.frame:Show()
    self.current = entity
    self.frame.detailIcon:SetTexture(iconFor(entity))
    self.frame.detailName:SetText(entity.name .. (entity.rank and " - " .. entity.rank or ""))
    self.frame.detailType:SetText(entity.classification or pretty(entity.type))
    local lines = { entity.summary or "No summary is available for this journal entry." }
    append(lines, "Zone", entity.zone)
    append(lines, "Level", entity.level)
    append(lines, "Location", entity.location)
    append(lines, "Skill", entity.skill)
    append(lines, "Trivial", entity.trivial)
    if entity.type == "spell" then
        append(lines, "Game", entity.game == "wow" and "World of Warcraft" or "EverQuest")
        append(lines, "Spell ID", entity.clientId or entity.realmId)
        append(lines, "Rank", entity.rank)
        append(lines, "Spellbook", entity.spellBookTab)
        append(lines, "Description", entity.description)
        append(lines, "Cast", entity.castTimeText)
        append(lines, "Cooldown", entity.cooldownText)
        append(lines, "Cast time", entity.castTime and tostring(entity.castTime) .. " ms" or nil)
        append(lines, "Range", entity.maxRange and tostring(entity.minRange or 0) .. "-" .. tostring(entity.maxRange) or nil)
        local knownBy = {}
        for name in pairs(entity.knownBy or {}) do table.insert(knownBy, name) end
        table.sort(knownBy)
        if #knownBy > 0 then append(lines, "Known by", table.concat(knownBy, ", ")) end
    end
    if entity.classes then append(lines, "Usable by", table.concat(entity.classes, ", ")) end
    if entity.uses then
        table.insert(lines, "")
        table.insert(lines, "|cffffd100Used for|r")
        for _, use in ipairs(entity.uses) do table.insert(lines, "  - " .. use) end
    end
    if entity.objectives and #entity.objectives > 0 then
        table.insert(lines, "")
        table.insert(lines, "|cffffd100Objectives|r")
        for _, objective in ipairs(entity.objectives) do
            local text = type(objective) == "table" and objective.text or objective
            if text and text ~= "" then table.insert(lines, "  - " .. tostring(text)) end
        end
    end
    if entity.drops then
        table.insert(lines, "")
        table.insert(lines, "|cffffd100Found from|r")
        for _, drop in ipairs(entity.drops) do
            local chance = drop.chance and " - approx. " .. tostring(drop.chance) .. "%" or ""
            local level = drop.level or ((drop.minLevel or drop.maxLevel) and tostring(drop.minLevel or "?") .. "-" .. tostring(drop.maxLevel or "?") or nil)
            table.insert(lines, "  - " .. drop.npc .. " - " .. (drop.zone or "unknown") .. (level and " (level " .. level .. ")" or "") .. chance)
        end
    end
    local relations = NIQ.Data:GetRelations(entity)
    if #relations > 0 then
        table.insert(lines, "")
        table.insert(lines, "|cffffd100Related|r")
        for _, relation in ipairs(relations) do table.insert(lines, "  - " .. relation.name .. " [" .. relation.type .. "]") end
    end
    local recommendation = NIQ.Recommendation:Evaluate(entity)
    table.insert(lines, "")
    table.insert(lines, "|cffffd100Recommendation:|r " .. recommendation.action)
    table.insert(lines, recommendation.reason)
    local comparison = NIQ.Recommendation:CompareEquipped(entity)
    if comparison then
        table.insert(lines, "|cffffd100Worth crafting/equipping:|r " .. comparison.verdict)
        table.insert(lines, comparison.details)
    end
    if entity.source then
        table.insert(lines, "")
        table.insert(lines, "|cff6b5030Source: " .. (entity.source.name or entity.source.sourceId or "local observation") .. "|r")
        append(lines, "Source record ID", entity.source.recordId)
        append(lines, "Snapshot", entity.source.snapshotDate or entity.source.snapshotId)
        table.insert(lines, "|cff6b5030Confidence: " .. (entity.source.confidence or "unknown") .. (entity.source.transport == "unverified-http" and " - unverified HTTP" or "") .. "|r")
        table.insert(lines, "|cff6b5030" .. (entity.source.url or "No external source URL") .. "|r")
    end
    self.frame.detail:SetText(table.concat(lines, "\n"))
    self:BuildDetailLinks(entity, relations)
    NIQ:SetEnabled(self.frame.actions[1], entity.map or entity.zone or entity.drops)
    NIQ:SetEnabled(self.frame.actions[2], entity.turnins and #entity.turnins > 0)
    NIQ:SetEnabled(self.frame.actions[3], #relations > 0)
    NIQ:SetEnabled(self.frame.actions[4], entity.recipes and #entity.recipes > 0)
    NIQ:SetEnabled(self.frame.actions[5], entity.source and entity.source.url and string.find(entity.source.url, "^https?://"))
    self:RunSearch(self.frame.search:GetText())
end
