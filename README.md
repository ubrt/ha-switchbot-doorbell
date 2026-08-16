# SwitchBot Video Doorbell (Home Assistant Integration, v1)

Reverse-engineerte, inoffizielle Home-Assistant-Integration für die SwitchBot Video
Doorbell. Kein offizielles SwitchBot-Projekt.

## Installation via HACS

Dieses Repo als "Custom repository" (Kategorie: Integration) in HACS hinzufügen,
dann "SwitchBot Video Doorbell" installieren und Home Assistant neu starten.

## Umfang v1

- `sensor.<name>_battery` — Batterie in % (Poll-Intervall 5 min).
- `switch.<name>_mute` — an = gemutet. Einschalten mutet für
  `DEFAULT_MUTE_MINUTES` (Standard 60 min, siehe `const.py`); Service
  `switchbot_doorbell.mute_for` erlaubt eine eigene Dauer in Minuten.
- `binary_sensor.<name>_ring` — **experimentell**, per MQTT-Push (AWS IoT),
  schaltet kurz auf "on" und nach 5s automatisch zurück. Die genaue
  Nutzlast-Struktur eines echten Klingel-Events ist NICHT live verifiziert —
  das Parsing in `mqtt_client.py` ist bewusst tolerant und loggt jede
  empfangene MQTT-Nachricht komplett auf INFO-Level. **Nach dem ersten echten
  Klingeln bitte den Log prüfen** und bei Bedarf `RING_HINTS`/
  `_looks_like_ring()` in `mqtt_client.py` nachschärfen.
- Kein Live-Video, kein Standbild (die Doorbell hängt bei einer echten
  WebRTC-Verbindung nie Videomaterial an, obwohl der Transport-Handshake
  korrekt durchläuft; Standbild-Endpoint liefert aktuell serverseitig 502).

## Einrichtung

Nach der Installation über HACS: Einstellungen → Geräte & Dienste →
Integration hinzufügen → "SwitchBot Video Doorbell" → SwitchBot-Account-Login.
Gruppe/Gerät werden automatisch erkannt (bzw. Auswahl, falls mehrere
vorhanden).

## Bekannte offene Punkte

- MQTT-Broker-Endpoint (`mqtt_client.py`, `MQTT_ENDPOINT_PREFIX`/`MQTT_REGION`)
  ist aus `switchbot_config.json` übernommen, aber die Region ist eine Annahme
  (EU) — falls die Verbindung fehlschlägt, zuerst hier nachsehen.
- Login-Flow unterstützt aktuell **kein Captcha** (Server-Code 2024). Falls das
  auftritt, schlägt der Config-Flow mit `cannot_connect` fehl.
- `compute_mute_until_ms()` nimmt Unix-**Millisekunden** an (konsistent mit
  allen anderen live beobachteten Zeitstempeln dieser API) — beim ersten
  echten Mute-Test kurz per `switch.mute` prüfen, ob die Doorbell tatsächlich
  für die erwartete Dauer stumm bleibt.
