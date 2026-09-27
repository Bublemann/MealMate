#!/usr/bin/env bash
# Checks that a pushed tag may become an image and describes it (plan §§ 10.1-10.2).
#
#   tag-info.sh <tag>
#
# The tag must be vX.Y.Z[-alpha.N|-beta.N|-rc.N] and its commit must be on origin/release/X.Y
# (tags exist only on release branches). Prints key=value lines for $GITHUB_OUTPUT: version,
# line (X.Y), prerelease and commit. The moving image tags are decided later, right before they
# are pushed (image-tags.sh).
set -euo pipefail

fail() {
  echo "::error::$*" >&2
  exit 1
}

[ $# -eq 1 ] || fail "usage: tag-info.sh <tag>"
tag=$1
[[ $tag =~ ^v(([0-9]+\.[0-9]+)\.[0-9]+)(-(alpha|beta|rc)\.[0-9]+)?$ ]] ||
  fail "'$tag' is not a release tag (vX.Y.Z or vX.Y.Z-alpha|beta|rc.N)"
version=${BASH_REMATCH[1]}${BASH_REMATCH[3]}
line=${BASH_REMATCH[2]}
prerelease=$([ -n "${BASH_REMATCH[3]}" ] && echo true || echo false)

commit=$(git rev-parse --verify "refs/tags/${tag}^{commit}")
branch="refs/remotes/origin/release/${line}"
git rev-parse --quiet --verify "$branch" >/dev/null || fail "branch release/${line} does not exist"
git merge-base --is-ancestor "$commit" "$branch" || fail "${tag} is not on release/${line}"

echo "version=${version}"
echo "line=${line}"
echo "prerelease=${prerelease}"
echo "commit=${commit}"
