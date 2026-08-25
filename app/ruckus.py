from urllib import response

import paramiko

from app.fortigate import results
from . import config

class RuckusClient:

    def __init__(self, host, username, password):
        self.host = host
        self.username = username
        self.password = password

    def connect(self):
        self.ssh = paramiko.SSHClient()
        self.ssh.set_missing_host_key_policy(
            paramiko.AutoAddPolicy()
        )

        self.ssh.connect(
            hostname=self.host,
            username=self.username,
            password=self.password,
            timeout=10
        )



    def run(self, cmd):
        shell = self.ssh.invoke_shell()
        import time
        time.sleep(2)

        if shell.recv_ready():
            shell.recv(65535)
        shell.send("skip-page-display\n")
        time.sleep(2)
        if shell.recv_ready():
            shell.recv(65535)
        shell.send(cmd + "\n")
        time.sleep(3)
        response = ""
        while shell.recv_ready():
            response += shell.recv(65535).decode(
                errors="ignore"
            )
        shell.close()
        return response

    def get_interfaces(self):
        return self.run("show interfaces brief")

    def get_vlans(self):
        return self.run("show vlan brief")

    def get_mac_table(self):
        return self.run("show mac-address")

    def close(self):
        self.ssh.close()


def collect_ruckus_cache():

    switches = [
        {
            "name": "ICX7180-1",
            "host": config.RUCKUS_SWITCH1
        },
        {
            "name": "ICX7180-2",
            "host": config.RUCKUS_SWITCH2
        }
    ]

    results = []

    for sw in switches:
        client = RuckusClient(
            host=sw["host"],
            username=config.RUCKUS_USER,
            password=config.RUCKUS_PASSWORD
        )
        try:
            client.connect()
            output = client.run("show interfaces brief")
            results.extend(
                parse_interfaces(
                    output,
                    sw["name"]
                )
            )
        finally:
            client.close()

    return results            

def parse_interfaces(output, switch_name):
    interfaces = []

    for line in output.splitlines():
        line = line.strip()
        if not line.startswith("1/"):
            continue
        parts = line.split()
        if len(parts) < 8:
            continue
        port = parts[0]
        link = parts[1]
        speed = parts[4]
        vlan = parts[7]

        description = ""
        if len(parts) > 10:
            description = " ".join(parts[10:])

        interfaces.append({
            "switch": switch_name,
            "port": port,
            "link": link,
            "speed": speed,
            "vlan": vlan,
            "description": description
        })

    return interfaces
