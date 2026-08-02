# Browserless ARM image for Raspberry Pi / HAOS.
#
# Pinned deliberately. The floating `noweb-arm` tag combined with the add-on's
# auto_update means a Supervisor rebuild could pull an untested upstream WAHA
# without anyone initiating it. Bump this tag on purpose after reading WAHA's
# release notes; see https://hub.docker.com/r/devlikeapro/waha/tags
FROM devlikeapro/waha:noweb-arm-2026.7.2
USER root

ARG BUILD_VERSION
ARG BUILD_ARCH

LABEL \
  io.hass.name="WAHA WhatsApp API" \
  io.hass.description="Self-hosted WAHA WhatsApp HTTP API for Home Assistant OS" \
  io.hass.version="${BUILD_VERSION}" \
  io.hass.type="addon" \
  io.hass.arch="${BUILD_ARCH}"

RUN apt-get update \
    && apt-get install -y --no-install-recommends nginx \
    && rm -rf /var/lib/apt/lists/*

COPY run.sh /run.sh
COPY ingress.conf.template /etc/nginx/templates/waha-ingress.conf.template
COPY channel-test.html /usr/share/waha-ingress/channel-test.html
RUN chmod a+x /run.sh

# Drives the Supervisor watchdog. The config.yaml `watchdog:` key is obsolete;
# Home Assistant reads container health instead. Probing /healthz goes through
# Nginx *and* on to WAHA, so "unhealthy" means WhatsApp stopped answering
# rather than just that the proxy is listening. Node is used because it is
# guaranteed present in the WAHA image; curl is not.
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
  CMD node -e "require('http').get('http://127.0.0.1:8099/healthz',r=>process.exit(r.statusCode===200?0:1)).on('error',()=>process.exit(1))"

# Keep WAHA's upstream ENTRYPOINT (/usr/bin/tini --) and replace only CMD.
CMD ["/run.sh"]
