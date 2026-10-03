# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase.

## Before exploring, read these

- **`CONTEXT.md`** at the repo root: the glossary of domain terms.
- **`docs/adr/`**: read ADRs that touch the area you're about to work in.

If any of these files don't exist, **proceed silently**. Don't flag their absence; don't suggest creating them upfront. The `/domain-modeling` skill (reached via `/grill-with-docs` and `/improve-codebase-architecture`) creates them lazily when terms or decisions actually get resolved.

## File structure

Single-context repo:

```
/
├── CONTEXT.md            ← glossary
├── docs/
│   ├── adr/              ← created when the first ADR is written
│   ├── requirements.md
│   ├── plan.md
│   └── operations.md
├── backend/
├── frontend/
└── deploy/
```

## Project docs

- `docs/requirements.md`: what MealMate must do. Every requirement has a stable ID (e.g. `LIST-04`); cite these IDs in tickets and PRs.
- `docs/plan.md`: architecture, data model and milestones.
- `CONTRIBUTING.md`: branch names, Conventional Commit PR titles, squash merge.

## Use the glossary's vocabulary

When your output names a domain concept (in an issue title, a refactor proposal, a hypothesis, a test name), use the term as defined in `CONTEXT.md`. Don't drift to synonyms the glossary explicitly avoids.

If the concept you need isn't in the glossary yet, that's a signal: either you're inventing language the project doesn't use (reconsider) or there's a real gap (note it for `/domain-modeling`).

## Flag ADR conflicts

If your output contradicts an existing ADR, surface it explicitly rather than silently overriding:

> _Contradicts ADR-0003 (…), but worth reopening because…_
