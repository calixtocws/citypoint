# app/smartzone.py

import requests
import urllib3
from . import config

urllib3.disable_warnings()



class SmartZoneClient:

    def __init__(self):

        self.base_url = config.SMARTZONE_URL
        self.session = requests.Session()

        self.zone_id = None
        self.wlan_id = None

    def login(self):

        url = f"{self.base_url}/wsg/api/public/v11_0/session"

        body = {
            "username": config.SMARTZONE_USER,
            "password": config.SMARTZONE_PASSWORD
        }

        r = self.session.post(
            url,
            json=body,
            verify=False,
            timeout=30
        )

        r.raise_for_status()

    def get_zones(self):

        r = self.session.get(
            f"{self.base_url}/wsg/api/public/v11_0/rkszones",
            verify=False,
            timeout=30
        )

        r.raise_for_status()

        return r.json()

    def get_wlans(self, zone_id):

        r = self.session.get(
            f"{self.base_url}/wsg/api/public/v11_0/rkszones/{zone_id}/wlans",
            verify=False,
            timeout=30
        )
        r.raise_for_status()
        return r.json()

    def resolve_ids(self):
        zones = self.get_zones()
        for zone in zones.get("list", []):

            if zone["name"] != config.SMARTZONE_ZONE_NAME:
                continue

            self.zone_id = zone["id"]

            wlans = self.get_wlans(self.zone_id)

            for wlan in wlans.get("list", []):

                if wlan["name"] != config.SMARTZONE_SSID:
                    continue

                self.wlan_id = wlan["id"]

                return

        raise Exception(
            f"Cannot locate "
            f"{config.SMARTZONE_ZONE_NAME}/"
            f"{config.SMARTZONE_SSID}"
        )

    def get_dpsks(self):
        if not self.zone_id or not self.wlan_id:
            self.resolve_ids()

        r = self.session.get(
            f"{self.base_url}/wsg/api/public/v11_0/"
            f"rkszones/{self.zone_id}/"
            f"wlans/{self.wlan_id}/dpsk",
            verify=False,
            timeout=30
        )
        r.raise_for_status()
        return r.json()
    



def collect_smartzone_cache():
    sz = SmartZoneClient()
    sz.login()
    raw = sz.get_dpsks()
    results = []
    for row in raw.get("list", []):
        results.append({
            "id": row.get("id"),
            "vlan": row.get("vlanId"),
            "username": row.get("userName"),
            "passphrase": row.get("passphrase"),
            "created": row.get("creationDateTime"),
            "expires": row.get("expirationDateTime")
        })
    return results

import secrets
import string


def generate_passphrase(length=8):
    alphabet = (
        string.ascii_letters +
        string.digits
    )

    return ''.join(
        secrets.choice(alphabet)
        for _ in range(length)
    )


def sanitize_username(name):
    return (
        name.strip()
            .replace(" ", "_")
            .replace("/", "_")
            .replace("\\", "_")
    )



def create_smartzone_dpsk(
    session,
    base_url,
    api_version,
    zone_id,
    wlan_id,
    vlan,
    username,
    passphrase,
    group_enabled=True,
    service_ticket=None,
):
    url = (
        f"{base_url}/wsg/api/public/{api_version}"
        f"/rkszones/{zone_id}"
        f"/wlans/{wlan_id}"
        f"/dpsk/batchGenUnbound"
    )

    payload = {
        "amount": 1,
        "userName": username,
        "passphrase": passphrase,
        "vlanId": int(vlan),
        "groupDpsk": bool(group_enabled),
    }

    params = {}

    if service_ticket:
        params["serviceTicket"] = service_ticket

    response = session.post(
        url,
        params=params,
        json=payload,
        timeout=30,
        verify=False,
    )

    if not response.ok:
        raise RuntimeError(
            "SmartZone DPSK creation failed: "
            f"HTTP {response.status_code}: "
            f"{response.text}"
        )

    if not response.content:
        return {
            "status": "created"
        }

    try:
        return response.json()
    except ValueError:
        return {
            "status": "created",
            "response": response.text,
        }
        
