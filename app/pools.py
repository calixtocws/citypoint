import ipaddress
from . import db
SPECIAL_SUBNETS = ["10.10.98.0/23","10.10.100.0/24","10.10.101.0/24","10.10.102.0/24","10.10.103.0/24","10.10.104.0/24","10.10.105.0/24","10.10.112.0/20","10.10.128.0/22"]
def first_usable(cidr): return str(next(ipaddress.ip_network(cidr, strict=False).hosts()))
def mask(cidr): return str(ipaddress.ip_network(cidr, strict=False).netmask)
def generated_subnets():
    out=list(SPECIAL_SUBNETS)
    for third in range(106,111):
        for fourth in range(0,225,32): out.append(f"10.10.{third}.{fourth}/27")
    return out
def initialize_pools():
    for vlan in list(range(190,200))+list(range(300,351)):
        db.execute("INSERT OR IGNORE INTO vlans(vlan_id,status) VALUES (?, 'available')", (vlan,))
    for cidr in generated_subnets():
        db.execute("INSERT OR IGNORE INTO subnets(cidr,gateway,mask,status) VALUES (?, ?, ?, 'available')", (cidr, first_usable(cidr), mask(cidr)))
def refresh_statuses():

    db.execute("UPDATE booths SET status='available'")
    db.execute("UPDATE vlans SET status='available'")
    db.execute("UPDATE subnets SET status='available'")

    for r in db.rows(
        """
        SELECT licensee,
               booth_group,
               vlan_id,
               subnet_cidr
        FROM customers
        WHERE status='active'
        """
    ):

        if r.get('booth_group'):
            db.execute(
                "UPDATE booths SET status='used' WHERE booth_group=?",
                (r['booth_group'],)
            )

        if r.get('vlan_id'):
            db.execute(
                "UPDATE vlans SET status='used' WHERE vlan_id=?",
                (r['vlan_id'],)
            )

        if r.get('subnet_cidr'):
            db.execute(
                "UPDATE subnets SET status='used' WHERE cidr=?",
                (r['subnet_cidr'],)
            )

    #
    # Reserved infrastructure VLANs
    #
    db.execute(
        """
        UPDATE vlans
        SET status='infrastructure'
        WHERE vlan_id BETWEEN 191 AND 199
           OR vlan_id = 900
        """
    )
