#!/bin/sh
# Build image backend, tag versi, lalu simpan semua image ke satu arsip untuk
# server tanpa akses registry.
#
#   scripts/build_release.sh v1.0.0
#
# Hasil: cert-autofill-images-v1.0.0.tar.gz
# Di server: docker load < arsip, lalu jalankan compose produksi.
set -eu

VERSION=${1:-}
if [ -z "$VERSION" ]; then
    echo "usage: scripts/build_release.sh <versi, mis. v1.0.0>" >&2
    exit 2
fi

IMAGE="cert-autofill-backend:${VERSION}"
ARCHIVE="cert-autofill-images-${VERSION}.tar.gz"

docker compose build backend
docker tag certificate-autofill-dev-backend:latest "$IMAGE"

# Image runtime wajib. Caddy hanya dipakai bila docker-compose.proxy.yml aktif.
set -- \
    "$IMAGE" \
    postgres:17-alpine \
    prom/prometheus:v2.54.1 \
    grafana/grafana:11.2.0 \
    grafana/loki:2.9.8 \
    grafana/promtail:2.9.8 \
    caddy:2-alpine

for image in "$@"; do
    if ! docker image inspect "$image" >/dev/null 2>&1; then
        docker pull "$image"
    fi
done

docker save "$@" | gzip > "$ARCHIVE"

echo "Arsip image: $ARCHIVE"
echo "Deploy di server:"
echo "  docker load < $ARCHIVE"
echo "  BACKEND_IMAGE=$IMAGE docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d"
