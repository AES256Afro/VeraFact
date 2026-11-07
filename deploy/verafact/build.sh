#!/bin/sh
# Build the VeraFact image from this checkout.
#   deploy/verafact/build.sh [tag]      (default tag: verafact:dev)
# Needs Docker with BuildKit (the Dockerfile uses cache mounts and COPY --exclude).
set -eu

tag="${1:-verafact:dev}"
root="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$root"

# The Dockerfile copies searx/version_frozen.py, which only a git checkout can produce.
python3 -m searx.version freeze

created="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
revision="$(git rev-parse HEAD)"
version="$(git describe --tags --always --dirty 2>/dev/null || git rev-parse --short HEAD)"

DOCKER_BUILDKIT=1 docker build \
  --file container/Dockerfile \
  --tag "$tag" \
  --build-arg "CREATED=$created" \
  --build-arg "VERSION=$version" \
  --build-arg "VCS_URL=https://github.com/AES256Afro/VeraFact" \
  --build-arg "VCS_REVISION=$revision" \
  .

echo "built $tag ($version)"
