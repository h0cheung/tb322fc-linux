"""Exercise user paths, two-engine isolation and real configuration round trips."""
import builtins
import importlib
import importlib.util
import io
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
decky = types.ModuleType("decky")
decky.logger = logging.getLogger("lsfg-port-test")
sys.modules["decky"] = decky


def load(flavor):
    name = "port_" + flavor
    directory = ROOT / "plugins" / ("decky-lsfg-vk-classic" if flavor == "classic" else "decky-lsfg-vk") / "py_modules" / "lsfg_vk"
    spec = importlib.util.spec_from_file_location(name, directory / "__init__.py", submodule_search_locations=[str(directory)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return name


CLASSIC = load("classic")
V2 = load("v2")


def component(package, filename, symbol):
    return getattr(importlib.import_module(package + "." + filename), symbol)


class PortTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.user_home = Path(self.temporary.name) / "steam user"
        self.user_home.mkdir()
        decky.DECKY_USER_HOME = str(self.user_home)
        self.environment = mock.patch.dict(os.environ, {"HOME": str(Path(self.temporary.name) / "root"), "DECKY_USER_HOME": str(self.user_home)})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def save_classic_dll(self):
        path = self.user_home / ".local/share/lsfg-vk-classic/Lossless.dll"
        path.parent.mkdir(parents=True)
        path.write_bytes(b"saved-classic-dll")
        return path

    def test_services_use_decky_user_even_with_root_home(self):
        for package in (CLASSIC, V2):
            service = component(package, "base_service", "BaseService")()
            self.assertEqual(service.user_home, self.user_home)

    def test_classic_keeps_saved_dll_after_steam_branch_switch(self):
        saved = self.save_classic_dll()
        current = self.user_home / ".local/share/Steam/steamapps/common/Lossless Scaling/Lossless.dll"
        current.parent.mkdir(parents=True)
        current.write_bytes(b"different-after-beta-switch")
        service = component(CLASSIC, "dll_detection", "DllDetectionService")()
        self.assertEqual(service.check_lossless_scaling_dll()["path"], str(saved))

    def test_classic_profile_save_and_script_settings_round_trip(self):
        saved = self.save_classic_dll()
        service = component(CLASSIC, "configuration", "ConfigurationService")()
        current = service._get_profile_data()["current_profile"]
        config = component(CLASSIC, "config_schema", "ConfigurationManager").get_defaults()
        config.update(dll=str(saved), multiplier=2, enable_wsi=True, mangohud_workaround=True, enable_zink=True)
        result = service.update_profile_config(current, config)
        self.assertTrue(result["success"], result)
        got = service.get_config()["config"]
        for field in ("enable_wsi", "mangohud_workaround", "enable_zink"):
            self.assertTrue(got[field], (field, got))
        self.assertEqual(got["dll"], str(saved))

    def test_classic_launcher_disables_v2_and_preserves_profile_name(self):
        self.save_classic_dll()
        service = component(CLASSIC, "configuration", "ConfigurationService")()
        data = service._get_profile_data()
        old = data["current_profile"]
        data["current_profile"] = "two words; literal"
        data["profiles"][data["current_profile"]] = data["profiles"].pop(old)
        script = self.user_home / "lsfg-classic"
        script.write_text(service._generate_script_content_for_profile(data))
        code = "import os,json;print(json.dumps({k:os.getenv(k) for k in ['LSFG_CLASSIC','DISABLE_LSFG','DISABLE_LSFGVK','LSFG_PROCESS']}))"
        environment = dict(os.environ, HOME=str(self.user_home), DISABLE_LSFG="1")
        result = subprocess.run(["bash", str(script), sys.executable, "-c", code], env=environment, capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout), {"LSFG_CLASSIC":"1", "DISABLE_LSFG":None, "DISABLE_LSFGVK":"1", "LSFG_PROCESS":data["current_profile"]})

    def test_v2_installer_uses_native_cli_and_keeps_x86_layers(self):
        service = component(V2, "installation", "InstallationService")()
        native = self.user_home / "native-cli"
        native.write_bytes(b"native-arm64-cli")
        archive = self.user_home / "payload.tar"
        destinations = service._payload_destinations()
        with tarfile.open(archive, "w") as output:
            for name in destinations:
                payload = b"x86-archive-" + name.encode()
                member = tarfile.TarInfo("./" + name)
                member.size = len(payload)
                output.addfile(member, io.BytesIO(payload))
        def native_open(path, *args, **kwargs):
            return builtins.open(native if path == "/usr/bin/lsfg-vk-cli" else path, *args, **kwargs)
        with mock.patch(V2 + ".installation.open", side_effect=native_open, create=True):
            service._install_archive(archive)
        self.assertEqual(service.cli_file.read_bytes(), native.read_bytes())
        self.assertTrue(service.lib_file.read_bytes().startswith(b"x86-archive-"))
        self.assertTrue(service.lib_x86_file.exists())
        self.assertFalse((self.user_home / ".local/bin/lsfg-vk-ui").exists())

    @unittest.skipUnless(Path("/usr/bin/lsfg-vk-cli").is_file(), "native CLI is tested on the tablet")
    def test_v2_game_config_round_trips_through_real_cli(self):
        runtime = component(V2, "runtime_service", "RuntimeService")()
        runtime.cli_path = Path("/usr/bin/lsfg-vk-cli")
        service = component(V2, "configuration", "ConfigurationService")(runtime_service=runtime)
        result = service.update_game_config("1057090", "Test game", {"multiplier":2, "flow_scale":0.5, "performance_mode":True})
        self.assertTrue(result["success"], result)
        got = service.get_game_configs()
        self.assertTrue(got["success"], got)
        self.assertEqual(got["games"][0]["appid"], "1057090")
        self.assertEqual(got["games"][0]["config"]["multiplier"], 2)

    def test_v2_workarounds_clear_classic_and_round_trip(self):
        service = component(V2, "wrapper_service", "WrapperService")()
        state = service.default_state()
        state.update(disableGamescopeWsi=True, disableHdr=True)
        result = service.set("1057090", state)
        self.assertTrue(result["success"], result)
        self.assertIn("LSFG_CLASSIC", service.wrapper_path.read_text())
        self.assertEqual(service.get("1057090")["state"], state)


if __name__ == "__main__":
    unittest.main()
