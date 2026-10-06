# Userspace patches

Each patch applies to the corresponding public commit in `sources.json`.
`scripts/fetch-sources.py` applies it to the Git index and verifies the exact
resulting tree. This avoids relying on unpublished branches or private builds.

- `hexagonrpc.patch`: writable Linux sensor registry state and safe filesystem
  descriptor/alias handling.
- `libcamera.patch`: CAMSS/simple-pipeline capture handling, sensor controls,
  request cleanup and qcam lens controls.

(`iio-sensor-proxy.patch` now lives with its package,
`packages/iio-sensor-proxy-y700/`, which builds it from the pinned commit as a
renamed package instead of a plain source build.)

The patches retain the licenses of their upstream files. Kernel changes are
already published in the pinned kernel repository and are not duplicated here.
