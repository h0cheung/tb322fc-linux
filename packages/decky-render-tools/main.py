# SPDX-License-Identifier: BSD-3-Clause
"""Opt-in rendering tools; no power-service or loader-specific imports."""
import asyncio
import json
import math
import os
from pathlib import Path
import sys
import threading

import decky
sys.path.insert(0, str(Path(__file__).parent / 'py_modules'))
import steamlib
import upscaling

_lock = threading.Lock()
FG_DEFAULT = dict(enabled=False, multiplier='2', flow_scale=0.5, preserve_images=False, bypass_wsi=True)

def app_id(value):
    if isinstance(value, bool) or not str(value).isdigit() or not 0 < int(value) <= 0xffffffff:
        raise ValueError('Invalid Steam app ID')
    return int(value)

def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, indent=2) + '\n')
    os.replace(tmp, path)

def profiles_path():
    return Path(decky.DECKY_PLUGIN_SETTINGS_DIR) / 'framegen.json'

def load_profiles():
    try:
        return json.loads(profiles_path().read_text())
    except FileNotFoundError:
        return {}

def get_fg(appid):
    return {**FG_DEFAULT, **load_profiles().get(str(appid), {})}

def save_fg(appid, patch):
    with _lock:
        if not set(patch) <= set(FG_DEFAULT):
            raise ValueError('Unknown framegen setting')
        g = {**get_fg(appid), **patch}
        if g['multiplier'] not in ('2', '3', 'auto'):
            raise ValueError('Invalid multiplier')
        if type(g['flow_scale']) not in (int, float) or not math.isfinite(g['flow_scale']) or not 0.25 <= g['flow_scale'] <= 1:
            raise ValueError('Invalid flow scale')
        if any(type(g[k]) is not bool for k in ('enabled', 'preserve_images', 'bypass_wsi')):
            raise ValueError('Invalid toggle')
        conf = Path(decky.DECKY_USER_HOME) / '.config/kettle-framegen' / f'{appid}.conf'
        conf.parent.mkdir(parents=True, exist_ok=True)
        text = (f"multiplier = {g['multiplier'] if g['enabled'] else '1'}\n"
                f"flow_scale = {g['flow_scale']}\nfifo = true\n"
                f"preserve_images = {str(g['preserve_images']).lower()}\nlatency = normal\n")
        tmp = conf.with_suffix('.tmp'); tmp.write_text(text); os.replace(tmp, conf)
        atomic_json(conf.with_suffix('.launcher.json'), {'bypass_wsi': g['bypass_wsi']})
        profiles = load_profiles(); profiles[str(appid)] = g; atomic_json(profiles_path(), profiles)
        return g

def up_call(name, *args):
    with _lock:
        return getattr(upscaling, name)(*args)

class Plugin:
    async def installed_games(self):
        return await asyncio.to_thread(steamlib.installed_games)

    async def fg_get(self, appid):
        return get_fg(app_id(appid))

    async def fg_set(self, appid, settings):
        return await asyncio.to_thread(save_fg, app_id(appid), settings)

    async def up_launch_get(self, appid):
        appid = app_id(appid)
        path = Path(decky.DECKY_PLUGIN_SETTINGS_DIR) / 'launch-owned.json'
        with _lock:
            try:
                return json.loads(path.read_text()).get(str(appid))
            except FileNotFoundError:
                return None

    async def up_launch_save(self, appid, proxy, before):
        appid = app_id(appid)
        if proxy not in upscaling.PROXIES or (before is not None and not isinstance(before, str)):
            raise ValueError('Invalid DLL override state')
        path = Path(decky.DECKY_PLUGIN_SETTINGS_DIR) / 'launch-owned.json'
        with _lock:
            try:
                states = json.loads(path.read_text())
            except FileNotFoundError:
                states = {}
            states.setdefault(str(appid), {'proxy': proxy, 'before': before})
            atomic_json(path, states)

    async def up_launch_clear(self, appid):
        appid = app_id(appid)
        path = Path(decky.DECKY_PLUGIN_SETTINGS_DIR) / 'launch-owned.json'
        with _lock:
            try:
                states = json.loads(path.read_text())
            except FileNotFoundError:
                return
            states.pop(str(appid), None)
            atomic_json(path, states)

    async def up_status(self):
        return upscaling.status()

    async def up_get_game(self, appid):
        return await asyncio.to_thread(up_call, 'get_game', app_id(appid))

    async def up_select_install(self, appid, exe_dir, proxy):
        return await asyncio.to_thread(up_call, 'select_install', app_id(appid), exe_dir, proxy)

    async def up_enable(self, appid, exe_dir, proxy):
        return await asyncio.to_thread(up_call, 'enable', app_id(appid), exe_dir, proxy)

    async def up_disable(self, appid):
        return await asyncio.to_thread(up_call, 'disable', app_id(appid))

    async def up_configure(self, appid, settings):
        return await asyncio.to_thread(up_call, 'configure', app_id(appid), settings)

    async def up_reset(self, appid):
        return await asyncio.to_thread(up_call, 'reset', app_id(appid))

    async def _main(self):
        pass

    async def _unload(self):
        pass
