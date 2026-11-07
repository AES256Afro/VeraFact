#!/bin/sh
# Build the VeraFact image from this checkout.
#   deploy/verafact/build.sh [tag]      (default tag: verafact:dev)
# Needs Docker with BuildKit (the Dockerfile uses cache mounts and COPY --exclude).
set -eu

tag="${1:-verafact:dev}"
root="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$root"

# The Dockerfile copies searx/version_frozen.py. Upstream writes it with
# `python -m searx.version freeze`, which imports the app and so needs its
# dependencies installed; derive the same strings from git here instead.
date_hash="$(git show -s --date='format:%Y.%m.%d' --format='%cd+%h' | sed 's/\.0/./g')"
version="$date_hash"
git diff --quiet -- . ':!searx/settings.yml' ':!utils/brand.env' || version="$version+dirty"
docker_tag="$(printf '%s' "$date_hash" | tr '+' '-')"
branch="$(git rev-parse --abbrev-ref HEAD)"
cat > searx/version_frozen.py <<PY
# SPDX-License-Identifier: AGPL-3.0-or-later
# pylint: disable=missing-module-docstring,invalid-name
VERSION_STRING = "$version"
VERSION_TAG = "$date_hash"
DOCKER_TAG = "$docker_tag"
GIT_URL = "https://github.com/AES256Afro/VeraFact"
GIT_BRANCH = "$branch"
PY

created="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
revision="$(git rev-parse HEAD)"

DOCKER_BUILDKIT=1 docker build \
  --file container/Dockerfile \
  --tag "$tag" \
  --build-arg "CREATED=$created" \
  --build-arg "VERSION=$version" \
  --build-arg "VCS_URL=https://github.com/AES256Afro/VeraFact" \
  --build-arg "VCS_REVISION=$revision" \
  .

echo "built $tag ($version)"
