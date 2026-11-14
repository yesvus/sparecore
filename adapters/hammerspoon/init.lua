-- SpareCore observe-only menu. Does not start a VM or modify Kubernetes.
-- Usage: sparecore = dofile("/absolute/path/to/sparecore/adapters/hammerspoon/init.lua")
local path = debug.getinfo(1, "S").source:gsub("^@", "")
local root = assert(path:match("^(.*)/adapters/hammerspoon/init%.lua$"))
local mode = hs.settings.get("sparecore.mode")
if mode ~= "auto" and mode ~= "on" and mode ~= "off" then mode = "off" end

local displaysAsleep = false
local state = {tier="off", reason="Waiting for host signals"}
local pending = nil
local sampling = nil
local previousVM = nil
local boostEligibleAt = nil
local lastUpdate = nil
local menu = assert(hs.menubar.new())
local icon = hs.image.imageFromPath(root .. "/assets/sparecore-menubar.png")
assert(icon, "SpareCore menu icon missing")
menu:setIcon(icon:setSize({w=17,h=17}), true)
menu:setTitle("")
local refresh

local function monotonic()
    return hs.timer.absoluteTime() / 1000000000
end

local function swapRate()
    local vm = hs.host.vmStat()
    if not vm or not vm.pageSize or not vm.swapIns or not vm.swapOuts then
        previousVM = nil
        return nil
    end
    local now = monotonic()
    local rate = nil
    if previousVM then
        local dt = now - previousVM.at
        local ins = vm.swapIns - previousVM.ins
        local outs = vm.swapOuts - previousVM.outs
        if dt >= 10 and ins >= 0 and outs >= 0 then
            -- Both directions are relevant to interactive latency; swap is counted
            -- in VM pages and converted to total MiB/s across the sample interval.
            rate = (ins + outs) * vm.pageSize / (dt * 1024 * 1024)
        end
    end
    previousVM = {at=now, ins=vm.swapIns, outs=vm.swapOuts}
    return rate
end

local function render()
    menu:setTooltip("SpareCore · " .. state.tier .. " · " .. state.reason)
    menu:setMenu({
        {title="SpareCore · " .. state.tier .. " (observe only)", disabled=true},
        {title=state.reason, disabled=true},
        {title="-"},
        {title="Auto", checked=mode=="auto", fn=function()
            mode="auto"; hs.settings.set("sparecore.mode",mode); boostEligibleAt=nil; refresh()
        end},
        {title="On (AC only)", checked=mode=="on", fn=function()
            mode="on"; hs.settings.set("sparecore.mode",mode); boostEligibleAt=nil; refresh()
        end},
        {title="Off", checked=mode=="off", fn=function()
            mode="off"; hs.settings.set("sparecore.mode",mode); boostEligibleAt=nil; refresh()
        end},
    })
end

local function applyResponse(code, output, err)
    pending = nil
    if code ~= 0 then
        boostEligibleAt = nil
        state = {tier="off", reason="Policy CLI failed"}
        lastUpdate = nil
        hs.printf("SpareCore: %s", tostring(err))
        return render()
    end
    local ok, parsed = pcall(hs.json.decode, output)
    if not ok or type(parsed) ~= "table" or
        (parsed.tier ~= "off" and parsed.tier ~= "light" and parsed.tier ~= "boost") then
        boostEligibleAt = nil
        state = {tier="off", reason="Malformed policy output"}
        lastUpdate = nil
        return render()
    end
    if parsed.tier == "boost" then
        local now = monotonic()
        if not boostEligibleAt then boostEligibleAt = now end
        if now - boostEligibleAt < 120 then
            parsed.tier = "light"
            parsed.reason = "Idle headroom stable check (2 min)"
        end
    else
        boostEligibleAt = nil
    end
    state = parsed
    lastUpdate = monotonic()
    render()
end

local function evaluate(cpu)
    sampling = nil
    if pending then return end
    local usage = cpu and cpu.overall and cpu.overall.active
    local input = hs.json.encode({
        on_ac = hs.battery.powerSource() == "AC Power",
        idle_seconds = hs.host.idleTime() or 0,
        displays_asleep = displaysAsleep,
        cpu_busy_percent = usage,
        thermal_state = hs.host.thermalState(),
        swap_io_mib_s = swapRate(),
        mode = mode,
    })
    local newTask = hs.task.new("/usr/bin/python3", applyResponse,
                               {"-m", "sparecore", "decide", "--macos-pressure", "--input", input})
    if not newTask then
        boostEligibleAt = nil
        state = {tier="off",reason="Cannot launch policy"}
        lastUpdate = nil
        return render()
    end
    newTask:setWorkingDirectory(root)
    pending = newTask
    if not newTask:start() then
        pending = nil
        boostEligibleAt = nil
        state = {tier="off",reason="Policy launch failed"}
        lastUpdate = nil
        render()
    end
end

refresh = function()
    if pending or sampling then return end
    -- Async sampling: do not block the Hammerspoon UI for CPU measurement.
    sampling = hs.host.cpuUsage(0.5, evaluate)
end

local battery = hs.battery.watcher.new(refresh):start()
local power = hs.caffeinate.watcher.new(function(event)
    if event == hs.caffeinate.watcher.screensDidSleep then
        displaysAsleep = true
    elseif event == hs.caffeinate.watcher.screensDidWake or event == hs.caffeinate.watcher.systemDidWake then
        displaysAsleep = false
        boostEligibleAt = nil
    end
    refresh()
end):start()
local timer = hs.timer.doEvery(30, refresh)
render()
refresh()

local controller = {}
function controller.status()
    return state.tier, state.reason
end
function controller.iconLoaded()
    return menu:icon() ~= nil and menu:title() == ""
end
function controller.statusAge()
    if not lastUpdate then return -1 end
    return monotonic() - lastUpdate
end
function controller.stop()
    timer:stop(); battery:stop(); power:stop()
    if sampling then sampling:stop() end
    if pending then pending:terminate() end
    menu:delete()
end
return controller
