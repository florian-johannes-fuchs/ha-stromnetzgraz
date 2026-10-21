"""The Stromnetz Graz integration."""
from __future__ import annotations

import asyncio
import logging
import os
import ssl
import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.const import (
    CONF_USERNAME,
    CONF_PASSWORD,
)

import sngraz
from sngraz import StromNetzGraz, InvalidLogin
from .const import DOMAIN

PLATFORMS = [Platform.SENSOR]
_LOGGER = logging.getLogger(__name__)


def _create_ssl_context() -> ssl.SSLContext:
    """Build the same SSL context sngraz would, but outside the event loop (loading certs blocks)."""
    sslcontext = ssl.create_default_context()
    sslcontext.load_verify_locations(
        cafile=os.path.join(os.path.dirname(sngraz.__file__), "certchain.crt")
    )
    return sslcontext


async def async_create_connection(
    hass: HomeAssistant, username: str, password: str
) -> StromNetzGraz:
    """Create the API connection without blocking the event loop."""
    sslcontext = await hass.async_add_executor_job(_create_ssl_context)
    websession = aiohttp.ClientSession(
        headers={aiohttp.hdrs.USER_AGENT: f"pySNGraz/{sngraz.__version__}"},
        connector=aiohttp.TCPConnector(ssl=sslcontext),
    )
    return StromNetzGraz(username, password, websession=websession)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Stromnetz Graz from a config entry."""

    conn = await async_create_connection(
        hass, entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD]
    )

    hass.data[DOMAIN] = conn

    try:
        await conn.authenticate()
    except asyncio.TimeoutError as err:
        raise ConfigEntryNotReady from err
    except aiohttp.ClientError as err:
        _LOGGER.error("Error connecting: %s ", err)
        return False
    except InvalidLogin as err:
        _LOGGER.error("Invalid Auth: %s", err)
        return False
    except Exception as exp:
        _LOGGER.error("Failed to login. %s", exp)
        return False

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_update_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update options."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await hass.data[DOMAIN].close_connection()

    return unload_ok
