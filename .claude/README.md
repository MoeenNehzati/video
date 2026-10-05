# Claude discovery

Canonical instructions are in [AGENTS.md](../AGENTS.md); canonical skills are in
[.agents/skills](../.agents/skills). `CLAUDE.md` imports `AGENTS.md` using Claude's
native `@` syntax, so instruction loading does not depend on Git symlink support.
`.claude/skills` remains a discovery symlink; when unavailable, the agent reads the
selected skill directly from its canonical location.

Execute scripts directly with the repo environment's Python; execution does not
rely on the skill discovery symlink. Follow AGENTS.md for startup configuration and
per-command environment loading. No shared Claude settings or shell launchers are required.
Machine-specific settings may be recreated locally in ignored `settings.json`.
