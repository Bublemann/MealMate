# MealMate

## Agent skills

### Skills

The mattpocock skills, plus `pr-quality-gate`, are personal skills in `~/.claude/skills/`, not part of this repo. See `docs/agents/skills.md`. Where a skill's workflow differs from this file, this file wins:

- `implement-spec`: `main` is the integration branch, so steps 3, 5, 7 and 8 (integration branch, merger, final review, draft PR) give way to "Tickets and pull requests" below: each ticket gets its own worktree, branch from `origin/main` and PR, and starts once its blockers are merged. The PR of the last open ticket also says `Closes #<spec>`.
- `pr`: the PR body has exactly the sections of `.github/pull_request_template.md` (Summary, Requirements, Checks). The skill's diagram, evidence and merge danger go under Summary.
- `prototype`: the prototype lives in the session's own worktree and stays local. Before the worktree goes, post on the issue: the verdict, the question it settled, the key code (in a collapsed `<details>` block) and, for a UI, a description of what it showed.
- `teach`: when started here, ask for a folder outside this repo and keep the teaching workspace there.

### Issue tracker

GitHub Issues in `Bublemann/MealMate`, used through the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

The five default labels: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `GLOSSARY.md` at the repo root. Where the skills say ADR, write a D-nn row in the decision log, `docs/requirements.md` §7. See `docs/agents/domain.md`.

## Tickets and pull requests

- One ticket, one branch, one PR. Branch from `main`, named as in `CONTRIBUTING.md` (`feature/`, `fix/`, `docs/`, `chore/`).
- Start a ticket only when every ticket that blocks it is closed, i.e. its PR is merged. Assign it to yourself when you start (`gh issue edit <n> --add-assignee @me`). Never branch from another ticket's unmerged branch: PRs are squash-merged, so stacked branches would need a rebase after every merge.
- The PR body says `Closes #<ticket>`, lists each blocker as `Blocked by #<n>`, and fills in the requirement IDs as the PR template asks.

### Finishing a PR

Never merge a PR, never enable auto-merge, and never change anyone else's PR. The owner merges. Your job is to bring your own ticket PR to a state where the owner can merge it without reviewing it:

1. Wait until every required check passes (`gh pr checks <n> --watch`). If one fails, fix it on the branch and wait again.
2. Call the Skill tool with `pr-quality-gate` on the PR, with `origin/main` (after `git fetch`) as the base and the ticket as the spec. Its Standards reviewer must get this repo's rules (`CONTRIBUTING.md`, `frontend/README.md`). The gate runs the checks, reviews, fixes and pushes what it finds, and posts its report as a PR comment. If it pushed fixes, go back to step 1.
3. Tell the owner the gate's result, nothing more:
   - can be merged: one sentence saying so, with the PR link;
   - otherwise: one line saying it can't be merged yet, then each problem as one short bullet.

It can't be merged, and on the ticket you replace `ready-for-agent` with `ready-for-human` (`gh issue edit <n> --remove-label ready-for-agent --add-label ready-for-human`), when:

- a required check keeps failing for a reason you can't fix within the ticket, or fails only sometimes;
- the gate's verdict is BLOCKED, or it leaves an open question the ticket doesn't answer;
- the change reaches beyond the ticket: a migration that drops or rewrites existing data, login or security code (SEC-*), CI or release workflows, or `deploy/`;
- the ticket contradicts `docs/requirements.md` or `GLOSSARY.md`.

PRs are squash-merged with the PR title and number as the subject (`<PR title> (#<n>)`), because the squash commit's subject becomes the changelog entry. So keep the PR title changelog-ready.

Merging to `main` deploys nothing: images are built only from release tags. What only an iPhone can show (keyboard, see-through tab bar) the owner checks on a real iPhone before a release (QA-06).
