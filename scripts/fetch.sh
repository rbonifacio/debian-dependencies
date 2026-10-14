#!/bin/sh
# Baixa os índices Packages e Sources de uma release do Debian.
# Uso: scripts/fetch.sh [suite] [arch]   (padrão: trixie amd64)
set -eu
SUITE=${1:-trixie}
ARCH=${2:-amd64}
MIRROR=https://deb.debian.org/debian
DEST=data/$SUITE
mkdir -p "$DEST"
curl -sSf -o "$DEST/Packages.xz" "$MIRROR/dists/$SUITE/main/binary-$ARCH/Packages.xz"
curl -sSf -o "$DEST/Sources.xz" "$MIRROR/dists/$SUITE/main/source/Sources.xz"
xz -dkf "$DEST/Packages.xz" "$DEST/Sources.xz"
echo "índices salvos em $DEST"
