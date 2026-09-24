#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Internal entry point: called only inside the native AArch64 build chroot.
set -euo pipefail
[[ $EUID == 0 && $(uname -m) == aarch64 && -d /root/tb322fc-build/sources ]] || {
    echo 'Run build-rootfs.sh on a native AArch64 host; do not run this script on the host.' >&2
    exit 1
}
cd /root/tb322fc-build
export LC_ALL=C.UTF-8
JOBS=${JOBS:-$(nproc)}

# Keep package signatures enabled. The authenticated bootstrap contains the
# distro keyring; update it before the full rolling-release upgrade.
pacman-key --init
pacman-key --populate archlinuxarm
pacman -Sy --noconfirm archlinuxarm-keyring
pacman -Syu --noconfirm
runtime_packages=(
    base systemd systemd-sysvcompat linux-firmware kmod sudo nano less
    networkmanager wpa_supplicant bluez bluez-utils
    plasma-desktop plasma-workspace plasma-nm plasma-pa plasma-keyboard powerdevil xdg-desktop-portal-kde
    kscreen breeze sddm layer-shell-qt qt6-wayland qt6-virtualkeyboard xorg-xwayland
    konsole dolphin ark firefox
    mesa vulkan-freedreno vulkan-icd-loader mesa-utils vulkan-tools
    alsa-ucm-conf alsa-utils pipewire pipewire-audio pipewire-alsa pipewire-pulse wireplumber
    noto-fonts noto-fonts-cjk fcitx5 fcitx5-chinese-addons fcitx5-configtool fcitx5-qt fcitx5-gtk
    libqmi protobuf-c glib2 libgudev polkit libyaml libevent qt6-base
)
build_packages=(
    base-devel linux-api-headers meson ninja git python pkgconf
    glib2-devel protobuf gobject-introspection vala gettext
    python-jinja python-ply python-yaml openssl
)
pacman -S --needed --noconfirm "${runtime_packages[@]}" "${build_packages[@]}"

# Package versions include an epoch (1:); compare the upstream version itself.
for package in mesa vulkan-freedreno; do
    read -r _ version < <(pacman -Q "$package")
    upstream=${version#*:}
    if (( $(vercmp "$upstream" 26.2.1) < 0 )); then
        echo "$package $version is below this CI's tested Adreno 830 baseline (26.2.1). Use an up-to-date Arch Linux ARM mirror and rebuild." >&2
        exit 1
    fi
done

# Apply verified device firmware after distro package installation. Never copy
# directory contents from the input bundle that are absent from firmware.json.
python3 - <<'PY'
import json
from pathlib import Path
import shutil

for item in json.loads(Path('/usr/share/tb322fc/firmware.json').read_text())['files']:
    source = Path('firmware') / item['path']
    target = Path('/usr/lib/firmware') / item['path']
    target.parent.mkdir(parents=True, exist_ok=True)
    target.unlink(missing_ok=True)
    shutil.copyfile(source, target)
    target.chmod(0o644)
PY

mkdir -p build /usr/share/tb322fc/meson
build_component() {
    local component=$1
    shift
    meson setup "build/$component" "sources/$component" --prefix=/usr --libdir=lib \
        --buildtype=release --wrap-mode=nodownload "$@"
    meson compile -C "build/$component" -j "$JOBS"
    meson install -C "build/$component"
    cp "build/$component/meson-info/intro-buildoptions.json" "/usr/share/tb322fc/meson/$component.json"
    ldconfig
}
build_component hexagonrpc
build_component libssc
build_component iio-sensor-proxy --libexecdir=libexec -Dssc-support=enabled \
    -Dtests=false -Dgtk-tests=false -Dgtk_doc=false
build_component libcamera -Dpipelines=simple -Dipas=softisp -Dqcam=enabled -Dcam=enabled \
    -Ddocumentation=disabled -Dgstreamer=disabled -Dpycamera=disabled \
    -Dlc-compliance=disabled -Dv4l2=disabled -Dsoftisp-gpu=disabled \
    -Dapps-output-dng=disabled -Dtest=false

# Keep pacman upgrades from replacing the patched libraries with distro builds.
# Manual installation of a conflicting package must first remove this guard
# and rebuild the device support; these builds are recorded in sources.json.
sed -i '/^\[options\]$/a IgnorePkg = hexagonrpc libssc iio-sensor-proxy libcamera libcamera-ipa libcamera-tools' /etc/pacman.conf

release=$(cat /usr/share/tb322fc/kernel.release)
[[ $release =~ ^[a-zA-Z0-9._+-]+$ ]] || { echo 'Invalid kernel release' >&2; exit 1; }
# The archive uses usr/lib/modules; do not overwrite Arch's /lib symlink.
tar --numeric-owner -xzf kernel-modules.tar.gz -C /
[[ -d /usr/lib/modules/$release ]] || { echo "No modules directory for $release" >&2; exit 1; }
depmod -a "$release"

# Preserve upstream UCM as a diagnostic backup before the device overlay.
tar -C /usr/share/alsa -czf /usr/share/tb322fc/ucm2-before-overlay.tar.gz ucm2
cp -a overlay/audio/ucm2/. /usr/share/alsa/ucm2/
install -Dm644 overlay/camera/70-libcamera-dma-heap.rules /etc/udev/rules.d/70-libcamera-dma-heap.rules
install -Dm644 overlay/camera/libcamera-qcam.desktop /usr/share/applications/libcamera-qcam.desktop
install -Dm644 overlay/sensors/hexagonrpcd-sensors.service /etc/systemd/system/hexagonrpcd-sensors.service
install -Dm644 overlay/sensors/iio-sensor-proxy.conf /etc/systemd/system/iio-sensor-proxy.service.d/ssc.conf
install -d -m 700 /var/lib/hexagonrpc /var/lib/hexagonrpc/sensors
ln -s /sys/devices/soc0 /var/lib/hexagonrpc/socinfo
# Enablement is harmless before calibration is installed: both services are
# gated on the same required paths, including the per-device registry state.
for service in hexagonrpcd-sensors iio-sensor-proxy; do
    install -d "/etc/systemd/system/$service.service.d"
    cat > "/etc/systemd/system/$service.service.d/require-device-data.conf" <<'EOF'
[Unit]
ConditionDirectoryNotEmpty=/var/lib/hexagonrpc/acdb
ConditionDirectoryNotEmpty=/var/lib/hexagonrpc/dsp
ConditionDirectoryNotEmpty=/var/lib/hexagonrpc/sensors/config
ConditionDirectoryNotEmpty=/var/lib/hexagonrpc/sensors/state/registry
ConditionPathExists=/var/lib/hexagonrpc/sensors/state/sns_reg_version
ConditionPathExists=/var/lib/hexagonrpc/sensors/sns_reg.conf
EOF
done

# Turnip (Vulkan) plus Zink (OpenGL) is the tested A830 graphics path.
shopt -s nullglob
icds=(/usr/share/vulkan/icd.d/freedreno_icd*.json)
(( ${#icds[@]} == 1 )) || { echo 'Expected one native Freedreno Vulkan ICD.' >&2; exit 1; }
cat > /etc/environment <<EOF
GALLIUM_DRIVER=zink
MESA_LOADER_DRIVER_OVERRIDE=zink
VK_DRIVER_FILES=${icds[0]}
XMODIFIERS=@im=fcitx
EOF
install -d /etc/sddm.conf.d /etc/systemd/system/sddm.service.d
cat > /etc/sddm.conf.d/10-tb322fc.conf <<'EOF'
[General]
DisplayServer=wayland
GreeterEnvironment=QT_WAYLAND_SHELL_INTEGRATION=layer-shell

[Wayland]
CompositorCommand=kwin_wayland --drm --no-lockscreen --no-global-shortcuts --locale1

[Theme]
Current=breeze
EOF
install -d /etc/xdg
cat > /etc/xdg/kwinrc <<'EOF'
[Wayland]
InputMethod=/usr/share/applications/org.kde.plasma.keyboard.desktop
VirtualKeyboardEnabled=true
EOF
[[ -f /usr/share/applications/org.kde.plasma.keyboard.desktop ]]
cat > /etc/systemd/system/sddm.service.d/graphics.conf <<EOF
[Service]
Environment=GALLIUM_DRIVER=zink MESA_LOADER_DRIVER_OVERRIDE=zink VK_DRIVER_FILES=${icds[0]}
EOF

sed -i -E 's/^#(en_US.UTF-8 UTF-8|zh_CN.UTF-8 UTF-8)$/\1/' /etc/locale.gen
locale-gen
echo 'LANG=en_US.UTF-8' > /etc/locale.conf
ln -sf /usr/share/zoneinfo/UTC /etc/localtime
echo 'y700-gen4' > /etc/hostname
cat > /etc/hosts <<'EOF'
127.0.0.1 localhost
::1 localhost
127.0.1.1 y700-gen4
EOF
cat > /etc/fstab <<'EOF'
# The initramfs already mounts the existing partition named rootfs.
PARTLABEL=rootfs / ext4 defaults,noatime 0 1
EOF
if ! id alarm >/dev/null 2>&1; then
    useradd -m -s /bin/bash alarm
fi
usermod -aG wheel,video,input alarm
echo 'alarm:alarm' | chpasswd
chage -d 0 alarm
passwd -l root
install -d -m 750 /etc/sudoers.d
echo '%wheel ALL=(ALL:ALL) ALL' > /etc/sudoers.d/10-wheel
chmod 440 /etc/sudoers.d/10-wheel
visudo -cf /etc/sudoers.d/10-wheel
cat > /etc/issue <<'EOF'
Arch Linux ARM on Lenovo Y700 Gen 4 (TB322FC)
Initial login: alarm / alarm. Change the password at first login.
EOF

# Use NetworkManager as the sole network manager. Never enable SSH by default.
for service in systemd-networkd.service systemd-networkd.socket systemd-networkd-wait-online.service dhcpcd.service sshd.service sshd.socket; do
    if [[ -f /usr/lib/systemd/system/$service || -L /etc/systemd/system/$service ]]; then
        systemctl disable "$service"
    fi
done
systemctl enable NetworkManager.service bluetooth.service sddm.service hexagonrpcd-sensors.service
systemctl set-default graphical.target
systemctl --global enable pipewire.socket pipewire-pulse.socket wireplumber.service

# Record both pacman packages and the source-built components.
pacman -Q > /usr/share/tb322fc/rootfs.packages
{
    printf 'kernel_release=%s\n' "$release"
    printf 'architecture=%s\n' "$(uname -m)"
    printf 'meson=%s\n' "$(meson --version)"
    printf 'hexagonrpc=from-sources.json\n'
    printf 'libssc=%s\n' "$(pkg-config --modversion libssc)"
    printf 'libcamera=%s\n' "$(pkg-config --modversion libcamera)"
    printf 'iio-sensor-proxy=from-sources.json\n'
} > /usr/share/tb322fc/userspace-build.txt
[[ -x /usr/bin/hexagonrpcd && -x /usr/libexec/iio-sensor-proxy && -x /usr/bin/qcam && -x /sbin/init ]]
[[ -f /usr/share/wayland-sessions/plasma.desktop ]]
# Leave build tools installed for diagnosis. Remove downloads, host identities
# and transient state; package signatures and the distro trust database remain.
pacman -Scc --noconfirm
rm -f /etc/machine-id /var/lib/dbus/machine-id /var/lib/systemd/random-seed
: > /etc/machine-id
ln -s /etc/machine-id /var/lib/dbus/machine-id
rm -f /etc/ssh/ssh_host_* /root/.bash_history
find /var/log -type f -exec truncate -s 0 {} +
