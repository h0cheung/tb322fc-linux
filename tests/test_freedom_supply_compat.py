#!/usr/bin/env python3
"""Exercise charge writes and thermal policy across the two kernel names."""
import importlib.machinery
import importlib.util
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


charge = load("charge_compat", ROOT / "packages/y700-charge/y700-charged")
thermal = load("thermal_compat", ROOT / "rootfs/thermald/adapt_thermal_conf.py")


class SupplyCompatibility(unittest.TestCase):
    def test_thermal_startup_rejects_missing_battery(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "runtime.xml"
            command = [sys.executable, str(ROOT / "rootfs/thermald/adapt_thermal_conf.py"),
                       "--source", str(ROOT / "rootfs/thermald/thermal-conf.xml"),
                       "--thermal-root", tmp, "--output", str(output)]
            result = subprocess.run(command, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(output.exists())
            zone = Path(tmp) / "thermal_zone99"
            zone.mkdir()
            (zone / "type").write_text("battery")
            subprocess.run(command, check=True)
            self.assertEqual(sum(x.text == "battery" for x in ET.fromstring(output.read_text()).iter("SensorType")), 3)

    def test_charge_control_and_readback_for_each_name(self):
        for name in charge.BATTERY_NAMES:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                battery = Path(tmp) / name
                battery.mkdir()
                for key, value in {"constant_charge_current": "3000000", "capacity": "76",
                                   "charge_control_start_threshold": "60",
                                   "charge_control_end_threshold": "70"}.items():
                    (battery / key).write_text(value)
                cfg = dict(charge.DEFAULT_CONFIG, bypass=True, threshold=85)
                with patch.object(charge, "POWER_SUPPLY_ROOT", tmp), patch.object(charge, "mirror_hwdb"):
                    charge.apply_config(cfg)
                    state = charge.read_state(cfg)
                self.assertEqual((battery / "constant_charge_current").read_text(), "0")
                self.assertEqual((battery / "charge_control_end_threshold").read_text(), "85")
                self.assertEqual((battery / "charge_control_start_threshold").read_text(), "75")
                self.assertEqual(state["capacity"], 76)
                self.assertTrue(state["supported"])

    def test_late_registration_and_both_uevent_names(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(charge, "POWER_SUPPLY_ROOT", tmp):
            self.assertFalse(charge.battery_present())
            battery = Path(tmp) / "battery"
            battery.mkdir()
            (battery / "constant_charge_current").write_text("3000000")
            self.assertTrue(charge.battery_present())
            self.assertEqual(charge.BAT, str(battery))
        for name in charge.BATTERY_NAMES:
            event = f"SUBSYSTEM=power_supply\0DEVPATH=/devices/test/{name}\0ACTION=add\0".encode()
            with patch.object(charge, "apply_config") as apply, patch.object(charge, "load_config", return_value={}):
                charge._handle_uevent(event)
                apply.assert_called_once_with({})
        self.assertIn("battery:battery:*:\n CHARGE_LIMIT=75,85", charge._hwdb_body(75, 85))

    def test_thermal_sensor_selection_preserves_all_policy_values(self):
        source = ROOT / "rootfs/thermald/thermal-conf.xml"
        original = source.read_text()
        temperatures = [x.text for x in ET.fromstring(original).iter("Temperature")]
        states = [x.text for x in ET.fromstring(original).iter("TargetState")]
        for name in charge.BATTERY_NAMES:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                zone = Path(tmp) / "thermal_zone99"
                zone.mkdir()
                (zone / "type").write_text(name)
                adapted = thermal.adapt(source, tmp)
                xml = ET.fromstring(adapted)
                self.assertEqual([x.text for x in xml.iter("Temperature")], temperatures)
                self.assertEqual([x.text for x in xml.iter("TargetState")], states)
                self.assertEqual(sum(x.text == name for x in xml.iter("SensorType")), 3)


if __name__ == "__main__":
    unittest.main()
