-- SpareCore observe-only Hammerspoon menu; NO VM or Kubernetes mutations.
-- Usage: sparecore = dofile("/absolute/path/to/sparecore/adapters/hammerspoon/init.lua")
local path = debug.getinfo(1, "S").source:gsub("^@", "")
local root = assert(path:match("^(.*)/adapters/hammerspoon/init%.lua$"))
local mode = hs.settings.get("sparecore.mode")
if mode ~= "auto" and mode ~= "on" and mode ~= "off" then mode = "off" end
local displaysAsleep = false
local state = {tier="off", reason="Waiting for host signals"}
local pending = nil
local menu = assert(hs.menubar.new())
local refresh

local function render()
    menu:setTitle("SC:" .. state.tier)
    menu:setTooltip("SpareCore preview: no worker execution")
    menu:setMenu({
        {title="SpareCore: OBSERVE ONLY", disabled=true},
        {title=state.reason, disabled=true},
        {title="-"},
        {title="Auto", checked=mode=="auto", fn=function() mode="auto"; hs.settings.set("sparecore.mode",mode); refresh() end},
        {title="On (AC only)", checked=mode=="on", fn=function() mode="on"; hs.settings.set("sparecore.mode",mode); refresh() end},
        {title="Off", checked=mode=="off", fn=function() mode="off"; hs.settings.set("sparecore.mode",mode); refresh() end},
    })
end

refresh = function()
    if pending then return end
    local cpu = hs.host.cpuUsage()
    local args = hs.json.encode({
        on_ac = hs.battery.powerSource() == "AC Power",
        idle_seconds = hs.host.idleTime() or 0,
        displays_asleep = displaysAsleep,
        cpu_busy_percent = cpu and cpu.overall and cpu.overall.active or nil,
        mode = mode,
        -- memory_safe absent: deliberately forbids boost until validated.
    })
    local nextTask = hs.task.new("/usr/bin/python3",function(code,output,err)
        pending = nil
        if code == 0 then
            local parsed = hs.json.decode(output)
            if parsed and parsed.tier then state = parsed end
        else
            state = {tier="off",reason="Policy CLI failed"}
            hs.printf("SpareCore: %s",tostring(err))
        end
        render()
    end,{"-m","sparecore","decide","--input",args})
    if not nextTask then
        state = {tier="off",reason="Cannot launch Python"}
        render()
        return
    end
    nextTask:setWorkingDirectory(root)
    pending = nextTask
    if not pending:start() then pending=nil; state={tier="off",reason="Cannot run policy"}; render() end
end

local battery = hs.battery.watcher.new(refresh):start()
local power = hs.caffeinate.watcher.new(function(event)
    if event == hs.caffeinate.watcher.screensDidSleep then
        displaysAsleep = true
    elseif event == hs.caffeinate.watcher.screensDidWake or event == hs.caffeinate.watcher.systemDidWake then
        displaysAsleep = false
    end
    refresh()
end):start()
local timer = hs.timer.doEvery(30,refresh)
render()
refresh()
local controller = {}
function controller.status()
    return state.tier, state.reason
end
function controller.stop()
    timer:stop(); battery:stop(); power:stop()
    if pending then pending:terminate() end
    menu:delete()
end
return controller
