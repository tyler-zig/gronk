local ADDON_NAME = ...

local DEFAULT_CONFIG = {
    enabled = true,
    trigger = "!grok",
    draftOnly = true,
    autoRespond = false,
    maxAutoReplyLength = 240,
    channels = {
        GUILD = true,
        OFFICER = false,
        PARTY = false,
        RAID = false,
        INSTANCE_CHAT = false,
        CHANNEL = false,
        SAY = false,
        YELL = false,
    },
    channelNames = {},
}

local CHAT_EVENTS = {
    CHAT_MSG_GUILD = "GUILD",
    CHAT_MSG_OFFICER = "OFFICER",
    CHAT_MSG_PARTY = "PARTY",
    CHAT_MSG_PARTY_LEADER = "PARTY",
    CHAT_MSG_RAID = "RAID",
    CHAT_MSG_RAID_LEADER = "RAID",
    CHAT_MSG_INSTANCE_CHAT = "INSTANCE_CHAT",
    CHAT_MSG_INSTANCE_CHAT_LEADER = "INSTANCE_CHAT",
    CHAT_MSG_CHANNEL = "CHANNEL",
    CHAT_MSG_SAY = "SAY",
    CHAT_MSG_YELL = "YELL",
}

local initialized = false

local function copyDefaults(target, defaults)
    for key, value in pairs(defaults) do
        if type(value) == "table" then
            if type(target[key]) ~= "table" then
                target[key] = {}
            end
            copyDefaults(target[key], value)
        elseif target[key] == nil then
            target[key] = value
        end
    end
end

local function normalizeChannelName(name)
    if not name or name == "" then
        return ""
    end
    return string.lower((name:gsub("^%d+%.%s*", "")))
end

local function isChannelAllowed(channelType, channelName)
    local config = GronkDB.config
    if not config.channels[channelType] then
        return false
    end

    if channelType ~= "CHANNEL" then
        return true
    end

    local configured = config.channelNames or {}
    local hasNames = false
    for _ in pairs(configured) do
        hasNames = true
        break
    end

    if not hasNames then
        return true
    end

    return configured[normalizeChannelName(channelName)] == true
end

local function startsWithTrigger(message)
    local trigger = GronkDB.config.trigger or "!grok"
    if trigger == "" then
        return nil
    end

    local prefix = string.sub(message, 1, string.len(trigger))
    if string.lower(prefix) ~= string.lower(trigger) then
        return nil
    end

    local prompt = string.sub(message, string.len(trigger) + 1)
    prompt = prompt:gsub("^%s+", "")
    if prompt == "" then
        return nil
    end

    return prompt
end

local function addRequest(prompt, channelType, channelName, author)
    GronkDB.nextRequestId = (GronkDB.nextRequestId or 0) + 1
    local id = tostring(time()) .. "-" .. tostring(GronkDB.nextRequestId)

    table.insert(GronkDB.queue, {
        id = id,
        prompt = prompt,
        channelType = channelType,
        channelName = channelName or "",
        author = author or "",
        createdAt = date("!%Y-%m-%dT%H:%M:%SZ"),
        status = "pending",
    })

    print("|cff55ddffGronk:|r queued question " .. id .. ". Run the bridge, then /reload for responses.")
end

local function splitMessage(text, limit)
    local chunks = {}
    local remaining = text or ""
    limit = limit or 240

    while string.len(remaining) > limit do
        local cut = limit
        for i = limit, math.max(1, limit - 40), -1 do
            if string.sub(remaining, i, i) == " " then
                cut = i
                break
            end
        end

        table.insert(chunks, string.sub(remaining, 1, cut))
        remaining = remaining:sub(cut + 1):gsub("^%s+", "")
    end

    if remaining ~= "" then
        table.insert(chunks, remaining)
    end

    return chunks
end

local function sendResponse(response)
    local text = response.answer or ""
    if text == "" then
        return
    end

    local channelType = response.channelType or "GUILD"
    local channelName = response.channelName
    local chunks = splitMessage(text, GronkDB.config.maxAutoReplyLength)

    for _, chunk in ipairs(chunks) do
        if channelType == "CHANNEL" and channelName and channelName ~= "" then
            local channelId = GetChannelName(channelName)
            if not channelId or channelId == 0 then
                channelId = GetChannelName(normalizeChannelName(channelName))
            end

            if channelId and channelId > 0 then
                SendChatMessage(chunk, "CHANNEL", nil, channelId)
            else
                print("|cff55ddffGronk:|r could not find channel " .. channelName .. " for auto response.")
            end
        else
            SendChatMessage(chunk, channelType)
        end
    end
end

local function processResponses()
    if not GronkDB.responses then
        return
    end

    for _, response in ipairs(GronkDB.responses) do
        if not response.delivered then
            print("|cff55ddffGronk:|r " .. (response.answer or ""))
            if GronkDB.config.autoRespond and not GronkDB.config.draftOnly then
                sendResponse(response)
            end
            response.delivered = true
        end
    end
end

local function printStatus()
    local pending = 0
    local responses = 0

    for _, request in ipairs(GronkDB.queue or {}) do
        if request.status == "pending" then
            pending = pending + 1
        end
    end

    for _, response in ipairs(GronkDB.responses or {}) do
        if not response.delivered then
            responses = responses + 1
        end
    end

    print("|cff55ddffGronk|r enabled=" .. tostring(GronkDB.config.enabled)
        .. " trigger=" .. tostring(GronkDB.config.trigger)
        .. " draftOnly=" .. tostring(GronkDB.config.draftOnly)
        .. " autoRespond=" .. tostring(GronkDB.config.autoRespond)
        .. " pending=" .. tostring(pending)
        .. " unread=" .. tostring(responses))
end

local uiFrame
local uiControls = {}

local function makeLabel(parent, text, x, y)
    local label = parent:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
    label:SetPoint("TOPLEFT", parent, "TOPLEFT", x, y)
    label:SetText(text)
    return label
end

local function makeButton(parent, text, width, height, x, y, onClick)
    local button = CreateFrame("Button", nil, parent, "UIPanelButtonTemplate")
    button:SetSize(width, height)
    button:SetPoint("TOPLEFT", parent, "TOPLEFT", x, y)
    button:SetText(text)
    button:SetScript("OnClick", onClick)
    return button
end

local function makeCheck(parent, text, x, y, onClick)
    local check = CreateFrame("CheckButton", nil, parent, "UICheckButtonTemplate")
    check:SetSize(24, 24)
    check:SetPoint("TOPLEFT", parent, "TOPLEFT", x, y)
    check.text = parent:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
    check.text:SetPoint("LEFT", check, "RIGHT", 2, 0)
    check.text:SetText(text)
    check:SetScript("OnClick", function(self)
        onClick(self:GetChecked())
        if uiFrame and uiFrame.Refresh then
            uiFrame:Refresh()
        end
    end)
    return check
end

local function makeEditBox(parent, width, height, x, y)
    local edit = CreateFrame("EditBox", nil, parent, "InputBoxTemplate")
    edit:SetSize(width, height)
    edit:SetPoint("TOPLEFT", parent, "TOPLEFT", x, y)
    edit:SetAutoFocus(false)
    edit:SetFontObject(ChatFontNormal)
    edit:SetTextInsets(4, 4, 0, 0)
    edit:SetScript("OnEscapePressed", function(self)
        self:ClearFocus()
    end)
    edit:SetScript("OnEnterPressed", function(self)
        self:ClearFocus()
    end)
    return edit
end

local function countPending()
    local pending = 0
    for _, request in ipairs(GronkDB.queue or {}) do
        if request.status == "pending" then
            pending = pending + 1
        end
    end
    return pending
end

local function countUnread()
    local unread = 0
    for _, response in ipairs(GronkDB.responses or {}) do
        if not response.delivered then
            unread = unread + 1
        end
    end
    return unread
end

local function createOptionsUI()
    if uiFrame then
        return uiFrame
    end

    local frame = CreateFrame("Frame", "GronkOptionsFrame", UIParent)
    if not frame.SetBackdrop and BackdropTemplateMixin then
        Mixin(frame, BackdropTemplateMixin)
    end

    frame:SetSize(430, 520)
    frame:SetPoint("CENTER")
    frame:SetFrameStrata("DIALOG")
    frame:EnableMouse(true)
    frame:SetMovable(true)
    frame:RegisterForDrag("LeftButton")
    frame:SetScript("OnDragStart", frame.StartMoving)
    frame:SetScript("OnDragStop", frame.StopMovingOrSizing)
    frame:Hide()

    if frame.SetBackdrop then
        frame:SetBackdrop({
            bgFile = "Interface\\DialogFrame\\UI-DialogBox-Background",
            edgeFile = "Interface\\DialogFrame\\UI-DialogBox-Border",
            tile = true,
            tileSize = 32,
            edgeSize = 32,
            insets = { left = 11, right = 12, top = 12, bottom = 11 },
        })
    end

    local title = frame:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
    title:SetPoint("TOPLEFT", frame, "TOPLEFT", 18, -18)
    title:SetText("Gronk")

    local close = CreateFrame("Button", nil, frame, "UIPanelCloseButton")
    close:SetPoint("TOPRIGHT", frame, "TOPRIGHT", -6, -6)

    uiControls.status = frame:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    uiControls.status:SetPoint("TOPLEFT", frame, "TOPLEFT", 18, -45)
    uiControls.status:SetWidth(390)
    uiControls.status:SetJustifyH("LEFT")

    uiControls.enabled = makeCheck(frame, "Enabled", 18, -75, function(checked)
        GronkDB.config.enabled = checked and true or false
    end)
    uiControls.draft = makeCheck(frame, "Draft-only", 140, -75, function(checked)
        GronkDB.config.draftOnly = checked and true or false
        if checked then
            GronkDB.config.autoRespond = false
        end
    end)
    uiControls.auto = makeCheck(frame, "Auto respond on login", 260, -75, function(checked)
        GronkDB.config.autoRespond = checked and true or false
        if checked then
            GronkDB.config.draftOnly = false
        end
    end)

    makeLabel(frame, "Trigger", 18, -115)
    uiControls.trigger = makeEditBox(frame, 120, 24, 18, -135)
    makeButton(frame, "Save", 70, 22, 150, -135, function()
        local value = uiControls.trigger:GetText()
        if value and value ~= "" then
            GronkDB.config.trigger = value
            print("|cff55ddffGronk:|r trigger set to " .. value)
        end
        uiControls.trigger:ClearFocus()
        frame:Refresh()
    end)

    makeLabel(frame, "Chat Sources", 18, -180)
    local channelRows = {
        { "GUILD", "Guild", 18, -205 },
        { "OFFICER", "Officer", 140, -205 },
        { "PARTY", "Party", 260, -205 },
        { "RAID", "Raid", 18, -235 },
        { "INSTANCE_CHAT", "Instance", 140, -235 },
        { "CHANNEL", "Custom channel", 260, -235 },
        { "SAY", "Say", 18, -265 },
        { "YELL", "Yell", 140, -265 },
    }
    uiControls.channels = {}
    for _, row in ipairs(channelRows) do
        local key = row[1]
        uiControls.channels[key] = makeCheck(frame, row[2], row[3], row[4], function(checked)
            GronkDB.config.channels[key] = checked and true or false
        end)
    end

    makeLabel(frame, "Allowed custom channel name", 18, -305)
    uiControls.channelName = makeEditBox(frame, 175, 24, 18, -325)
    makeButton(frame, "Allow", 70, 22, 205, -325, function()
        local value = normalizeChannelName(uiControls.channelName:GetText())
        if value ~= "" then
            GronkDB.config.channelNames[value] = true
            print("|cff55ddffGronk:|r allowed channel name " .. value)
        end
        uiControls.channelName:SetText("")
        uiControls.channelName:ClearFocus()
    end)

    makeLabel(frame, "Manual question", 18, -370)
    uiControls.question = makeEditBox(frame, 280, 24, 18, -390)
    makeButton(frame, "Queue", 80, 22, 310, -390, function()
        local value = uiControls.question:GetText()
        if value and value ~= "" then
            addRequest(value, "GUILD", "", UnitName("player"))
            uiControls.question:SetText("")
            uiControls.question:ClearFocus()
        end
        frame:Refresh()
    end)

    makeButton(frame, "Show Responses", 115, 24, 18, -435, function()
        processResponses()
        frame:Refresh()
    end)
    makeButton(frame, "Clear", 70, 24, 145, -435, function()
        GronkDB.queue = {}
        GronkDB.responses = {}
        print("|cff55ddffGronk:|r cleared queued requests and responses.")
        frame:Refresh()
    end)
    makeButton(frame, "Close", 70, 24, 320, -435, function()
        frame:Hide()
    end)

    function frame:Refresh()
        uiControls.status:SetText("Pending: " .. tostring(countPending()) .. "   Unread responses: " .. tostring(countUnread()))
        uiControls.enabled:SetChecked(GronkDB.config.enabled)
        uiControls.draft:SetChecked(GronkDB.config.draftOnly)
        uiControls.auto:SetChecked(GronkDB.config.autoRespond)
        uiControls.trigger:SetText(GronkDB.config.trigger or "!grok")
        for key, check in pairs(uiControls.channels) do
            check:SetChecked(GronkDB.config.channels[key])
        end
    end

    uiFrame = frame
    return frame
end

local function showOptionsUI()
    local options = createOptionsUI()
    options:Refresh()
    options:Show()
end

local function handleSlash(input)
    local command, rest = input:match("^(%S*)%s*(.-)$")
    command = string.lower(command or "")

    if command == "" or command == "ui" or command == "config" then
        showOptionsUI()
    elseif command == "status" then
        printStatus()
    elseif command == "on" then
        GronkDB.config.enabled = true
        print("|cff55ddffGronk:|r enabled.")
    elseif command == "off" then
        GronkDB.config.enabled = false
        print("|cff55ddffGronk:|r disabled.")
    elseif command == "draft" then
        GronkDB.config.draftOnly = true
        GronkDB.config.autoRespond = false
        print("|cff55ddffGronk:|r draft-only mode enabled.")
    elseif command == "auto" then
        GronkDB.config.draftOnly = false
        GronkDB.config.autoRespond = true
        print("|cff55ddffGronk:|r auto-response mode enabled. Responses post after /reload.")
    elseif command == "trigger" and rest ~= "" then
        GronkDB.config.trigger = rest
        print("|cff55ddffGronk:|r trigger set to " .. rest)
    elseif command == "ask" and rest ~= "" then
        addRequest(rest, "GUILD", "", UnitName("player"))
    elseif command == "channel" and rest ~= "" then
        local channel = string.upper(rest)
        GronkDB.config.channels[channel] = not GronkDB.config.channels[channel]
        print("|cff55ddffGronk:|r " .. channel .. "=" .. tostring(GronkDB.config.channels[channel]))
    elseif command == "allowname" and rest ~= "" then
        local name = normalizeChannelName(rest)
        GronkDB.config.channelNames[name] = true
        print("|cff55ddffGronk:|r allowed channel name " .. name)
    elseif command == "clear" then
        GronkDB.queue = {}
        GronkDB.responses = {}
        print("|cff55ddffGronk:|r cleared queued requests and responses.")
    else
        print("|cff55ddffGronk commands:|r /gronk, ui, status, on, off, draft, auto, trigger <text>, ask <question>, channel <GUILD|CHANNEL|...>, allowname <name>, clear")
    end
end

local frame = CreateFrame("Frame")

frame:RegisterEvent("ADDON_LOADED")
frame:RegisterEvent("PLAYER_LOGIN")
for event in pairs(CHAT_EVENTS) do
    frame:RegisterEvent(event)
end

frame:SetScript("OnEvent", function(_, event, ...)
    if event == "ADDON_LOADED" then
        local loadedAddon = ...
        if loadedAddon ~= ADDON_NAME then
            return
        end

        GronkDB = GronkDB or {}
        GronkDB.config = GronkDB.config or {}
        GronkDB.queue = GronkDB.queue or {}
        GronkDB.responses = GronkDB.responses or {}
        GronkDB.nextRequestId = GronkDB.nextRequestId or 0
        copyDefaults(GronkDB.config, DEFAULT_CONFIG)
        initialized = true

        SLASH_GRONK1 = "/gronk"
        SlashCmdList.GRONK = handleSlash
        return
    end

    if event == "PLAYER_LOGIN" and initialized then
        processResponses()
        return
    end

    if not GronkDB or not GronkDB.config or not GronkDB.config.enabled then
        return
    end

    local channelType = CHAT_EVENTS[event]
    local message, author, _, _, _, _, _, _, channelName = ...
    if not channelType or not isChannelAllowed(channelType, channelName) then
        return
    end

    local prompt = startsWithTrigger(message or "")
    if prompt then
        addRequest(prompt, channelType, channelName, author)
    end
end)
