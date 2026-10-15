# Agent skills

`.claude/skills/` holds the 27 skills of the `mattpocock-skills` plugin, copied unchanged from [mattpocock/skills](https://github.com/mattpocock/skills) at commit `49dd158d1076134a641b33efb035946536778336` (2026-10-09, plugin 1.3.1). Upstream's MIT licence is in `.claude/skills/LICENSE`. Claude Code loads them as project skills in every session on this repo: the main checkout, worktrees and cloud sessions.

The copies stay unchanged, so an update stays a plain copy. This repo's conventions live outside them: workflow differences in `CLAUDE.md` (Agent skills → Skills), tracker and domain conventions in `docs/agents/*.md`.

## Names

- `code-review`, `pr` and `prototype` share their names with skills bundled in Claude Code. A project skill replaces the bundled one of the same name ([skills docs](https://code.claude.com/docs/en/skills)), so `/code-review` here is the two-axis Standards and Spec review. The bundled review keeps its alias `/review`.
- Each skill shows up twice (`/tdd` and `/mattpocock-skills:tdd`) while the claude.ai plugin `mattpocock-skills` is switched on. Keep the plugin off.

## Updating

1. Clone upstream and read its `CHANGELOG.md` since the commit above, looking for renamed or removed skills and changed conventions (like the `CONTEXT.md` → `GLOSSARY.md` rename, [mattpocock/skills#1120](https://github.com/mattpocock/skills/pull/1120)).
2. Copy every folder listed in upstream's `.claude-plugin/plugin.json` to `.claude/skills/<folder name>/`, replacing the old copy. Delete the folders of skills upstream dropped, and copy upstream's `LICENSE` again.
3. Compare `docs/agents/*.md` with the templates in upstream's `skills/engineering/setup-matt-pocock-skills/` and carry over changed conventions. Re-check the list in `CLAUDE.md` (Agent skills → Skills) against every skill whose workflow changed.
4. Update the first paragraph: commit, its date, plugin version and number of skills.

Done when `.claude/skills/` holds exactly the plugin's skills, file for file, plus `LICENSE`.
