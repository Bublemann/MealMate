# Security policy

## Reporting a vulnerability

Please **do not open a public issue**. Report it privately through GitHub: *Security → Report a vulnerability* on this repository (private vulnerability reporting). You will get an answer within a few days.

## Supported versions

Only the newest release line (`release/X.Y`) gets security fixes. Fixes are published as patch releases (`vX.Y.Z`), and self-hosted instances that follow the version line install them automatically at night after verifying the image's signed build provenance.

## Design notes

- MealMate is meant to be reachable **only through Tailscale**. It is not designed to be exposed to the public internet.
- No secrets are stored in this repository. The secret key is generated on the server at setup, and the app refuses to start without one.
- Release images are built only by GitHub Actions from `release/*` branches and carry signed build provenance (Sigstore).
