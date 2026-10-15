# Agent skills

`.claude/skills/` holds the 27 skills of the `mattpocock-skills` plugin, copied unchanged from [mattpocock/skills](https://github.com/mattpocock/skills) at commit `49dd158d1076134a641b33efb035946536778336` (2026-10-09, plugin 1.3.1). Upstream's MIT licence is in `.claude/skills/LICENSE`. Claude Code loads them as project skills in every session on this repo: the main checkout, worktrees and cloud sessions.

The copies stay unchanged. This repo's conventions go into `docs/agents/*.md` instead, which the skills read through `CLAUDE.md`, so an update stays a plain copy.

## Names

- `code-review` replaces Claude Code's bundled `/code-review`. The bundled review is still reachable as `/review`.
- Each skill shows up twice (`/tdd` and `/mattpocock-skills:tdd`) while the claude.ai plugin `mattpocock-skills` is switched on. Keep the plugin off.

## Updating

1. Clone upstream and read its `CHANGELOG.md` since the commit above, looking for renamed or removed skills and changed conventions (like the `CONTEXT.md` → `GLOSSARY.md` rename, [mattpocock/skills#1120](https://github.com/mattpocock/skills/pull/1120)).
2. Copy every folder listed in upstream's `.claude-plugin/plugin.json` to `.claude/skills/<folder name>/`, replacing the old copy. Delete the folders of skills upstream dropped, and copy upstream's `LICENSE` again.
3. Compare `docs/agents/*.md` with the templates in upstream's `skills/engineering/setup-matt-pocock-skills/` and carry over changed conventions.
4. Put the new commit above.

Done when `.claude/skills/` holds exactly the plugin's skills, file for file, plus `LICENSE`.
