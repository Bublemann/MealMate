# MealMate

## Agent skills

### Issue tracker

GitHub Issues in `Bublemann/MealMate`, used through the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

The five default labels: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.

## Tickets and pull requests

- One ticket, one branch, one PR. Branch from `main`, named as in `CONTRIBUTING.md` (`feature/`, `fix/`, `docs/`, `chore/`).
- Start a ticket only when every ticket that blocks it is closed, i.e. its PR is merged. Never branch from another ticket's unmerged branch: PRs are squash-merged, so stacked branches would need a rebase after every merge.
- The PR body says `Closes #<ticket>`, lists each blocker as `Blocked by #<n>`, and fills in the requirement IDs as the PR template asks.

### Finishing a PR without the owner

The owner does not review PRs. Take each PR to merged yourself:

1. Wait until every required check passes (`gh pr checks <n> --watch`). If one fails, fix it on the branch and wait again.
2. Review the whole PR diff against the ticket's acceptance criteria and this repo's rules (`CONTRIBUTING.md`, `frontend/README.md`), using the `code-review` skill. Fix what you find, push, and go back to step 1.
3. Post the review result as a PR comment. GitHub doesn't let you approve your own PR, and `main` requires no approval.
4. Merge with `gh pr merge <n> --squash --delete-branch` once the checks are green, the review found nothing, and every blocker is merged. The PR title (a Conventional Commit) becomes the changelog entry.

Don't merge. Instead, leave the PR open, say why in a PR comment, and add `ready-for-human` to the ticket when:

- a required check keeps failing for a reason you can't fix within the ticket, or fails only sometimes;
- the review finds a bug or gap you can't close within the ticket's scope;
- the change reaches beyond the ticket: a migration that drops or rewrites existing data, login or security code (SEC-*), CI or release workflows, or `deploy/`;
- the ticket contradicts `docs/requirements.md` or `CONTEXT.md`.

Merging to `main` deploys nothing: images are built only from release tags. What only an iPhone can show (keyboard, see-through tab bar) the owner checks with the QA-06 list before a release.
