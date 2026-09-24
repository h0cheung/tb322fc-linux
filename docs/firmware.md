# Firmware

`firmware.json` lists the 78 files from the original validated hardware configuration.
Paths are relative to the Linux firmware directory. Firmware must be available
before rootfs mounts because several drivers are built into the kernel.

## Newer kernel Bluetooth firmware

The current kernel pin `ba28ec16f01f59ba8f5099e8af9e95b061fc5c78` adds WCN7861
peripheral setup. A cold Bluetooth initialization additionally requests:

- `qca/brhperifw20.tlv`
- `qca/brhperinv20.bin`
- `qca/tmel_peach_20.elf`

These files and their verified hashes are not supplied by the original umbrella
repository or its 78-file manifest. The existing bundle remains sufficient for
the declared build inputs, but it must not be described as complete Bluetooth
firmware for the new kernel. Missing peripheral firmware can make Bluetooth
initialization fail; it is not a dependency of the rootfs handoff.

Once matching stock files are available, record their real sizes and SHA256s in
`firmware.json`, add their paths to `configs/initramfs.list`, and regenerate the
firmware bundle. The CI rootfs installer already follows the manifest. Do not
invent hashes or substitute another board's NVM to satisfy the build.

## Stock inputs

Extract matching firmware from your own tablet's stock Android system or its
matching firmware image. With a rooted Android system, `adb pull` can read the
following directories into `inputs/stock/`; some files require a root-capable
ADB setup. Keep the extracted hierarchy and do not write Android partitions.

| Stock location | Contents needed |
| --- | --- |
| `/vendor/firmware` | Touch image, `haptic_ram.bin`, `aw882xx_acf.bin`, Bluetooth firmware |
| `/vendor/firmware_mnt/image` | ADSP MDT/segments, GPU firmware, Peach firmware and board data |
| `/odm/etc/wifi/peach` | Additional board-data candidates |
| Pinned `sources/wireless-regdb` checkout | `regulatory.db` and `regulatory.db.p7s` |

The importer locates files by size and SHA256, not by guessed board IDs or
Android filenames. Supply all extracted directories and the generated topology:

```sh
python3 scripts/import-firmware.py inputs/stock build/audio sources/wireless-regdb
```

It prints every missing destination if the supplied stock release does not
contain a matching file, and imports nothing until the full set is available.
The matching stock files are required external inputs, not bundled binaries.
There is no public download URL asserted for device-specific firmware.

## Linux layout

| Function | Paths under `inputs/firmware/` |
| --- | --- |
| Touch | `novatek_ts_csot_3k_fw.bin` |
| GPU | `qcom/gen80000_gmu.bin`, `qcom/gen80000_sqe.fw`, `qcom/gen80000_aqe.fw`, `qcom/sm8750/gen80000_zap.mbn` |
| Wi-Fi | `ath12k/PEACH/hw2.0/`: `amss.bin`, `tmel.bin`, `board.bin`, `regdb.bin`, `m3.bin`, `aux_ucode.bin`, `qdss_trace_config.bin` |
| Regulatory database | `regulatory.db`, `regulatory.db.p7s` |
| Bluetooth | `qca/brhbtfw20.tlv`, `qca/brhbtnv20.bin` |
| ADSP | `qcom/sm8750/adsp.mdt`, `adsp.bNN`, `adsp_dtb.mdt`, `adsp_dtb.bNN`; exact segment list in the manifest |
| Haptics | `awinic/y700-gen4-haptic.bin` (stock `haptic_ram.bin`) |
| Speakers | `awinic/y700-gen4-speakers.bin` (stock `aw882xx_acf.bin`) |
| Audio topology | `qcom/sm8750/Lenovo-Y700-Gen4-tplg.bin`, generated from the supplied source |

Touch firmware is also compiled directly into the kernel. The initramfs keeps
its firmware in `/run/firmware` across `switch_root`, so asynchronous requests
do not depend on a private rootfs firmware payload. Installing matching files
under rootfs `/usr/lib/firmware` is useful for other boot configurations.

CDSP is disabled and does not need firmware for this configuration. Camera
tuning and sensor registry/calibration are separate userspace requirements;
see [rootfs setup](rootfs.md). Do not distribute another tablet's calibration
as a universal configuration.
