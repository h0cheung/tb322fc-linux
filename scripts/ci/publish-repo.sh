#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Publish the packages built by build-rootfs.sh as a pacman repository on a
# rolling GitHub pre-release (tag: repository), laid out the way pacman expects:
# <repo>.db / <repo>.files plus the package tarballs, all under one release URL.
set -euo pipefail
cd -- "$(dirname -- "$0")/../.."

REPO=${REPO_NAME:-tb322fc}
TAG=${REPO_TAG:-repository}
SLUG=${GITHUB_REPOSITORY:-h0cheung/tb322fc-linux}
PKGS=${REPO_PKGS:-build/rootfs-cache/pkgs}

[[ -d "$PKGS" ]] || { echo "publish-repo: no packages at $PKGS (run build-rootfs.sh first)" >&2; exit 1; }
shopt -s nullglob
pkgs=("$PKGS"/*.pkg.tar.*)
shopt -u nullglob
(( ${#pkgs[@]} )) || { echo "publish-repo: no .pkg.tar.* files under $PKGS" >&2; exit 1; }

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

# GitHub rewrites release-asset names (":" -> "."), but pacman builds the
# download URL from the db's %FILENAME%. Rename to the same safe charset first
# so the db and the served asset agree; the package contents are untouched.
for src in "${pkgs[@]}"; do
    base=$(basename "$src")
    cp -f "$src" "$work/${base//[!A-Za-z0-9._-]/.}"
done

cd "$work"
repo-add -q "$REPO.db.tar.gz" ./*.pkg.tar.* >/dev/null
# pacman fetches <repo>.db; GitHub cannot serve symlinks, so ship real copies
# (repo-add leaves <repo>.db as a symlink to <repo>.db.tar.gz).
rm -f "$REPO.db" "$REPO.files"
cp -f "$REPO.db.tar.gz" "$REPO.db"
cp -f "$REPO.files.tar.gz" "$REPO.files"

declare -A keep=()
for f in "$REPO.db" "$REPO.db.tar.gz" "$REPO.files" "$REPO.files.tar.gz" ./*.pkg.tar.*; do
    keep[$(basename "$f")]=1
done

if ! gh release view "$TAG" --repo "$SLUG" >/dev/null 2>&1; then
    cat > "$work/NOTES.md" <<EOF
Rolling pacman repository of the packages this project builds.

    [$REPO]
    SigLevel = Optional TrustAll
    Server = https://github.com/$SLUG/releases/download/$TAG
EOF
    gh release create "$TAG" --repo "$SLUG" --prerelease \
        --title "Package repository" --notes-file "$work/NOTES.md"
fi

gh release upload "$TAG" --repo "$SLUG" --clobber "${!keep[@]}"

# Drop superseded assets (for example yesterday's -git mesa build) so the
# release only ever holds the current package set.
mapfile -t existing < <(gh release view "$TAG" --repo "$SLUG" --json assets -q '.assets[].name')
for name in "${existing[@]}"; do
    [[ -n "$name" && -z "${keep[$name]:-}" ]] || continue
    gh release delete-asset "$TAG" "$name" --repo "$SLUG" --yes
done

echo "publish-repo: published ${#pkgs[@]} packages to $SLUG@$TAG"
