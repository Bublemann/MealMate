# Agent skills

The agent skills used here are not in this repo. They are personal skills in `~/.claude/skills/` on each machine:

- the 27 skills of [mattpocock/skills](https://github.com/mattpocock/skills);
- `pr-quality-gate`, which `implement-spec`, `implement` and "Finishing a PR without the owner" in `CLAUDE.md` call.

That folder is its own git repo. Its `README.md` says how to set it up on another machine and how to update from upstream.

A session that doesn't have that folder doesn't have these skills. This includes cloud sessions on claude.ai/code and other people's machines.

This repo's conventions live outside the skills: workflow differences in `CLAUDE.md` (Agent skills → Skills), tracker and domain conventions in `docs/agents/*.md`. After an upstream update, compare `docs/agents/*.md` with the templates in upstream's `skills/engineering/setup-matt-pocock-skills/` and carry over changed conventions.

## Names

- `code-review`, `pr` and `prototype` share their names with skills bundled in Claude Code. Whichever `/code-review` opens, `pr-quality-gate` doesn't depend on it: it reads the mattpocock `code-review/SKILL.md` by path. The bundled review keeps its alias `/review`.
- Each skill shows up twice (`/tdd` and `/mattpocock-skills:tdd`) while the claude.ai plugin `mattpocock-skills` is switched on. Keep the plugin off.
