# Claude discovery

Canonical instructions are in [AGENTS.md](../AGENTS.md); canonical skills are in
[.agents/skills](../.agents/skills). `CLAUDE.md` and `.claude/skills` are discovery
symlinks. A host that does not materialize Git symlinks must use those canonical
locations or configure discovery locally.

Execute scripts directly with the repo environment's Python; execution does not
rely on either symlink. No shared Claude settings or shell launchers are required.
Machine-specific settings may be recreated locally in ignored `settings.json`.
