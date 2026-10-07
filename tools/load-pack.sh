#!/bin/sh
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$task_root"
# sha256sum refuses modified or missing files; use the independent release checksum too.
if command -v sha256sum >/dev/null 2>&1; then sha256sum --check --strict SHA256SUMS
elif command -v shasum >/dev/null 2>&1; then shasum -a 256 --check SHA256SUMS
else echo 'SHA-256 utility missing.' >&2; exit 2; fi
docker load --input images.tar
while read -r task_service task_reference task_expected; do
    task_actual=$(docker image inspect --format '{{.Id}}' "$task_reference")
    [ "$task_actual" = "$task_expected" ] || { echo 'Image identity mismatch' >&2; exit 1; }
    [ "$task_service" != app ] || docker tag "$task_reference" openblindysir-server:local
done < images.list
echo 'Pack loaded. Read docs/offline-pack.en.md before initialization.'
