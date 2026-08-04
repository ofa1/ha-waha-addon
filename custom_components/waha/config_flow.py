"""Config flow for the WAHA integration."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_API_KEY, CONF_HOST, CONF_PORT, CONF_SSL
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import WahaAuthError, WahaClient, WahaConnectionError, WahaError
from .const import CONF_SESSION, DEFAULT_PORT, DEFAULT_SESSION, DOMAIN

_LOGGER = logging.getLogger(__name__)

CREDENTIAL_SELECTOR = TextSelector(
    TextSelectorConfig(type=TextSelectorType.PASSWORD)
)


def _schema(defaults: Mapping[str, Any]) -> vol.Schema:
    """Build the connection form, pre-filled from `defaults`."""
    return vol.Schema(
        {
            vol.Required(
                CONF_HOST, default=defaults.get(CONF_HOST, vol.UNDEFINED)
            ): TextSelector(),
            vol.Required(
                CONF_PORT, default=defaults.get(CONF_PORT, DEFAULT_PORT)
            ): NumberSelector(
                NumberSelectorConfig(min=1, max=65535, mode=NumberSelectorMode.BOX)
            ),
            vol.Required(CONF_API_KEY): CREDENTIAL_SELECTOR,
            vol.Required(
                CONF_SESSION, default=defaults.get(CONF_SESSION, DEFAULT_SESSION)
            ): TextSelector(),
            vol.Required(
                CONF_SSL, default=defaults.get(CONF_SSL, False)
            ): BooleanSelector(),
        }
    )


def _clean_host(host: str) -> str:
    """Strip anything a user might paste around a bare hostname."""
    host = host.strip()
    for prefix in ("http://", "https://"):
        if host.lower().startswith(prefix):
            host = host[len(prefix) :]
    return host.strip("/").split("/")[0]


async def _async_validate(hass: Any, data: Mapping[str, Any]) -> None:
    """Confirm the credentials work, raising a WahaError otherwise."""
    client = WahaClient(
        async_get_clientsession(hass),
        _clean_host(data[CONF_HOST]),
        int(data[CONF_PORT]),
        data[CONF_API_KEY],
        use_ssl=bool(data.get(CONF_SSL, False)),
    )
    await client.async_list_sessions()


class WahaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the WAHA config flow."""

    VERSION = 1

    async def _async_process(
        self,
        user_input: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, dict[str, str]]:
        """Validate input, returning (cleaned data, errors)."""
        errors: dict[str, str] = {}
        cleaned = dict(user_input)
        cleaned[CONF_HOST] = _clean_host(cleaned[CONF_HOST])
        cleaned[CONF_PORT] = int(cleaned[CONF_PORT])

        if not cleaned[CONF_HOST]:
            errors[CONF_HOST] = "invalid_host"
            return None, errors

        try:
            await _async_validate(self.hass, cleaned)
        except WahaAuthError:
            errors["base"] = "invalid_auth"
        except WahaConnectionError:
            errors["base"] = "cannot_connect"
        except WahaError as err:
            _LOGGER.debug("Unexpected WAHA response during setup: %s", err)
            errors["base"] = "unknown"

        return (None if errors else cleaned), errors

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            cleaned, errors = await self._async_process(user_input)
            if cleaned is not None:
                await self.async_set_unique_id(
                    f"{cleaned[CONF_HOST].lower()}:{cleaned[CONF_PORT]}"
                )
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"WAHA ({cleaned[CONF_HOST]})", data=cleaned
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_schema(user_input or {}),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the host, port, key or default session of an existing entry."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            cleaned, errors = await self._async_process(user_input)
            if cleaned is not None:
                await self.async_set_unique_id(
                    f"{cleaned[CONF_HOST].lower()}:{cleaned[CONF_PORT]}"
                )
                self._abort_if_unique_id_mismatch(reason="wrong_server")
                return self.async_update_reload_and_abort(entry, data=cleaned)

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_schema(user_input or entry.data),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle an API key that stopped working."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a fresh API key."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            candidate = {**entry.data, CONF_API_KEY: user_input[CONF_API_KEY]}
            cleaned, errors = await self._async_process(candidate)
            if cleaned is not None:
                return self.async_update_reload_and_abort(entry, data=cleaned)

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_API_KEY): CREDENTIAL_SELECTOR}),
            description_placeholders={"host": entry.data[CONF_HOST]},
            errors=errors,
        )
