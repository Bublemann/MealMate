#!/usr/bin/env bash
# Computes the next release of a version line from the existing tags (plan § 10.2).
#
#   next-version.sh <X.Y> <final|patch|alpha|beta|rc> <commit>
#
# final: X.Y.0 (also after its pre-releases) · patch: X.Y.(n+1) after a final ·
# alpha|beta|rc: X.Y.0-<kind>.(n+1), never after X.Y.0 or after a later pre-release stage.
# Prints key=value lines for $GITHUB_OUTPUT: version, tag, prerelease, latest (highest final
# overall) and previous (the tag the release notes start after; empty for the first release).
set -euo pipefail

fail() {
  echo "::error::$*" >&2
  exit 1
}

[ $# -eq 3 ] || fail "usage: next-version.sh <X.Y> <final|patch|alpha|beta|rc> <commit>"
line=$1 kind=$2 commit=$3
[[ $line =~ ^([0-9]+)\.([0-9]+)$ ]] || fail "version line must look like X.Y, got '$line'"
major=${BASH_REMATCH[1]} minor=${BASH_REMATCH[2]}

final_re="^v${major}\.${minor}\.([0-9]+)$"
pre_re="^v${major}\.${minor}\.0-(alpha|beta|rc)\.([0-9]+)$"
stages=(alpha beta rc)
latest_patch=-1
declare -A latest_pre=([alpha]=0 [beta]=0 [rc]=0)
while read -r tag; do
  if [[ $tag =~ $final_re ]]; then
    if ((BASH_REMATCH[1] > latest_patch)); then latest_patch=${BASH_REMATCH[1]}; fi
  elif [[ $tag =~ $pre_re ]]; then
    stage=${BASH_REMATCH[1]} number=${BASH_REMATCH[2]}
    if ((number > latest_pre[$stage])); then latest_pre[$stage]=$number; fi
  fi
done < <(git tag --list "v${major}.${minor}.*")

case $kind in
  final)
    ((latest_patch < 0)) || fail "v${line}.0 already exists; publish a patch instead"
    version="${line}.0"
    ;;
  patch)
    ((latest_patch >= 0)) || fail "v${line}.0 does not exist yet; publish the final release first"
    version="${line}.$((latest_patch + 1))"
    ;;
  alpha | beta | rc)
    ((latest_patch < 0)) || fail "v${line}.0 is released; pre-releases of ${line} are closed"
    later=0
    for stage in "${stages[@]}"; do
      if ((later && latest_pre[$stage] > 0)); then
        fail "v${line}.0-${stage}.${latest_pre[$stage]} exists; a new ${kind} would sort before it"
      fi
      if [ "$stage" = "$kind" ]; then later=1; fi
    done
    version="${line}.0-${kind}.$((latest_pre[$kind] + 1))"
    ;;
  *)
    fail "kind must be final, patch, alpha, beta or rc, got '$kind'"
    ;;
esac

tag="v${version}"
if git rev-parse --quiet --verify "refs/tags/${tag}" >/dev/null; then
  fail "tag ${tag} already exists"
fi

if [[ $kind == alpha || $kind == beta || $kind == rc ]]; then
  prerelease=true
  latest=false
  # Notes cover everything since the previous tag of any kind.
  previous=$(git describe --tags --abbrev=0 --match 'v[0-9]*' "$commit" 2>/dev/null || true)
else
  prerelease=false
  highest=$({
    git tag --list 'v[0-9]*' | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' || true
    echo "$tag"
  } | sort -V | tail -n 1)
  latest=$([ "$highest" = "$tag" ] && echo true || echo false)
  # Notes of a final or patch release cover everything since the previous final release.
  previous=$(git describe --tags --abbrev=0 --match 'v[0-9]*' --exclude 'v*-*' "$commit" \
    2>/dev/null || true)
fi

echo "version=${version}"
echo "tag=${tag}"
echo "prerelease=${prerelease}"
echo "latest=${latest}"
echo "previous=${previous}"
