"""Constants for the WAHA integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "waha"

DEFAULT_PORT: Final = 3000
DEFAULT_SESSION: Final = "default"

CONF_SESSION: Final = "session"

# Service names.
SERVICE_SEND_TEXT: Final = "send_text"
SERVICE_SEND_MEDIA: Final = "send_media"

# Service field names.
ATTR_CONFIG_ENTRY_ID: Final = "config_entry_id"
ATTR_CHAT_ID: Final = "chat_id"
ATTR_SESSION: Final = "session"
ATTR_TEXT: Final = "text"
ATTR_URL: Final = "url"
ATTR_MIMETYPE: Final = "mimetype"
ATTR_FILENAME: Final = "filename"
ATTR_CAPTION: Final = "caption"
ATTR_LINK_PREVIEW: Final = "link_preview"
