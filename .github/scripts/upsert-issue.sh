#!/usr/bin/env bash
# Keeps one open issue per automated check (SEC-11). Needs GH_TOKEN (issues: write) and GH_REPO.
#
#   upsert-issue.sh <title> <body-file>   findings: comment on the open issue, or open one
#   upsert-issue.sh <title>               all clear: close the open issue, if there is one
set -euo pipefail

title=$1
body=${2:-}
number=$(gh issue list --state open --search "in:title \"${title}\"" --json number,title \
  --limit 100 | jq -r --arg title "$title" 'map(select(.title == $title)) | first | .number // empty')

if [ -n "$body" ]; then
  if [ -n "$number" ]; then
    gh issue comment "$number" --body-file "$body"
  else
    gh issue create --title "$title" --body-file "$body"
  fi
elif [ -n "$number" ]; then
  gh issue close "$number" --comment "Resolved: the latest run found nothing (${RUN_URL:-})."
fi
