# Install with an AI coding agent

Copy this prompt into ChatGPT Work, Codex, OpenCode, Claude Code, Cursor or
another coding agent. This is for today's **observe-only** macOS version.

~~~text
Help me set up SpareCore on my personal Mac:
https://github.com/yesvus/sparecore

Goal: get one Hammerspoon menu-bar icon working in observe-only mode.
Preserve my Mac's interactivity, battery life and existing configuration.

1. Read the current README.md, INSTALL_PROMPT.md, AGENTS.md and
   docs/INSTALLATION.md from the repository before choosing commands.
2. Inspect my macOS version, architecture, Python, Homebrew,
   Hammerspoon configuration and existing OrbStack installation.
3. Explain missing prerequisites and get permission before installing
   packages, granting permissions or changing persistent files.
4. Clone into my preferred location; do not overwrite existing files.
   Back up an existing Hammerspoon init.lua before editing it.
5. Run python3 -m sparecore doctor and the repository unit tests.
6. If I approve, add exactly one dofile statement with the correct
   absolute path to ~/.hammerspoon/init.lua and reload Hammerspoon.
   Avoid duplicate menu icons or destructive configuration replacement.
7. Confirm the status menu appears and explain that Off/Light/Boost
   are hypothetical capacity decisions, not actual allocated resources.
8. Report exactly what changed, what was verified and how to revert.

Safety:
- No Tailscale enrollment, Kubernetes join, VM creation, cloud/DNS/firewall
  or GitHub Actions changes without separate explicit approval.
- Never request, print, commit or log passwords, access tokens,
  Tailscale auth keys, private SSH keys or kubeconfigs.
- Do not automatically enable auto-start or execute unfamiliar shell
  installers without inspecting them.
- Do not claim a command ran successfully unless you verified the result.
- Reuse standard tools. Do not create a scheduler, broker or lease service.
~~~

[Manual setup](README.md) · [Troubleshooting](docs/INSTALLATION.md)

A fully interactive wizard is planned but not yet implemented.
