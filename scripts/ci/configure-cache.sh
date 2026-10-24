#!/usr/bin/env bash
# Sourced inside the staging root after the distro build tools are installed.
: "${CACHE:?Set the persistent build cache}"
mkdir -p "$CACHE"/{sources,pkgs,meson,ccache}
cat >> /etc/makepkg.conf <<EOF
SRCDEST=$CACHE/sources
PKGDEST=$CACHE/pkgs
BUILDENV+=(ccache)
EOF
# makepkg puts its ccache compiler wrappers on PATH, including clang selected
# by Kbuild's LLVM=1. The system config also applies across sudo -u alarm.
cat > /etc/ccache.conf <<EOF
cache_dir = $CACHE/ccache
base_dir = /home/alarm
compiler_check = content
max_size = 4G
compression = true
EOF
export CCACHE_DIR="$CACHE/ccache"
export CCACHE_BASEDIR=/home/alarm
export CCACHE_COMPILERCHECK=content

# Cached installed Meson trees must follow the distro ABI as well as sources.
# Compiler objects remain in ccache, which checks compiler/input contents.
stamp=$(pacman -Q | LC_ALL=C sort | sha256sum | cut -d' ' -f1)
if [[ ! -f "$CACHE/meson.dependencies" || $(cat "$CACHE/meson.dependencies") != "$stamp" ]]; then
    rm -f "$CACHE/meson/"*.tar "$CACHE/meson/"*.tree
fi
printf '%s\n' "$stamp" > "$CACHE/meson.dependencies"
