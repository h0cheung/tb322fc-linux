# Lenovo Y700 Gen4 Linux

Mainline Linux for the Lenovo Legion Tab Y700 Gen4, based on Qualcomm SM8750
(Snapdragon 8 Elite), device codename **elden**.

This repository provides the kernel configuration, boot-image builder, rootfs
integration, firmware inventory and hardware support status. Kernel development
lives in [tb322fc-linux-kernel](https://github.com/h0cheung/tb322fc-linux-kernel),
forked from [GEEKiDoS/linux](https://github.com/GEEKiDoS/linux/tree/v7.2-elden).
Userspace changes are included as patches against pinned public sources.

## Hardware support

The results below describe the device-tested baseline, refreshed for the current
kernel pin `09e22021`. Bluetooth, suspend (s2idle) and the built-in microphone
have since been verified on hardware; hibernation to disk is untested.

| Component | Status | Notes |
| --- | --- | --- |
| Kernel / UFS | Working | Linux 7.2; ext4 rootfs |
| Display | Working | 24/40/60/90/120/144/165 Hz modes |
| Touch | Working | Novatek NT36536 |
| GPU | Working | Adreno 830 with Mesa Turnip and Zink |
| Wi-Fi | Working | Qualcomm Peach / ath12k |
| Bluetooth | Working | QCA UART firmware load, discovery and pairing |
| Speakers | Working | AW88461; supplied AudioReach topology and UCM |
| Microphone | Working | Built-in analog capture (AMIC1/AMIC4 via the WCD9395) |
| Haptics | Working | Two AW86927-family devices; force-feedback replay |
| Accelerometer / gyro / light | Working | ADSP/SSC; patched sensor services required |
| Cameras | Partial | Front/rear capture works; camera application and tuning work remains |
| Suspend | Working | s2idle on USB-attached sleep; hibernate-to-disk untested |
| Battery / charging | Partial | Charger wake and power/reporting issues remain |

See the [support matrix](docs/hardware.md) for test scope and unverified features.

## Build and use

### Automated Arch Linux Ports images

The **Build Arch Linux Ports images** Actions workflow builds a direct Android
`boot.img` and an Arch Linux Ports Plasma `rootfs.img` from pinned device sources.
It requires a matching firmware bundle; no GRUB or Debian device packages are
used. See the [CI setup and image guide](docs/ci.md) for input preparation,
artifact verification and first boot. This new pipeline still needs a full
firmware-backed build and device validation before its images can be called
tested releases.

### Manual boot image build

1. [Install the build dependencies](docs/build.md#host-dependencies).
2. Fetch the pinned source trees with `python3 scripts/fetch-sources.py`.
3. [Extract and import matching firmware](docs/firmware.md).
4. Build with `bash scripts/build-boot.sh`.
5. Prepare the [rootfs and device services](docs/rootfs.md).
6. Test with `fastboot boot artifacts/boot.img`.

The build produces `boot.img`, `Image`, `sm8750-lenovo-elden.dtb`,
`kernel.config` and `SHA256SUMS` under `artifacts/`. Images and firmware binaries
are not stored in Git. The firmware comes from your own matching stock system;
sensor calibration stays with your device. Rootfs artifacts can be built through
the workflow; no prebuilt tested rootfs release is supplied.

## Project files

| Path | Purpose |
| --- | --- |
| [`sources.json`](sources.json) | Public source URLs, exact commits and expected trees |
| [`patches/`](patches) | Libcamera, hexagonrpc and iio-sensor-proxy changes |
| [`configs/`](configs) | Kernel, BusyBox, command line and initramfs layout |
| [`initramfs/`](initramfs) | Rootfs selection and handoff |
| [`rootfs/`](rootfs) | Audio, sensor and camera integration files |
| [`firmware.json`](firmware.json) | Required firmware paths, sizes and SHA256 hashes |

## Development

- Keep changes scoped to this device and demonstrated dependencies.
- Use devicetree for hardware distinctions; avoid board-specific kernel switches.
- Build verified drivers and their dependencies into the kernel.
- Test with `fastboot boot`; do not flash partitions.
- Preserve a working boot image and device calibration before testing changes.
- Keep generated images, personal logs and device state out of Git.

See [contributing](CONTRIBUTING.md), [boot design](docs/boot.md) and
[validation](docs/validation.md). The repository structure follows the compact
umbrella approach used by [tb321fu-linux](https://github.com/GUF296/tb321fu-linux);
its hardware-specific configurations do not apply to this tablet.
