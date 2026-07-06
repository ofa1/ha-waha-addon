# Browserless ARM image for Raspberry Pi / HAOS.
# Pin this after you confirm channel posting works in your environment, e.g.
# FROM devlikeapro/waha:2026.x.y-noweb-arm if WAHA publishes that tag shape.
FROM devlikeapro/waha:noweb-arm

ARG BUILD_VERSION
ARG BUILD_ARCH

LABEL \
  io.hass.name="WAHA WhatsApp API" \
  io.hass.description="Self-hosted WAHA WhatsApp HTTP API for Home Assistant OS" \
  io.hass.version="${BUILD_VERSION}" \
  io.hass.type="addon" \
  io.hass.arch="${BUILD_ARCH}"

COPY run.sh /run.sh
RUN chmod a+x /run.sh

# Keep WAHA's upstream ENTRYPOINT (/usr/bin/tini --) and replace only CMD.
CMD ["/run.sh"]
