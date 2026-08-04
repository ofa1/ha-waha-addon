"""Session-status sensors for WAHA."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import WahaConfigEntry, WahaCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WahaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up a status sensor per WAHA session, including ones added later."""
    coordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def _async_add_new_sessions() -> None:
        new = set(coordinator.data or {}) - known
        if not new:
            return
        known.update(new)
        async_add_entities(
            WahaSessionSensor(coordinator, entry, name) for name in sorted(new)
        )

    entry.async_on_unload(coordinator.async_add_listener(_async_add_new_sessions))
    _async_add_new_sessions()


class WahaSessionSensor(CoordinatorEntity[WahaCoordinator], SensorEntity):
    """Reports the WhatsApp session state — WORKING, SCAN_QR_CODE, FAILED, ...

    Deliberately not a SensorDeviceClass.ENUM: an enum sensor raises when it
    sees a state outside its declared options, and WAHA is free to add a status
    in any release. A new status should show up in the UI, not break the entity.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "session_status"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: WahaCoordinator,
        entry: WahaConfigEntry,
        session_name: str,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator)
        self._session_name = session_name
        self._attr_unique_id = f"{entry.entry_id}_{session_name}_status"
        self._attr_translation_placeholders = {"session": session_name}
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="devlike.pro",
            model="WAHA",
            configuration_url=coordinator.client.base_url,
        )

    @property
    def _session(self) -> dict[str, Any] | None:
        """Return this session's record from the last poll."""
        return (self.coordinator.data or {}).get(self._session_name)

    @property
    def available(self) -> bool:
        """Only available while WAHA still reports this session."""
        return super().available and self._session is not None

    @property
    def native_value(self) -> str | None:
        """Return the session status."""
        session = self._session
        if session is None:
            return None
        status = session.get("status")
        return str(status) if status is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the engine and the paired account, when WAHA reports them."""
        session = self._session or {}
        attributes: dict[str, Any] = {"session": self._session_name}

        engine = session.get("engine")
        if isinstance(engine, dict):
            attributes["engine"] = engine.get("engine")
        elif engine is not None:
            attributes["engine"] = engine

        me = session.get("me")
        if isinstance(me, dict):
            attributes["account_id"] = me.get("id")
            attributes["account_name"] = me.get("pushName")

        return attributes
