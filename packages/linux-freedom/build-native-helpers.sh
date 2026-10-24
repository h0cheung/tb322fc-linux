#!/usr/bin/env bash
# Build host helpers in the architecture where the headers will be used.
set -euo pipefail
builddir=$(realpath "$1")
[[ $(uname -m) == aarch64 ]] || { echo 'Build these helpers on AArch64.' >&2; exit 1; }
cd "$builddir"
gcc -O2 -I scripts/include scripts/basic/fixdep.c -o scripts/basic/fixdep
gcc -O2 -std=gnu11 -I scripts/include -I scripts/mod \
  scripts/mod/modpost.c scripts/mod/file2alias.c scripts/mod/sumversion.c \
  scripts/mod/symsearch.c -o scripts/mod/modpost
gcc -O2 scripts/mod/mk_elfconfig.c -o scripts/mod/mk_elfconfig
gcc -O2 -I tools/include/uapi scripts/sign-file.c -o scripts/sign-file -lcrypto
# Host libc can use newer UAPI integer types than this kernel's tools copy.
# Load the host type definitions before the tools' private include paths.
make -C tools/bpf/resolve_btfids -j4 HOSTCC=gcc HOSTLD=ld HOSTAR=ar \
  HOSTCFLAGS='-include /usr/include/linux/types.h'
for program in scripts/basic/fixdep scripts/mod/modpost scripts/mod/mk_elfconfig \
               scripts/sign-file tools/bpf/resolve_btfids/resolve_btfids; do
  file "$program" | grep -q 'ARM aarch64'
  strip --strip-unneeded "$program"
done
# Source and libraries used only to build resolve_btfids are not needed by DKMS.
install -Dm755 tools/bpf/resolve_btfids/resolve_btfids .native/resolve_btfids
rm -r tools
install -Dm755 .native/resolve_btfids tools/bpf/resolve_btfids/resolve_btfids
rm -r .native
find scripts -type f \( -name '*.o' -o -name '*.cmd' -o -name '*.d' \) -delete
