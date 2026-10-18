#!/usr/bin/python3
"""Publish net.hadess.SensorProxy light levels into the als-bridge IIO module.

Steam reads /sys/bus/iio/devices/iio:deviceN/in_illuminance_raw directly and
refuses to enable its adaptive-brightness switch unless a sysfs IIO light
sensor exists. The real sensor is only reachable via the SSC, which
iio-sensor-proxy (libssc) exposes over D-Bus - so this daemon claims the light
sensor there and mirrors the lux value into the als-bridge module parameter,
which is what the IIO device's in_illuminance_raw reports.

The proxy must not claim the synthetic device itself (see
90-als-bridge-proxy.rules): otherwise it serves this same value back and the
loop stays at 0 lux.

The claim is lost whenever iio-sensor-proxy restarts, and a missed
PropertiesChanged signal would freeze the published value, so the daemon
re-claims on the proxy's reappearance and re-reads the property every few
seconds.
"""

import sys

import gi
gi.require_version("GLib", "2.0")
from gi.repository import GLib, Gio

SENSOR_BUS_NAME = "net.hadess.SensorProxy"
SENSOR_OBJ_PATH = "/net/hadess/SensorProxy"
SENSOR_IFACE = "net.hadess.SensorProxy"
LUX_PARAM = "/sys/module/als_bridge/parameters/lux"
REFRESH_SECONDS = 5


def publish(value):
    try:
        with open(LUX_PARAM, "w") as f:
            f.write(str(int(round(value))))
    except OSError as err:
        print(f"failed to publish lux: {err}", file=sys.stderr)


def get_props(bus):
    return bus.call_sync(
        SENSOR_BUS_NAME, SENSOR_OBJ_PATH,
        "org.freedesktop.DBus.Properties", "GetAll",
        GLib.Variant("(s)", (SENSOR_IFACE,)), None,
        Gio.DBusCallFlags.NONE, -1, None,
    ).unpack()[0]


def claim(bus):
    bus.call_sync(
        SENSOR_BUS_NAME, SENSOR_OBJ_PATH, SENSOR_IFACE, "ClaimLight",
        None, None, Gio.DBusCallFlags.NONE, -1, None,
    )


def publish_current(bus):
    try:
        publish(get_props(bus)["LightLevel"])
    except GLib.Error:
        pass


def on_properties_changed(bus, sender, path, iface, signal, params):
    _iface, changed, _invalidated = params.unpack()
    if "LightLevel" in changed:
        publish(changed["LightLevel"])


def on_name_owner_changed(bus, sender, path, iface, signal, params):
    name, _old, new_owner = params.unpack()
    if name != SENSOR_BUS_NAME or not new_owner:
        return
    # iio-sensor-proxy (re)appeared: our previous claim is gone, take it again
    # so the proxy keeps polling and publishing.
    try:
        claim(bus)
    except GLib.Error as err:
        print(f"failed to re-claim light sensor: {err}", file=sys.stderr)
    publish_current(bus)


def on_refresh(bus):
    publish_current(bus)
    return True


def main():
    bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)

    bus.signal_subscribe(
        "org.freedesktop.DBus", "org.freedesktop.DBus",
        "NameOwnerChanged", "/org/freedesktop/DBus", None,
        Gio.DBusSignalFlags.NONE, on_name_owner_changed,
    )
    bus.signal_subscribe(
        SENSOR_BUS_NAME, "org.freedesktop.DBus.Properties",
        "PropertiesChanged", SENSOR_OBJ_PATH, None,
        Gio.DBusSignalFlags.NONE, on_properties_changed,
    )

    try:
        props = get_props(bus)
    except GLib.Error as err:
        print(f"waiting for SensorProxy: {err}", file=sys.stderr)
        props = None

    if props is not None:
        if not props["HasAmbientLight"]:
            print("SensorProxy reports no ambient light sensor", file=sys.stderr)
            return 1
        claim(bus)
        publish(props["LightLevel"])

    GLib.timeout_add_seconds(REFRESH_SECONDS, on_refresh, bus)
    loop = GLib.MainLoop()
    try:
        loop.run()
    finally:
        try:
            bus.call_sync(
                SENSOR_BUS_NAME, SENSOR_OBJ_PATH, SENSOR_IFACE, "ReleaseLight",
                None, None, Gio.DBusCallFlags.NONE, -1, None,
            )
        except GLib.Error:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
