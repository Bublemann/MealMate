# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase.

## Before exploring, read these

- **`GLOSSARY.md`** at the repo root: the glossary of domain terms.
- **The decision log**, `docs/requirements.md` §7: read the D-nn rows that touch the area you're about to work in.

## File structure

Single-context repo:

```
/
├── GLOSSARY.md           ← glossary
├── docs/
│   ├── requirements.md   ← requirements with stable IDs; decision log in §7
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

When your output names a domain concept (in an issue title, a refactor proposal, a hypothesis, a test name), use the term as defined in `GLOSSARY.md`. Don't drift to synonyms the glossary explicitly avoids.

If the concept you need isn't in the glossary yet, that's a signal: either you're inventing language the project doesn't use (reconsider) or there's a real gap (note it for `/domain-modeling`).

## Decisions go in the decision log

This repo records decisions as rows of the decision log in `docs/requirements.md` §7. Wherever a skill says ADR or `docs/adr/`, write a row there instead:

- Every non-obvious decision the owner makes gets a §7 row (§8 holds only the answers to the original planning questions), product and UI choices included, even easily reversed ones such as D-35 and D-38.
- Take the next free `D-nn`, checked against the latest `origin/main`: parallel tickets often pick the same number.
- **Decision** states the decision and ends with `(date)`, or `(date, replaces D-nn)` when it replaces an older one, as D-21 shows. **Why** gives the reasons.
- A replaced row is struck through and points to its successor, as D-06 shows.

## Where glossary and decision edits land

The skills edit `GLOSSARY.md` and the decision log inline, as terms and decisions settle. Inside a ticket, they ride on the ticket's branch. A grilling, triage or architecture session outside a ticket first opens a `docs:` ticket, then makes the edits in the session's own worktree on a `docs/<topic>` branch from `origin/main`, created before the first edit, and finishes it like any ticket (as #62 did).

## Flag decision conflicts

If your output contradicts an existing decision, surface it explicitly rather than silently overriding:

> _Contradicts D-22 (tab screens without a visible headline), but worth reopening because…_
