#!/usr/bin/python3
"""Publish net.hadess.SensorProxy light levels into the als-bridge IIO module.

Steam reads /sys/bus/iio/devices/iio:deviceN/in_illuminance_raw directly and
refuses to enable its adaptive-brightness switch unless a sysfs IIO light
sensor exists. The sensor on this device is only reachable via the SSC, which
iio-sensor-proxy (libssc) exposes over D-Bus - so this daemon claims the light
sensor there and mirrors the lux value into the als-bridge module parameter,
which is what the IIO device's in_illuminance_raw reports.
"""

import sys

import gi
gi.require_version("GLib", "2.0")
from gi.repository import GLib, Gio

SENSOR_BUS_NAME = "net.hadess.SensorProxy"
SENSOR_OBJ_PATH = "/net/hadess/SensorProxy"
SENSOR_IFACE = "net.hadess.SensorProxy"
LUX_PARAM = "/sys/module/als_bridge/parameters/lux"


def publish(value):
    try:
        with open(LUX_PARAM, "w") as f:
            f.write(str(int(round(value))))
    except OSError as err:
        print(f"failed to publish lux: {err}", file=sys.stderr)


def on_properties_changed(bus, sender, path, iface, signal, params):
    _iface, changed, _invalidated = params.unpack()
    if "LightLevel" in changed:
        publish(changed["LightLevel"])


def main():
    bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)

    props = bus.call_sync(
        SENSOR_BUS_NAME, SENSOR_OBJ_PATH,
        "org.freedesktop.DBus.Properties", "GetAll",
        GLib.Variant("(s)", (SENSOR_IFACE,)), None,
        Gio.DBusCallFlags.NONE, -1, None,
    ).unpack()[0]

    if not props["HasAmbientLight"]:
        print("SensorProxy reports no ambient light sensor", file=sys.stderr)
        return 1

    bus.call_sync(
        SENSOR_BUS_NAME, SENSOR_OBJ_PATH, SENSOR_IFACE, "ClaimLight",
        None, None, Gio.DBusCallFlags.NONE, -1, None,
    )
    publish(props["LightLevel"])

    bus.signal_subscribe(
        SENSOR_BUS_NAME, "org.freedesktop.DBus.Properties",
        "PropertiesChanged", SENSOR_OBJ_PATH, None,
        Gio.DBusSignalFlags.NONE, on_properties_changed,
    )

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
