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
- Start a ticket only when every ticket that blocks it is closed, i.e. its PR is merged. Assign it to yourself when you start (`gh issue edit <n> --add-assignee @me`). Never branch from another ticket's unmerged branch: PRs are squash-merged, so stacked branches would need a rebase after every merge.
- The PR body says `Closes #<ticket>`, lists each blocker as `Blocked by #<n>`, and fills in the requirement IDs as the PR template asks.

### Finishing a PR without the owner

The owner does not review PRs. Take your own ticket PR (from a `feature/`, `fix/`, `docs/` or `chore/` branch into `main`) to merged yourself. Never merge, squash or change anyone else's PR: release sync and back-merge PRs, `hotfix/` PRs and Dependabot PRs stay with the owner.

1. Wait until every required check passes (`gh pr checks <n> --watch`). If one fails, fix it on the branch and wait again.
2. Review the whole PR diff against the ticket's acceptance criteria and this repo's rules (`CONTRIBUTING.md`, `frontend/README.md`), using the `mattpocock-skills:code-review` skill with the ticket as the spec. Fix what you find, push, and go back to step 1.
3. Post the review result as a PR comment. GitHub doesn't let you approve your own PR, and `main` requires no approval.
4. Merge with `gh pr merge <n> --squash --delete-branch --subject "<PR title> (#<n>)"` once the checks are green, the review found nothing, and every blocker is merged. Pass `--subject`: for a one-commit PR GitHub would otherwise take the commit's subject, and the squash commit's subject becomes the changelog entry.

Don't merge. Instead, leave the PR open, say why in a PR comment, and on the ticket replace `ready-for-agent` with `ready-for-human` (`gh issue edit <n> --remove-label ready-for-agent --add-label ready-for-human`) when:

- a required check keeps failing for a reason you can't fix within the ticket, or fails only sometimes;
- the review finds a bug or gap you can't close within the ticket's scope;
- the change reaches beyond the ticket: a migration that drops or rewrites existing data, login or security code (SEC-*), CI or release workflows, or `deploy/`;
- the ticket contradicts `docs/requirements.md` or `CONTEXT.md`.

Merging to `main` deploys nothing: images are built only from release tags. What only an iPhone can show (keyboard, see-through tab bar) the owner checks on a real iPhone before a release (QA-06).
