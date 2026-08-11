local NIQ = NorrathIQ
local Tooltip = { current = nil }
NIQ.Tooltip = Tooltip
NIQ:RegisterModule("Tooltip", Tooltip)

local colors = {
    KEEP = { 0.25, 1.0, 0.35 },
    VENDOR = { 1.0, 0.82, 0.2 },
    DESTROY = { 1.0, 0.25, 0.25 },
    REVIEW = { 0.55, 0.8, 1.0 },
}

function Tooltip:Initialize()
    self:CreateActions()
    local function hook(tooltip)
        if tooltip and tooltip.HookScript then
            tooltip:HookScript("OnTooltipSetItem", function(frame) self:Decorate(frame) end)
            tooltip:HookScript("OnHide", function() if self.actions then self.actions:Hide() end end)
        end
    end
    hook(GameTooltip)
    hook(ItemRefTooltip)
    hook(ShoppingTooltip1)
    hook(ShoppingTooltip2)
end

function Tooltip:CreateActions()
    local frame = CreateFrame("Frame", "NorrathIQTooltipActions", UIParent)
    frame:SetSize(390, 28)
    frame:SetFrameStrata("TOOLTIP")
    frame:Hide()
    local definitions = {
        { "Drops", function() if self.current then NIQ.Map:ShowEntity(self.current, "source") end end },
        { "Recipe", function() if self.current and NIQ.UI then NIQ.UI:ShowEntity(self.current.recipes and NIQ.Data:GetEntity(self.current.recipes[1]) or self.current) end end },
        { "Source map", function() if self.current then NIQ.Map:ShowEntity(self.current, "source") end end },
        { "Turn-in map", function() if self.current then NIQ.Map:ShowEntity(self.current, "turnin") end end },
    }
    frame.buttons = {}
    for index, definition in ipairs(definitions) do
        local button = CreateFrame("Button", nil, frame, "UIPanelButtonTemplate")
        button:SetSize(92, 24)
        button:SetPoint("LEFT", (index - 1) * 96, 0)
        button:SetText(definition[1])
        button:SetScript("OnClick", definition[2])
        frame.buttons[index] = button
    end
    self.actions = frame
end

local function addList(tooltip, label, values, formatter, maximum)
    if not values or #values == 0 then return end
    maximum = maximum or 3
    for index, value in ipairs(values) do
        if index > maximum then
            tooltip:AddLine("  +" .. tostring(#values - maximum) .. " more", 0.65, 0.65, 0.65)
            break
        end
        local text = formatter and formatter(value) or tostring(value)
        tooltip:AddLine((index == 1 and label .. ": " or "  ") .. text, 0.78, 0.9, 0.88, true)
    end
end

function Tooltip:Decorate(tooltip)
    if not NIQ.db or not NIQ.db.showTooltips or tooltip._niqDecorating then return end
    tooltip._niqDecorating = true
    local name, link = tooltip:GetItem()
    if not name then
        tooltip._niqDecorating = nil
        return
    end
    -- Tooltip hovers must never load or queue an offline data shard. They use
    -- only knowledge already resident in memory.
    local entity, status = NIQ.Data:ResolveExact(name, false, false)
    if status == "ambiguous" then
        tooltip:AddLine(" ")
        tooltip:AddLine("NorrathIQ: multiple exact knowledge matches", 1, 0.75, 0.2)
        tooltip:AddLine("Open /niq to choose the correct variant.", 0.75, 0.75, 0.75, true)
        tooltip:Show()
        tooltip._niqDecorating = nil
        return
    end
    if not entity then
        tooltip._niqDecorating = nil
        return
    end
    tooltip:AddLine(" ")
    tooltip:AddLine("|cff65d6c7NorrathIQ|r — " .. (entity.classification or entity.type), 0.4, 0.9, 0.82)
    if entity.summary then tooltip:AddLine(entity.summary, 0.88, 0.88, 0.88, true) end
    addList(tooltip, "Used for", entity.uses)
    addList(tooltip, "Dropped by", entity.drops, function(drop)
        local levelText = drop.level
        if not levelText and (drop.minLevel or drop.maxLevel) then
            if drop.minLevel and drop.maxLevel and drop.minLevel == drop.maxLevel then
                levelText = tostring(drop.minLevel)
            else
                levelText = tostring(drop.minLevel or "?") .. "-" .. tostring(drop.maxLevel or "?")
            end
        end
        local level = levelText and " (level " .. levelText .. ")" or ""
        return drop.npc .. level .. " — " .. (drop.zone or "unknown zone")
    end)
    addList(tooltip, "Known source zones", entity.sourceZones, function(zone) return tostring(zone) end)
    addList(tooltip, "Related", NIQ.Data:GetRelations(entity, false), function(related)
        return related.name .. " [" .. related.type .. "]"
    end, 4)
    local recommendation = NIQ.Recommendation:Evaluate(entity)
    local color = colors[recommendation.action] or colors.REVIEW
    tooltip:AddLine("Inventory guidance: " .. recommendation.action, color[1], color[2], color[3])
    tooltip:AddLine(recommendation.reason, 0.82, 0.82, 0.82, true)
    local comparison = NIQ.Recommendation:CompareEquipped(entity)
    if comparison then
        tooltip:AddLine("Worth crafting/equipping: " .. comparison.verdict, 0.7, 0.85, 1)
        tooltip:AddLine(comparison.details, 0.72, 0.72, 0.72, true)
    end
    if NIQ.db.showConfidence and entity.source then
        local label = entity.source.name or entity.source.sourceId or "unknown source"
        local record = entity.source.recordId and " #" .. tostring(entity.source.recordId) or ""
        local snapshot = entity.source.snapshotDate and " - " .. tostring(entity.source.snapshotDate) or ""
        tooltip:AddLine("Source: " .. label .. record .. snapshot, 0.55, 0.65, 0.65)
        tooltip:AddLine("Confidence: " .. (entity.source.confidence or "unknown") .. (entity.source.transport == "unverified-http" and " - unverified HTTP" or ""), 0.55, 0.65, 0.65)
    end
    tooltip:Show()
    tooltip._niqDecorating = nil
    self.current = entity
    if tooltip == GameTooltip then
        self.actions:ClearAllPoints()
        self.actions:SetPoint("TOPLEFT", tooltip, "BOTTOMLEFT", 0, -2)
        NIQ:SetShown(self.actions.buttons[1], entity.drops and #entity.drops > 0)
        NIQ:SetShown(self.actions.buttons[2], entity.recipes and #entity.recipes > 0)
        NIQ:SetShown(self.actions.buttons[3], (entity.drops and #entity.drops > 0) or entity.map or entity.zone)
        NIQ:SetShown(self.actions.buttons[4], entity.turnins and #entity.turnins > 0)
        self.actions:Show()
    end
end
