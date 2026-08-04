"""The WAHA WhatsApp API integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_API_KEY, CONF_HOST, CONF_PORT, CONF_SSL, Platform
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import WahaAuthError, WahaClient, WahaError
from .const import (
    ATTR_CAPTION,
    ATTR_CHAT_ID,
    ATTR_CONFIG_ENTRY_ID,
    ATTR_FILENAME,
    ATTR_LINK_PREVIEW,
    ATTR_MIMETYPE,
    ATTR_SESSION,
    ATTR_TEXT,
    ATTR_URL,
    CONF_SESSION,
    DEFAULT_SESSION,
    DOMAIN,
    SERVICE_SEND_MEDIA,
    SERVICE_SEND_TEXT,
)
from .coordinator import WahaConfigEntry, WahaCoordinator

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS: list[Platform] = [Platform.SENSOR]

_BASE_FIELDS = {
    vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
    vol.Required(ATTR_CHAT_ID): cv.string,
    vol.Optional(ATTR_SESSION): cv.string,
}

SEND_TEXT_SCHEMA = vol.Schema(
    {
        **_BASE_FIELDS,
        vol.Required(ATTR_TEXT): cv.string,
        vol.Optional(ATTR_LINK_PREVIEW): cv.boolean,
    }
)

SEND_MEDIA_SCHEMA = vol.Schema(
    {
        **_BASE_FIELDS,
        vol.Required(ATTR_URL): cv.string,
        vol.Required(ATTR_FILENAME): cv.string,
        vol.Optional(ATTR_MIMETYPE): cv.string,
        vol.Optional(ATTR_CAPTION): cv.string,
    }
)


def _async_resolve_entry(hass: HomeAssistant, call: ServiceCall) -> WahaConfigEntry:
    """Pick the config entry a service call targets.

    `config_entry_id` is optional because almost everyone runs one WAHA; it
    only becomes required once a second one exists, and the error says so.
    """
    entry_id = call.data.get(ATTR_CONFIG_ENTRY_ID)
    if entry_id is not None:
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.domain != DOMAIN:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="entry_not_found",
                translation_placeholders={"entry_id": entry_id},
            )
        if entry.state is not ConfigEntryState.LOADED:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="entry_not_loaded",
                translation_placeholders={"title": entry.title},
            )
        return entry

    loaded = hass.config_entries.async_loaded_entries(DOMAIN)
    if len(loaded) == 1:
        return loaded[0]
    if not loaded:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="no_entries"
        )
    raise ServiceValidationError(
        translation_domain=DOMAIN, translation_key="entry_id_required"
    )


def _async_call_context(
    hass: HomeAssistant, call: ServiceCall
) -> tuple[WahaClient, str]:
    """Return the client and the session name for this call."""
    entry = _async_resolve_entry(hass, call)
    coordinator: WahaCoordinator = entry.runtime_data
    session = call.data.get(ATTR_SESSION) or entry.data.get(
        CONF_SESSION, DEFAULT_SESSION
    )
    return coordinator.client, session


def _async_register_services(hass: HomeAssistant) -> None:
    """Register the WAHA services."""

    async def _handle_send_text(call: ServiceCall) -> ServiceResponse:
        client, session = _async_call_context(hass, call)
        try:
            result = await client.async_send_text(
                session=session,
                chat_id=call.data[ATTR_CHAT_ID],
                text=call.data[ATTR_TEXT],
                link_preview=call.data.get(ATTR_LINK_PREVIEW),
            )
        except WahaAuthError as err:
            raise HomeAssistantError(str(err)) from err
        except WahaError as err:
            raise HomeAssistantError(f"WAHA rejected the message: {err}") from err
        return _as_response(result)

    async def _handle_send_media(call: ServiceCall) -> ServiceResponse:
        client, session = _async_call_context(hass, call)
        try:
            result = await client.async_send_media(
                session=session,
                chat_id=call.data[ATTR_CHAT_ID],
                url=call.data[ATTR_URL],
                mimetype=call.data.get(ATTR_MIMETYPE),
                filename=call.data[ATTR_FILENAME],
                caption=call.data.get(ATTR_CAPTION),
            )
        except WahaAuthError as err:
            raise HomeAssistantError(str(err)) from err
        except WahaError as err:
            # Never include the payload: the URL may carry a bearer token.
            raise HomeAssistantError(f"WAHA rejected the media: {err}") from err
        return _as_response(result)

    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_TEXT,
        _handle_send_text,
        schema=SEND_TEXT_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_MEDIA,
        _handle_send_media,
        schema=SEND_MEDIA_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )


def _as_response(result: Any) -> ServiceResponse:
    """Normalise a WAHA reply into a service response."""
    if isinstance(result, dict):
        return result
    return {"result": result}


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register services once, independently of any config entry."""
    _async_register_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: WahaConfigEntry) -> bool:
    """Set up WAHA from a config entry."""
    client = WahaClient(
        async_get_clientsession(hass),
        entry.data[CONF_HOST],
        int(entry.data[CONF_PORT]),
        entry.data[CONF_API_KEY],
        use_ssl=bool(entry.data.get(CONF_SSL, False)),
    )

    coordinator = WahaCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: WahaConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
