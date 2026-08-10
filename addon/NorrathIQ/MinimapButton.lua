local NIQ = NorrathIQ
local MinimapButton = {}
NIQ.MinimapButton = MinimapButton
NIQ:RegisterModule("MinimapButton", MinimapButton)

local function atan2(y, x)
    if x > 0 then return math.atan(y / x) end
    if x < 0 and y >= 0 then return math.atan(y / x) + math.pi end
    if x < 0 and y < 0 then return math.atan(y / x) - math.pi end
    if x == 0 and y > 0 then return math.pi / 2 end
    if x == 0 and y < 0 then return -math.pi / 2 end
    return 0
end

function MinimapButton:UpdatePosition()
    if not self.button or not Minimap then return end
    local angle = math.rad((NIQ.db.minimap and NIQ.db.minimap.angle) or 220)
    self.button:ClearAllPoints()
    self.button:SetPoint("CENTER", Minimap, "CENTER", math.cos(angle) * 80, math.sin(angle) * 80)
end

function MinimapButton:UpdateDragPosition()
    if not Minimap or not GetCursorPosition then return end
    local cursorX, cursorY = GetCursorPosition()
    local scale = Minimap:GetEffectiveScale() or 1
    local centerX, centerY = Minimap:GetCenter()
    if not centerX or not centerY then return end
    cursorX, cursorY = cursorX / scale, cursorY / scale
    local angle = math.deg(atan2(cursorY - centerY, cursorX - centerX))
    NIQ.db.minimap.angle = angle
    self:UpdatePosition()
end

function MinimapButton:ToggleJournal()
    if not NIQ.UI or not NIQ.UI.frame then return end
    if NIQ.UI.frame:IsShown() then NIQ.UI.frame:Hide() else NIQ.UI:Show(nil) end
end

function MinimapButton:Initialize()
    NIQ.db.minimap = NIQ.db.minimap or { hidden = false, angle = 220 }
    local button = CreateFrame("Button", "NorrathIQMinimapButton", Minimap)
    button:SetSize(32, 32)
    button:SetFrameStrata("MEDIUM")
    button:SetFrameLevel(8)
    button:RegisterForClicks("LeftButtonUp", "RightButtonUp")
    button:RegisterForDrag("LeftButton")

    local icon = button:CreateTexture(nil, "BACKGROUND")
    icon:SetTexture("Interface\\Icons\\INV_Misc_Book_09")
    icon:SetSize(20, 20)
    icon:SetPoint("CENTER", 0, 0)
    button.icon = icon

    local border = button:CreateTexture(nil, "OVERLAY")
    border:SetTexture("Interface\\Minimap\\MiniMap-TrackingBorder")
    border:SetSize(54, 54)
    border:SetPoint("TOPLEFT", 0, 0)
    button.border = border
    button:SetHighlightTexture("Interface\\Minimap\\UI-Minimap-ZoomButton-Highlight", "ADD")

    button:SetScript("OnClick", function(_, mouseButton)
        if mouseButton == "RightButton" then
            if NIQ.Capture then NIQ:Print("Capture " .. NIQ.Capture:Status()) end
        else
            MinimapButton:ToggleJournal()
        end
    end)
    button:SetScript("OnDragStart", function(self)
        self.dragging = true
        self:SetScript("OnUpdate", function() MinimapButton:UpdateDragPosition() end)
    end)
    button:SetScript("OnDragStop", function(self)
        self.dragging = nil
        self:SetScript("OnUpdate", nil)
    end)
    button:SetScript("OnEnter", function(self)
        GameTooltip:SetOwner(self, "ANCHOR_LEFT")
        GameTooltip:AddLine("NorrathIQ", 0.4, 0.9, 0.82)
        GameTooltip:AddLine("Left-click: open or close the knowledge journal", 1, 1, 1)
        GameTooltip:AddLine("Right-click: show capture status", 0.75, 0.75, 0.75)
        GameTooltip:AddLine("Drag: move around the minimap", 0.75, 0.75, 0.75)
        GameTooltip:Show()
    end)
    button:SetScript("OnLeave", function() GameTooltip:Hide() end)

    self.button = button
    self:UpdatePosition()
    NIQ:SetShown(button, not NIQ.db.minimap.hidden)
end

function MinimapButton:SetHidden(hidden)
    NIQ.db.minimap.hidden = hidden and true or false
    NIQ:SetShown(self.button, not NIQ.db.minimap.hidden)
end
