#!/usr/bin/env bash
# Initialize the new pacman release with genuine empty repo-add databases.
set -euo pipefail
REPO=${REPO_NAME:-tb322fc}
TAG=${REPO_TAG:-repository-freedom-v2}
SLUG=${GITHUB_REPOSITORY:-h0cheung/tb322fc-linux}
[[ $TAG == repository-freedom-v2 && $REPO == tb322fc ]] || {
    echo 'Refusing to initialize a legacy or unrelated package repository' >&2; exit 1;
}
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
if gh release view "$TAG" --repo "$SLUG" --json assets,isDraft > "$work/release.json" 2> "$work/error"; then
    python3 - "$work/release.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1]))
required = {'tb322fc.db', 'tb322fc.db.tar.gz', 'tb322fc.files', 'tb322fc.files.tar.gz'}
if r['isDraft'] or not required <= {a['name'] for a in r['assets']}:
    raise SystemExit('Existing repository release is incomplete; inspect it before retrying')
PY
    echo 'Package repository already initialized; leaving its assets intact.'
    exit 0
fi
if ! grep -Eq 'release not found|HTTP 404|Not Found' "$work/error"; then
    cat "$work/error" >&2
    exit 1
fi
repo-add -q "$work/$REPO.db.tar.gz"
for kind in db files; do
    rm "$work/$REPO.$kind"
    cp "$work/$REPO.$kind.tar.gz" "$work/$REPO.$kind"
done
cat > "$work/NOTES.md" <<EOF
Rolling pacman repository for Freedom userspace packages.
Initialized with empty Arch package databases; CI publishes the package set here.
The coordinated kernel, headers, DKMS and kShim packages use versioned v2 releases.

    [$REPO]
    SigLevel = Optional TrustAll
    Server = https://github.com/$SLUG/releases/download/$TAG
EOF
target=()
[[ -z ${GITHUB_SHA:-} ]] || target=(--target "$GITHUB_SHA")
gh release create "$TAG" --repo "$SLUG" "${target[@]}" --draft --prerelease \
    --title 'Freedom package repository' --notes-file "$work/NOTES.md" \
    "$work/$REPO.db" "$work/$REPO.db.tar.gz" "$work/$REPO.files" "$work/$REPO.files.tar.gz"
gh release edit "$TAG" --repo "$SLUG" --draft=false
echo "Initialized $SLUG@$TAG with empty pacman databases."
