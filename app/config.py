import os
from dotenv import load_dotenv
load_dotenv()
DATABASE_PATH = os.getenv("DATABASE_PATH", "./data/citypoint_cmdb.sqlite3")
FORTIGATE_BASE_URL = os.getenv("FORTIGATE_BASE_URL", "").rstrip("/")
FORTIGATE_API_TOKEN = os.getenv("FORTIGATE_API_TOKEN", "")
FORTIGATE_VDOM = os.getenv("FORTIGATE_VDOM", "root")
FORTIGATE_VERIFY_SSL = os.getenv("FORTIGATE_VERIFY_SSL", "false").lower() in ("1", "true", "yes")
FORTIGATE_SDWAN_INTERFACE = os.getenv("FORTIGATE_SDWAN_INTERFACE", "sd-wan")
ENABLE_FORTIGATE_WRITE = os.getenv("ENABLE_FORTIGATE_WRITE", "false").lower() in ("1", "true", "yes")




RUCKUS_SWITCH1 = os.getenv("RUCKUS_SWITCH1", "")
RUCKUS_SWITCH2 = os.getenv("RUCKUS_SWITCH2", "")
RUCKUS_USER = os.getenv("RUCKUS_USER", "")
RUCKUS_PASSWORD = os.getenv("RUCKUS_PASSWORD", "")



SMARTZONE_URL = "https://10.40.53.90:8443"
SMARTZONE_USER = "calixto"
SMARTZONE_PASSWORD = "golf@zebra1"

SMARTZONE_ZONE_NAME = "Citypoint"
SMARTZONE_SSID = "Dekalb_Market"


SMARTZONE_DPSK_WLANS = [
    {
        "zone": "Citypoint",
        "ssid": "Dekalb_Market"
    }
]