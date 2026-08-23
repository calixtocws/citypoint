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

                print(
                    f"Found zone={zone['name']} "
                    f"zone_id={self.zone_id} "
                    f"ssid={wlan['name']} "
                    f"wlan_id={self.wlan_id}"
                )

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
    
    
    #def collect_smartzone_cache():
    #    sz = SmartZoneClient()
    #    sz.login()
    #    dpsks = sz.get_dpsks()
    #    return dpsks


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

if __name__ == "__main__":
    import json
    sz = SmartZoneClient()
    sz.login()
    sz.resolve_ids()
    print("Zone ID:", sz.zone_id)
    print("WLAN ID:", sz.wlan_id)
    data = sz.get_dpsks()
    print(json.dumps(data, indent=2))