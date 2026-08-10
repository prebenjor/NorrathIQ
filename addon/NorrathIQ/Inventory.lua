local NIQ = NorrathIQ
local Inventory = { pending = false, elapsed = 0, badges = {} }
NIQ.Inventory = Inventory
NIQ:RegisterModule("Inventory", Inventory)

local badgeColors = {
    Q = { 1.0, 0.85, 0.2 }, T = { 0.35, 0.85, 1.0 }, R = { 0.75, 0.45, 1.0 },
    K = { 1.0, 0.35, 0.25 }, ["$"] = { 0.45, 1.0, 0.45 },
}

function Inventory:Initialize()
    self.timer = CreateFrame("Frame")
    self.timer:SetScript("OnUpdate", function(_, elapsed)
        if not self.pending then return end
        self.elapsed = self.elapsed + elapsed
        if self.elapsed >= 0.12 then
            self.elapsed, self.pending = 0, false
            self:Refresh()
        end
    end)
    if ContainerFrame_Update and hooksecurefunc then
        hooksecurefunc("ContainerFrame_Update", function() self:Schedule() end)
    end
    self:Schedule()
end

function Inventory:OnEvent(event)
    if event == "BAG_UPDATE" or event == "PLAYER_LOGIN" then self:Schedule() end
end

function Inventory:Schedule()
    self.pending, self.elapsed = true, 0
end

function Inventory:GetBadge(button)
    if self.badges[button] then return self.badges[button] end
    local badge = button:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
    badge:SetPoint("TOPLEFT", button, "TOPLEFT", 2, -2)
    badge:SetShadowOffset(1, -1)
    self.badges[button] = badge
    return badge
end

function Inventory:UpdateButton(button, bag, slot)
    local badge = self:GetBadge(button)
    badge:SetText("")
    if not NIQ.db.showBagBadges or not GetContainerItemLink then return end
    local link = GetContainerItemLink(bag, slot)
    if not link then return end
    local entity, status = NIQ.Search:ResolveItemLink(link)
    if status ~= "exact" or not entity then return end
    local flag = NIQ.Recommendation:PrimaryFlag(entity)
    if not flag then
        local advice = NIQ.Recommendation:Evaluate(entity)
        if advice.action == "VENDOR" then flag = "$" end
    end
    if flag then
        local color = badgeColors[flag] or { 1, 1, 1 }
        badge:SetText(flag)
        badge:SetTextColor(color[1], color[2], color[3])
    end
end

function Inventory:RefreshDefault()
    for frameIndex = 1, 13 do
        local container = _G["ContainerFrame" .. frameIndex]
        if container and container:IsShown() then
            local bag = container:GetID()
            local size = bag and GetContainerNumSlots and GetContainerNumSlots(bag) or 0
            for visualIndex = 1, size do
                local button = _G["ContainerFrame" .. frameIndex .. "Item" .. visualIndex]
                if button then self:UpdateButton(button, bag, button:GetID()) end
            end
        end
    end
end

function Inventory:Refresh()
    self:RefreshDefault()
    for id, adapter in pairs(NIQ.bagAdapters) do
        if adapter.Refresh then
            local ok, err = pcall(adapter.Refresh, adapter, self)
            if not ok then NIQ:Print("Bag adapter " .. id .. " failed: " .. tostring(err)) end
        end
    end
end
