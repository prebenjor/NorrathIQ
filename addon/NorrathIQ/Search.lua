local NIQ = NorrathIQ
local Search = {}
NIQ.Search = Search
NIQ:RegisterModule("Search", Search)

local typeOrder = { item = 1, quest = 2, npc = 3, recipe = 4, spell = 5, zone = 6, object = 7, container = 8 }

local function resultComesFirst(a, b)
    if a.score ~= b.score then return a.score > b.score end
    local ao, bo = typeOrder[a.entity.type] or 99, typeOrder[b.entity.type] or 99
    if ao ~= bo then return ao < bo end
    return a.entity.name < b.entity.name
end

function Search:Query(text, filter, limit)
    local query = NIQ:Normalize(text)
    filter = filter or "all"
    limit = limit or 50

    local function included(entity)
        return filter == "all" or entity.type == filter
            or (filter == "eqspell" and entity.type == "spell" and entity.game ~= "wow")
            or (filter == "wowspell" and entity.type == "spell" and entity.game == "wow")
            or (filter == "key" and entity.flags and entity.flags.K)
            or (filter == "inventory" and entity.type == "item" and (entity.flags or entity.recommendation))
    end

    -- Opening /niq must never synchronously parse the full external database.
    -- Empty searches use whatever is already loaded (the bundled starter set on first open).
    local alreadyIndexed = query ~= "" and (NIQ.Data.exact[query] or NIQ.Data.aliases[query])
    if query ~= "" and not alreadyIndexed then NIQ.Data:LoadExternalPacks(query) end

    -- Exact names are the common case and already have a lookup table.
    if query ~= "" then
        local exactIds = NIQ.Data.exact[query] or NIQ.Data.aliases[query]
        if exactIds then
            local exactResults = {}
            for _, id in ipairs(exactIds) do
                local entity = NIQ.Data.entities[id]
                if entity and included(entity) then
                    table.insert(exactResults, { entity = entity, score = 2000 })
                    if #exactResults >= limit then break end
                end
            end
            if #exactResults > 0 then return exactResults end
        end
    end

    local terms = {}
    for term in string.gmatch(query, "%S+") do table.insert(terms, term) end
    local results = {}
    for _, entity in pairs(NIQ.Data.entities) do
        if included(entity) then
            if query == "" then
                table.insert(results, { entity = entity, score = 1 })
                if #results >= limit then return results end
            else
                local haystack = NIQ:Normalize(entity.name .. " " .. table.concat(entity.aliases or {}, " ") .. " "
                    .. (entity.summary or "") .. " " .. (entity.rank or "") .. " " .. (entity.spellBookTab or "")
                    .. " " .. (entity.game == "wow" and "world of warcraft wow" or entity.type == "spell" and "everquest eq" or ""))
                local score, matches = 0, true
                for _, term in ipairs(terms) do
                    local startAt = string.find(haystack, term, 1, true)
                    if not startAt then matches = false break end
                    score = score + (startAt == 1 and 100 or 20)
                end
                if NIQ:Normalize(entity.name) == query then score = score + 1000 end
                if matches then
                    table.insert(results, { entity = entity, score = score })
                    table.sort(results, resultComesFirst)
                    if #results > limit then table.remove(results) end
                end
            end
        end
    end
    table.sort(results, resultComesFirst)
    return results
end

function Search:ResolveItemLink(link)
    return NIQ.Data:ResolveExact(NIQ:ItemNameFromLink(link), false, false)
end
