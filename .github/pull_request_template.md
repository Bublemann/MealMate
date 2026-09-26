## Summary

<!-- What changes and why. The PR title is a Conventional Commit (`feat: …`, `fix: …`); it
becomes the changelog entry when the PR is squash-merged. -->

## Requirements

<!-- IDs from docs/requirements.md this PR implements or touches, e.g. LIST-04, SEC-06. -->

## Checks

- [ ] Tests cover the change (backend API/unit, Vitest, or E2E as fits)
- [ ] `make lint` and `make test` pass locally
- [ ] API changed: `make openapi` run and `frontend/src/api/generated/` committed
- [ ] New UI strings in both `de.json` and `en.json`; new test IDs in `src/testIds.ts`
- [ ] Database changed: migration added and reviewed
- [ ] No secrets, personal data or generated files beyond the above
