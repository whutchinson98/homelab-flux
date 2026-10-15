"""Seed a new volume without overwriting settings saved by Home Assistant.

HTTP settings moved to storage in 2026.8. Use the pinned release's schema and
store to initialize them, without leaving deprecated YAML or a five-minute
configuration trial. Recheck these imports when upgrading Home Assistant.
"""

import asyncio
import json
from pathlib import Path
import shutil


async def main():
    config = Path("/config")
    config.mkdir(parents=True, exist_ok=True)
    if not (config / "configuration.yaml").exists():
        shutil.copyfile("/bootstrap/configuration.yaml", config / "configuration.yaml")
    for name, initial in {
        "automations.yaml": "[]\n",
        "scripts.yaml": "{}\n",
        "scenes.yaml": "[]\n",
    }.items():
        if not (config / name).exists():
            (config / name).write_text(initial)

    if (config / ".storage/http").exists():
        print("Preserving existing Home Assistant HTTP settings")
        return

    from homeassistant.core import HomeAssistant
    from homeassistant.components.http.config import HTTPConfigStore, HTTP_STORAGE_SCHEMA

    hass = HomeAssistant(str(config))
    store = HTTPConfigStore(hass)
    settings = HTTP_STORAGE_SCHEMA(json.loads(Path("/bootstrap/http.json").read_text()))
    await store.async_migrate_yaml(settings)
    if store.pending is not None:
        await store.async_promote_pending()
    print("Initialized Home Assistant LAN listener and trusted Traefik proxy")


asyncio.run(main())
