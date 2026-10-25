# FFmpeg stateful V4L2

The complete Arch Linux FFmpeg recipe is based on [packaging commit
5c4a25f039c060c421a1cd887551d491dff4d55d](https://gitlab.archlinux.org/archlinux/packaging/packages/ffmpeg/-/tree/5c4a25f039c060c421a1cd887551d491dff4d55d).
It retains the signed 9.0.2 source, Chromium compatibility patch, codec
configuration and shared-library ABI. `ffmpeg-v4l2m2m` provides `ffmpeg`
and its library sonames and conflicts with the distribution package.

Three checksum-pinned patches are referenced from [Project-SunUEFI
be307364](https://github.com/slwyts/Project-SunUEFI/tree/be3073644216a413776b973203d4222e8950703a/linux/bsp/patches/ffmpeg):
stateful source-change sequencing, capture-buffer lifetime across resolution
changes, and P010 capture format handling. Patches retain the licenses and
notices of the original FFmpeg files.

Full Iris resolution-change validation also needs the kernel PSC_LAST fix;
building or installing this userspace package alone does not supply it.
Vivaldi's Chromium-specific `libffmpeg.so` is a separate build and cannot be
replaced by this package's `libavcodec.so` or command-line executable.

On the tablet with kernel `7.2.6-11-freedom`, Iris decoded the 12-frame H.264
sample and all 36 frames across 640x480 -> 1280x720 -> 640x480. Hardware
encoding produced 12 decodable frames; unloading and reloading Iris also
completed. Other codecs and P010 were not tested.

The raw H.264 encoder test has a remaining timing limitation: ffprobe reports
60 fps for a 25 fps input with both this package and the stock 9.0.2 package
on the same kernel. This port does not correct that encoder behavior.

Arch's [Vivaldi codec recipe](https://gitlab.archlinux.org/archlinux/packaging/packages/vivaldi-ffmpeg-codecs/-/blob/main/PKGBUILD)
builds a selected set of software codecs from Chromium's FFmpeg fork into
`/opt/vivaldi/libffmpeg.so.<browser-major>`. Replacing that library requires
a matching Chromium build; its preload path does not enable these V4L2 fixes.
