"""Profile isolation, reversible launch state, and exclusive framegen activation."""
import asyncio
import importlib.util
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]

class RenderToolsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        decky = types.ModuleType('decky')
        decky.DECKY_USER_HOME = str(self.home)
        decky.DECKY_PLUGIN_SETTINGS_DIR = str(self.home / 'settings')
        decky.logger = logging.getLogger('render-test')
        upstream = types.ModuleType('upscaling'); upstream.PROXIES = ['dxgi.dll']
        self.modules = patch.dict(sys.modules, decky=decky, upscaling=upstream, steamlib=types.ModuleType('steamlib'))
        self.modules.start(); self.addCleanup(self.modules.stop)
        spec = importlib.util.spec_from_file_location('render_test_backend', ROOT/'packages/decky-render-tools/main.py')
        self.backend = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.backend)

    def test_invalid_profile_does_not_write(self):
        for bad in ('../../escape', True, 0, -1, 2**32):
            with self.assertRaises(ValueError): self.backend.app_id(bad)
        for patch_ in ({'multiplier':'4'}, {'flow_scale':float('nan')}, {'enabled':'false'}, {'extra':1}):
            with self.assertRaises(ValueError): self.backend.save_fg(12, patch_)
        self.assertFalse((self.home/'.config').exists())

    def test_profiles_are_opt_in_and_isolated(self):
        self.assertFalse(self.backend.get_fg(12)['enabled'])
        self.backend.save_fg(12, {'enabled':True,'multiplier':'3'})
        self.assertFalse(self.backend.get_fg(13)['enabled'])
        self.backend.save_fg(12, {'enabled':False})
        conf = self.home/'.config/kettle-framegen/12.conf'
        self.assertIn('multiplier = 1\n', conf.read_text())
        self.assertEqual(self.backend.get_fg(12)['multiplier'],'3')

    def test_override_ownership_keeps_original(self):
        plugin = self.backend.Plugin()
        async def exercise():
            await plugin.up_launch_save(12,'dxgi.dll','b')
            await plugin.up_launch_save(12,'dxgi.dll','n,b')
            self.assertEqual((await plugin.up_launch_get(12))['before'],'b')
            await plugin.up_launch_clear(12)
            self.assertIsNone(await plugin.up_launch_get(12))
        asyncio.run(exercise())

    def test_launcher_disables_only_other_frame_generators(self):
        self.backend.save_fg(12, {'enabled':True,'bypass_wsi':True})
        env = dict(os.environ,HOME=str(self.home),XDG_CONFIG_HOME=str(self.home/'.config'),SteamAppId='12',
                   LSFG_CLASSIC='1',DISABLE_LSFGVK='0',ENABLE_GAMESCOPE_WSI='1',
                   VK_INSTANCE_LAYERS='VK_LAYER_other:VK_LAYER_LSFGVK_frame_generation_arm64')
        run = subprocess.run([sys.executable,str(ROOT/'packages/kettle-framegen-armada/kettle-fg'),
                              sys.executable,'-c','import os,json;print(json.dumps(dict(os.environ)))'],
                             env=env,capture_output=True,text=True,check=True)
        result = json.loads(run.stdout)
        self.assertEqual(result['KETTLE_FG'],'1')
        self.assertEqual(result['DISABLE_LSFGVK'],'1')
        self.assertEqual(result['DISABLE_LSFG'],'1')
        self.assertEqual(result['LSFG_CLASSIC'],'0')
        self.assertEqual(result['VK_INSTANCE_LAYERS'],'VK_LAYER_other')
        self.assertEqual(result['ENABLE_GAMESCOPE_WSI'],'0')
        self.assertEqual(env['ENABLE_GAMESCOPE_WSI'],'1')

    def test_launcher_without_bypass_preserves_wsi(self):
        self.backend.save_fg(12, {'enabled':True,'bypass_wsi':False})
        env=dict(os.environ,XDG_CONFIG_HOME=str(self.home/'.config'),SteamAppId='12',ENABLE_GAMESCOPE_WSI='1')
        result=subprocess.check_output([sys.executable,str(ROOT/'packages/kettle-framegen-armada/kettle-fg'),
                                        sys.executable,'-c','import os;print(os.environ["ENABLE_GAMESCOPE_WSI"])'],env=env,text=True)
        self.assertEqual(result.strip(),'1')

if __name__=='__main__': unittest.main()
