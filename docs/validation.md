# Validation

## Repository and build

- All pinned source revisions have been fetched from their public remotes.
- The three bundled userspace patches reproduce their recorded source trees.
- The pinned wireless-regdb source supplies the exact database/signature hashes.
- The firmware importer verified and staged all 78 required files.
- The audio topology regenerated from the fetched macros matches the expected hash.
- The kernel and a static AArch64 BusyBox were built from fetched source using
  the public configuration and build script.
- The boot image uses the expected embedded DTB and an empty external ramdisk.
- The initramfs contains the current handoff script and no private executable
  payload, experiment identifier or generated diagnostic service.

`scripts/check.py` checks tracked files for private workspace paths, stale
experiment labels, broken local links and malformed source/firmware manifests.
GitHub Actions also verifies public userspace source availability and patch
application. CI does not flash hardware or claim a firmware-equipped boot test.

## Device results

The rebuilt image booted through the cleaned initramfs to the greeter, confirmed
on the tablet. SSH then verified the live configuration and firmware search path.
All 78 firmware files under `/run/firmware` matched their hashes. Rootfs and its
parent disk remained writable; all other enumerated UFS devices were read-only.

The same boot passed 32 display CRC samples, rear/front 16-frame captures,
three seconds of speaker playback with 30 advancing PCM observations, and
87 accelerometer, 88 gyroscope and 17 light measurements. Sensor and desktop
services started automatically. No hardware-controller retry was needed.

The image SHA256 and source/config identities are in [validation.json](../validation.json).
These results used the existing prepared rootfs. They validate the rebuilt boot
image and its handoff, not a fresh distribution installation or every userspace
build recipe.

The [support matrix](hardware.md) includes earlier functional driver tests and
their limits. No new suspend, Bluetooth discovery or charging success is
claimed for the public image.
