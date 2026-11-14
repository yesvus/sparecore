# macOS installation and troubleshooting

SpareCore currently implements **observe-only status**, not worker scheduling.
The Hammerspoon icon reports Off, Light or Boost eligibility.

The read-only command below checks macOS, Python, Hammerspoon CLI,
the existence of an init.lua file, OrbStack CLI and optional Tailscale CLI:

~~~sh
python3 -m sparecore doctor
python3 -m sparecore doctor --json
~~~

It does not install software, mutate settings or authenticate devices.

## Setup

1. Install Python 3.9+ and Hammerspoon from trusted sources.
2. Clone the repository and run the unit tests and doctor command.
3. Preserve existing ~/.hammerspoon/init.lua; add a single dofile line
   pointing to the absolute path of the repo's adapters/hammerspoon/init.lua.
4. Open Hammerspoon and choose Reload Config. Observe the one CPU menu icon.

macOS may request permissions from Hammerspoon. Grant only the capabilities
that are actually required; do not bypass operating system prompts.

## Troubleshooting

- **No icon:** Open Hammerspoon and inspect its Console for Lua errors.
  Check the clone path and init.lua loading location.
- **Multiple icons:** Remove duplicate dofile statements and avoid manually
  loading the adapter in addition to the persistent init.lua.
- **Python failure:** The menu adapter uses /usr/bin/python3 on macOS;
  this interpreter must be compatible even if a newer Python is in PATH.
- **Doctor says hs missing:** The Hammerspoon CLI is optional for the
  status menu but useful for scripted diagnostics.
- **Always Off or Light:** This is expected on battery, under load,
  when sensors are unknown or during the two-minute boost warm-up.
- **No worker:** Also expected. Worker lifecycle is not implemented yet;
  see the gated manual pilot in K3S_PILOT.md.

## Uninstall the menu

Remove only the SpareCore dofile statement from your init.lua and
reload Hammerspoon. Keep Hammerspoon if other automations use it.
Removing the menu does not remove an existing OrbStack guest.
