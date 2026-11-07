#!/bin/sh
# Write searx/version_frozen.py from git, the way `python -m searx.version freeze`
# would, without importing the app (which needs its dependencies installed).
# Prints the Docker tag on stdout. Run from the repository root.
set -eu

date_hash="$(git show -s --date='format:%Y.%m.%d' --format='%cd+%h' | sed 's/\.0/./g')"
version="$date_hash"
git diff --quiet -- . ':!searx/settings.yml' ':!utils/brand.env' || version="$version+dirty"
docker_tag="$(printf '%s' "$date_hash" | tr '+' '-')"
branch="${GITHUB_REF_NAME:-$(git rev-parse --abbrev-ref HEAD)}"

cat > searx/version_frozen.py <<PY
# SPDX-License-Identifier: AGPL-3.0-or-later
# pylint: disable=missing-module-docstring,invalid-name
VERSION_STRING = "$version"
VERSION_TAG = "$date_hash"
DOCKER_TAG = "$docker_tag"
GIT_URL = "https://github.com/AES256Afro/VeraFact"
GIT_BRANCH = "$branch"
PY

printf '%s\n' "$docker_tag"
