import asyncio

from y700_charge.client import get_state, set_state


class Plugin:
    # The daemon owns the hardware; the plugin only proxies to it.
    async def get_state(self):
        return await asyncio.to_thread(get_state)

    async def set_bypass(self, enabled):
        return await asyncio.to_thread(set_state, bypass=enabled)

    async def set_protection(self, enabled):
        return await asyncio.to_thread(set_state, protection=enabled)

    async def set_threshold(self, value):
        return await asyncio.to_thread(set_state, threshold=value)
