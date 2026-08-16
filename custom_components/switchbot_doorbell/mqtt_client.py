"""AWS-IoT-MQTT-Client fuer Klingel-Push-Events.

EXPERIMENTELL: Zertifikats-Endpoint (/wonder/user/policyCer), PKCS12-Passwort
("12345678") und Topic-Namensschema (switchlink/<mac>/link_to_app) sind aus der
APK reverse-engineered, aber die exakte Nutzlast eines echten Klingel-Events ist
NICHT live verifiziert (siehe FINDINGS.md Abschnitt 5/7). Das Parsing hier ist
deshalb bewusst tolerant/best-effort und loggt jede empfangene Nachricht komplett,
damit man es nach dem ersten echten Klingeln bei Bedarf nachschaerfen kann.
"""
from __future__ import annotations

import json
import logging
import tempfile
from collections.abc import Callable
from pathlib import Path

from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, pkcs12
from homeassistant.core import HomeAssistant

from .api import SwitchBotApiClient

_LOGGER = logging.getLogger(__name__)

PKCS12_PASSWORD = b"12345678"

# switchbot_config.json (prd, EU): mqttEndpoint-Praefix. Region ist eine Annahme
# (alle anderen Endpunkte dieser Integration sind EU) - falls die Verbindung
# fehlschlaegt, ist das der erste Verdaechtige.
MQTT_ENDPOINT_PREFIX = "a2alhn2dfztqv9"
MQTT_REGION = "eu-central-1"
MQTT_HOST = f"{MQTT_ENDPOINT_PREFIX}-ats.iot.{MQTT_REGION}.amazonaws.com"
MQTT_PORT = 8883

RING_HINTS = ("RING", "ring", "doorbell_ring", "DOORBELL_RING")


class SwitchBotMqttClient:
    """Verbindet per Client-Zertifikat zu AWS IoT und meldet Klingel-Events."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: SwitchBotApiClient,
        access_token_getter: Callable[[], str],
        subtopic: str,
        on_ring: Callable[[], None],
    ) -> None:
        self._hass = hass
        self._api = api
        self._get_token = access_token_getter
        self._subtopic = subtopic
        self._on_ring = on_ring
        self._mqtt_client = None
        self._cert_file: Path | None = None
        self._key_file: Path | None = None
        self.connected = False

    async def async_start(self) -> None:
        if not self._subtopic:
            _LOGGER.warning(
                "Kein MQTT-Subtopic bekannt - Klingel-Push wird nicht gestartet."
            )
            return

        cert_b64 = await self._api.get_mqtt_cert(self._get_token())
        await self._hass.async_add_executor_job(self._prepare_cert_files, cert_b64)
        await self._hass.async_add_executor_job(self._connect)

    def _prepare_cert_files(self, cert_b64: str) -> None:
        import base64

        pkcs12_bytes = base64.b64decode(cert_b64)
        private_key, certificate, _extra_certs = pkcs12.load_key_and_certificates(
            pkcs12_bytes, PKCS12_PASSWORD
        )
        if private_key is None or certificate is None:
            raise ValueError("PKCS12-Blob enthielt keinen Key/Zertifikat.")

        cert_pem = certificate.public_bytes(Encoding.PEM)
        key_pem = private_key.private_bytes(Encoding.PEM, PrivateFormat.TraditionalOpenSSL, NoEncryption())

        cert_tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pem")
        cert_tmp.write(cert_pem)
        cert_tmp.close()
        key_tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pem")
        key_tmp.write(key_pem)
        key_tmp.close()

        self._cert_file = Path(cert_tmp.name)
        self._key_file = Path(key_tmp.name)

    def _connect(self) -> None:
        import paho.mqtt.client as mqtt

        assert self._cert_file is not None and self._key_file is not None

        client_id = f"ha-switchbot-doorbell-{id(self)}"
        # VERSION1 behaelt die "alten" Callback-Signaturen (client, userdata, flags, rc)
        # bei - paho-mqtt >=2.0 aendert sonst die Signatur (reason_code/properties statt rc).
        client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION1,
            client_id=client_id,
            protocol=mqtt.MQTTv311,
        )
        client.tls_set(
            certfile=str(self._cert_file),
            keyfile=str(self._key_file),
        )

        def on_connect(_client, _userdata, _flags, rc):
            if rc == 0:
                self.connected = True
                _LOGGER.info("MQTT verbunden, abonniere %s", self._subtopic)
                client.subscribe(self._subtopic)
            else:
                _LOGGER.error("MQTT-Verbindung fehlgeschlagen, rc=%s", rc)

        def on_disconnect(_client, _userdata, rc):
            self.connected = False
            _LOGGER.warning("MQTT getrennt, rc=%s", rc)

        def on_message(_client, _userdata, msg):
            raw = msg.payload.decode("utf-8", errors="replace")
            _LOGGER.info("MQTT-Nachricht auf %s: %s", msg.topic, raw)
            if self._looks_like_ring(raw):
                self._hass.loop.call_soon_threadsafe(self._on_ring)

        client.on_connect = on_connect
        client.on_disconnect = on_disconnect
        client.on_message = on_message

        client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
        client.loop_start()
        self._mqtt_client = client

    @staticmethod
    def _looks_like_ring(raw: str) -> bool:
        if any(hint in raw for hint in RING_HINTS):
            return True
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return False
        haystack = json.dumps(data).lower()
        return "ring" in haystack

    async def async_stop(self) -> None:
        if self._mqtt_client is not None:
            await self._hass.async_add_executor_job(self._mqtt_client.disconnect)
            await self._hass.async_add_executor_job(self._mqtt_client.loop_stop)
        for f in (self._cert_file, self._key_file):
            if f is not None:
                f.unlink(missing_ok=True)
