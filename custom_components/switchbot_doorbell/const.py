"""Constants for the SwitchBot Video Doorbell integration.

Alle Werte hier stammen aus dem Reverse Engineering der offiziellen SwitchBot-
Android-App (v10.0.1). Details/Quellen siehe FINDINGS.md im mitm-Repo.
"""

DOMAIN = "switchbot_doorbell"

ACCOUNT_HOST = "https://account.api.switchbot.net"
WONDER_HOST = "https://wonderlabs.eu.api.switchbot.net"

# App-weite OAuth-artige Konstanten (kein Nutzer-Secret, siehe FINDINGS.md Abschnitt 8
# - bewusste Entscheidung, das hier fest zu verdrahten).
CLIENT_ID = "5nnwmhmsa9xxskm14hd85lm9bm"
CLIENT_SECRET = "vzxjw7rvmduka4rlysdcv0bfke70icql33ol1pvr"
GRANT_TYPE = "password"

# Property-IDs auf dem Kamera-Sub-Device (device_type W1050001, NICHT die
# Signaling-Hub-ID W1050000 - siehe FINDINGS.md Abschnitt 3).
PROP_BATTERY = 820
PROP_MUTE = 8433

DEFAULT_MUTE_MINUTES = 720  # 12h, wie das Maximum in der offiziellen App
MAX_MUTE_MINUTES = 720
DEFAULT_SCAN_INTERVAL_SECONDS = 300

SERVICE_MUTE_FOR = "mute_for"
ATTR_MINUTES = "minutes"

CONF_GROUP_ID = "group_id"
CONF_DEVICE_ID = "device_id"
CONF_DEVICE_NAME = "device_name"
CONF_SUBTOPIC = "subtopic"
CONF_PUBTOPIC = "pubtopic"
CONF_ACCESS_TOKEN = "access_token"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_USER_ID = "user_id"
CONF_APP_DEVICE_ID = "app_device_id"
