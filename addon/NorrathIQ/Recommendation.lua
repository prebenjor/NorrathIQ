local NIQ = NorrathIQ
local Recommendation = {}
NIQ.Recommendation = Recommendation
NIQ:RegisterModule("Recommendation", Recommendation)

local precedence = { K = 5, Q = 4, R = 3, T = 2, ["$"] = 1 }

local function hasEntries(value)
    return type(value) == "table" and next(value) ~= nil
end

local function hasRetainedUse(entity)
    if not entity then return false end
    if entity.flags and (entity.flags.K or entity.flags.Q or entity.flags.R or entity.flags.T) then return true end
    for _, key in ipairs({ "uses", "quests", "turnins", "recipes", "components", "related", "rewards" }) do
        if hasEntries(entity[key]) then return true end
    end
    return false
end

function Recommendation:PrimaryFlag(entity)
    local best, score = nil, 0
    for flag, enabled in pairs(entity and entity.flags or {}) do
        if enabled and (precedence[flag] or 0) > score then best, score = flag, precedence[flag] end
    end
    return best
end

function Recommendation:Evaluate(entity)
    if not entity then return { action = "REVIEW", reason = "No knowledge record is available." } end
    if entity.flags and entity.flags.K then
        return { action = "KEEP", reason = entity.recommendation and entity.recommendation.reason or "Known key or important progression item." }
    end
    if entity.flags and (entity.flags.Q or entity.flags.R or entity.flags.T) then
        return { action = "KEEP", reason = entity.recommendation and entity.recommendation.reason or "Known quest, research, or tradeskill use." }
    end
    if hasEntries(entity.quests) or hasEntries(entity.turnins) then
        return { action = "KEEP", reason = "Known quest relationship; verify the quest before discarding this item." }
    end
    if hasEntries(entity.recipes) or hasEntries(entity.components) or hasEntries(entity.uses) then
        return { action = "KEEP", reason = "Known recipe, research, or tradeskill relationship." }
    end
    if hasEntries(entity.related) or hasEntries(entity.rewards) then
        return { action = "REVIEW", reason = "This item has related knowledge records; review them before discarding it." }
    end
    if entity.recommendation and entity.recommendation.action ~= "VENDOR" and entity.recommendation.action ~= "DESTROY" then
        return entity.recommendation
    end
    -- Destructive guidance is opt-in data, never inferred from a vendor price.
    -- A full detail record must explicitly certify that no retained use exists.
    if entity._detail and entity.verifiedNoUse == true and not hasRetainedUse(entity)
        and entity.vendorValue and entity.vendorValue > 0 then
        return { action = "VENDOR", reason = "Verified vendor value and explicitly verified to have no retained use." }
    end
    if entity._detail and entity.vendorValue == 0 and entity.verifiedNoUse == true and not hasRetainedUse(entity) then
        return { action = "DESTROY", reason = "Verified zero value and no known use." }
    end
    return { action = "REVIEW", reason = "No verified safe-discard decision is available." }
end

local slotMap = { HEAD = 1, NECK = 2, SHOULDER = 3, CHEST = 5, WAIST = 6, LEGS = 7, FEET = 8, WRIST = 9, HANDS = 10, FINGER = 11, TRINKET = 13, BACK = 15, MAINHAND = 16, OFFHAND = 17, RANGED = 18 }

function Recommendation:GetWeaponMetrics(link)
    if not link or not CreateFrame then return nil end
    if not self.scanTooltip then
        self.scanTooltip = CreateFrame("GameTooltip", "NorrathIQScanTooltip", UIParent, "GameTooltipTemplate")
        self.scanTooltip:SetOwner(UIParent, "ANCHOR_NONE")
    end
    self.scanTooltip:ClearLines()
    self.scanTooltip:SetHyperlink(link)
    local minimum, maximum, speed
    for index = 1, self.scanTooltip:NumLines() do
        local fontString = _G["NorrathIQScanTooltipTextLeft" .. index]
        local line = fontString and fontString:GetText()
        if line then
            local low, high = string.match(line, "(%d+)%s*%-%s*(%d+)%s+[Dd]amage")
            minimum = minimum or tonumber(low)
            maximum = maximum or tonumber(high)
            speed = speed or tonumber(string.match(line, "[Ss]peed%s+(%d+%.?%d*)"))
            minimum = minimum or tonumber(string.match(line, "DMG:%s*(%d+)"))
            maximum = maximum or minimum
            local delay = tonumber(string.match(line, "Delay:%s*(%d+)"))
            if delay then speed = delay / 10 end
        end
    end
    if not minimum or not maximum or not speed or speed == 0 then return nil end
    return { minimum = minimum, maximum = maximum, speed = speed, dps = ((minimum + maximum) / 2) / speed }
end

function Recommendation:CompareEquipped(entity)
    if not entity or not entity.slot then return nil end
    local slot = slotMap[entity.slot]
    if not slot or not GetInventoryItemLink then return { verdict = "Unknown", details = "No compatible equipment slot mapping." } end
    local equipped = GetInventoryItemLink("player", slot)
    if not equipped then return { verdict = "Yes", details = "The corresponding equipment slot is empty." } end
    if entity.weaponDamageMin and entity.weaponDamageMax and entity.weaponSpeed then
        local currentWeapon = self:GetWeaponMetrics(equipped)
        if currentWeapon then
            local average = (entity.weaponDamageMin + entity.weaponDamageMax) / 2
            local dps = average / entity.weaponSpeed
            local damageDelta = average - ((currentWeapon.minimum + currentWeapon.maximum) / 2)
            local speedDelta = entity.weaponSpeed - currentWeapon.speed
            local dpsDelta = dps - currentWeapon.dps
            local details = string.format(
                "%+.1f average damage, %+.2f sec speed (%s), %+.1f DPS",
                damageDelta, speedDelta, speedDelta > 0 and "slower" or (speedDelta < 0 and "faster" or "same"), dpsDelta
            )
            return { verdict = dpsDelta > 0 and "Yes" or "No", details = details }
        end
    end
    if not entity.wowStats or not GetItemStats then
        return { verdict = "Unknown", details = "Realm-normalized numeric stats are not installed; equipped item is " .. (NIQ:ItemNameFromLink(equipped) or "unknown") .. "." }
    end
    local current = GetItemStats(equipped) or {}
    local deltas, improved = {}, false
    for stat, value in pairs(entity.wowStats) do
        local delta = value - (current[stat] or 0)
        if delta ~= 0 then
            table.insert(deltas, stat .. " " .. (delta > 0 and "+" or "") .. tostring(delta))
            if delta > 0 then improved = true end
        end
    end
    return { verdict = improved and "Yes" or "No", details = #deltas > 0 and table.concat(deltas, ", ") or "No mapped stat difference." }
end
