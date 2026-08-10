local NIQ = NorrathIQ

NIQ.API = {
    version = 1,
    Search = function(text, filter, limit)
        return NIQ.Search:Query(text, filter, limit)
    end,
    GetEntity = function(id)
        return NIQ.Data:GetEntity(id)
    end,
    GetRelations = function(entity)
        return NIQ.Data:GetRelations(entity)
    end,
    ShowOnMap = function(entity, purpose)
        return NIQ.Map:ShowEntity(entity, purpose)
    end,
    RegisterBagAdapter = function(id, adapter)
        return NIQ:RegisterBagAdapter(id, adapter)
    end,
    RegisterMapProvider = function(id, provider)
        return NIQ:RegisterMapProvider(id, provider)
    end,
    RegisterDataPack = function(pack)
        return NIQ:RegisterDataPack(pack)
    end,
}

_G.NorrathIQ_API = NIQ.API
