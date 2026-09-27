#!/usr/bin/env bash
# Prints the image tags a release is published under (plan § 10.2), one per line. The tags that
# exist in the repository are read from stdin, one name per line.
#
#   image-tags.sh <version> <X.Y> <prerelease: true|false> < tag-names
#
# The version itself is always published. The moving tags only go to the newest release:
# - a final release gets X.Y if it is the highest final of its line, and latest if it is the
#   highest final overall;
# - a pre-release gets X.Y-pre if it is the highest pre-release of its line.
# The build-image workflow runs this right before pushing, so a slow or re-run build of an older
# release can never move these tags back (the Pi follows X.Y, plan § 11.5).
set -euo pipefail

fail() {
  echo "::error::$*" >&2
  exit 1
}

[ $# -eq 3 ] || fail "usage: image-tags.sh <version> <X.Y> <true|false> < tag-names"
version=$1 line=$2 prerelease=$3
[[ $line =~ ^[0-9]+\.[0-9]+$ ]] || fail "version line must look like X.Y, got '$line'"
[[ $prerelease =~ ^(true|false)$ ]] || fail "prerelease must be true or false, got '$prerelease'"
tags=$(cat)
line_re=${line//./\\.}

# The highest of the tags matching an extended regex (empty if none does).
highest() {
  { grep -E "$1" <<<"$tags" || true; } | sort -V | tail -n 1
}

echo "$version"
if [ "$prerelease" = true ]; then
  if [ "$(highest "^v${line_re}\.[0-9]+-(alpha|beta|rc)\.[0-9]+$")" = "v${version}" ]; then
    echo "${line}-pre"
  fi
else
  if [ "$(highest "^v${line_re}\.[0-9]+$")" = "v${version}" ]; then
    echo "$line"
  fi
  if [ "$(highest '^v[0-9]+\.[0-9]+\.[0-9]+$')" = "v${version}" ]; then
    echo latest
  fi
fi
