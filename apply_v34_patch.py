from pathlib import Path
import re
import shutil

main = Path('app/main.py')
if not main.exists():
    raise SystemExit('ERROR: Run from the citypoint_cmdb_app_v3 folder; app/main.py not found.')

text = main.read_text(encoding='utf-8')
backup = main.with_suffix('.py.pre_v3_4_reconciliation_backup')
if not backup.exists():
    shutil.copy2(main, backup)

start = text.find("@app.get('/api/reconciliation')")
end = text.find("@app.get('/api/fortigate/report')", start)
if start < 0 or end < 0:
    raise SystemExit('ERROR: v3.3 reconciliation endpoint not found. Apply v3.3 first.')

endpoint = '''@app.get('/api/reconciliation')
def reconciliation():
    """Correlate customer to FortiGate by VLAN + subnet, not interface name."""
    customers = db.rows("""
      SELECT id, licensee, legal_name, booth_group, vlan_id, subnet_cidr,
             fortigate_interface
      FROM customers
      WHERE status='active'
      ORDER BY licensee
    """)
    interfaces = db.rows("SELECT * FROM fortigate_interfaces ORDER BY name")

    # fortigate.py derives cidr from interface IP + mask. Example:
    # interface 10.10.106.1/27 is stored as subnet 10.10.106.0/27.
    exact_index = {}
    vlan_index = {}
    subnet_index = {}
    for fg in interfaces:
        vlan_key = str(fg.get("vlan_id")) if fg.get("vlan_id") is not None else None
        subnet_key = fg.get("cidr") or None
        if vlan_key and subnet_key:
            exact_index.setdefault((vlan_key, subnet_key), []).append(fg)
        if vlan_key:
            vlan_index.setdefault(vlan_key, []).append(fg)
        if subnet_key:
            subnet_index.setdefault(subnet_key, []).append(fg)

    matched_interface_names = set()
    findings = []
    counts = {"match": 0, "warning": 0, "critical": 0, "missing": 0, "orphaned": 0}

    for c in customers:
        customer_vlan = str(c.get("vlan_id")) if c.get("vlan_id") is not None else None
        customer_subnet = c.get("subnet_cidr") or None
        fg = None
        status = None
        details = []

        if not customer_vlan or not customer_subnet:
            status = "MISSING_CUSTOMER_DATA"
            missing_fields = []
            if not customer_vlan:
                missing_fields.append("VLAN")
            if not customer_subnet:
                missing_fields.append("subnet")
            details.append("Customer is missing " + " and ".join(missing_fields))
            counts["missing"] += 1
        else:
            exact = exact_index.get((customer_vlan, customer_subnet), [])
            vlan_matches = vlan_index.get(customer_vlan, [])
            subnet_matches = subnet_index.get(customer_subnet, [])

            if len(exact) == 1:
                fg = exact[0]
                status = "MATCH"
                details.append("VLAN and subnet both match")
                counts["match"] += 1
            elif len(exact) > 1:
                fg = exact[0]
                status = "WARNING_DUPLICATE_FG_MATCH"
                details.append(f"{len(exact)} FortiGate interfaces share the same VLAN and subnet")
                counts["warning"] += 1
            elif vlan_matches and not subnet_matches:
                fg = vlan_matches[0]
                status = "WARNING_VLAN_ONLY"
                details.append(f"VLAN {customer_vlan} matches, but customer subnet {customer_subnet} does not match FortiGate subnet {fg.get('cidr')}")
                if len(vlan_matches) > 1:
                    details.append(f"{len(vlan_matches)} FortiGate interfaces use this VLAN")
                counts["warning"] += 1
            elif subnet_matches and not vlan_matches:
                fg = subnet_matches[0]
                status = "WARNING_SUBNET_ONLY"
                details.append(f"Subnet {customer_subnet} matches, but customer VLAN {customer_vlan} does not match FortiGate VLAN {fg.get('vlan_id')}")
                if len(subnet_matches) > 1:
                    details.append(f"{len(subnet_matches)} FortiGate interfaces use this subnet")
                counts["warning"] += 1
            elif vlan_matches and subnet_matches:
                # VLAN and subnet each exist, but on different FG interfaces.
                fg = vlan_matches[0]
                status = "CRITICAL_SPLIT_MATCH"
                subnet_ifaces = ", ".join(x.get("name", "") for x in subnet_matches)
                details.append(f"VLAN matches interface {fg.get('name')}, but subnet matches different interface(s): {subnet_ifaces}")
                counts["critical"] += 1
            else:
                status = "MISSING_FG_INTERFACE"
                details.append("No FortiGate interface matches the customer VLAN or subnet")
                counts["missing"] += 1

        if fg and fg.get("name"):
            matched_interface_names.add(fg["name"])

        findings.append({
            "customer_id": c.get("id"),
            "licensee": c.get("licensee"),
            "booth_group": c.get("booth_group"),
            "customer_vlan": c.get("vlan_id"),
            "customer_subnet": customer_subnet,
            "fortigate_interface": fg.get("name") if fg else None,
            "fg_vlan": fg.get("vlan_id") if fg else None,
            "fg_interface_ip": fg.get("gateway") if fg else None,
            "fg_subnet": fg.get("cidr") if fg else None,
            "interface_status": fg.get("interface_status") if fg else None,
            "policy_id": fg.get("policy_id") if fg else None,
            "policy_name": fg.get("policy_name") if fg else None,
            "policy_status": fg.get("policy_status") if fg else None,
            "reconciliation_status": status,
            "details": "; ".join(details),
        })

    for fg in interfaces:
        if fg.get("name") not in matched_interface_names:
            counts["orphaned"] += 1
            findings.append({
                "customer_id": None,
                "licensee": None,
                "booth_group": None,
                "customer_vlan": None,
                "customer_subnet": None,
                "fortigate_interface": fg.get("name"),
                "fg_vlan": fg.get("vlan_id"),
                "fg_interface_ip": fg.get("gateway"),
                "fg_subnet": fg.get("cidr"),
                "interface_status": fg.get("interface_status"),
                "policy_id": fg.get("policy_id"),
                "policy_name": fg.get("policy_name"),
                "policy_status": fg.get("policy_status"),
                "reconciliation_status": "ORPHANED_INTERFACE",
                "details": "FortiGate interface did not match an active customer by VLAN + subnet",
            })

    return {"summary": counts, "results": findings}

'''
text = text[:start] + endpoint + text[end:]

# Update reconciliation summary cards from old v3.3 names to v3.4 names.
old_js_start = text.find('async function loadReconciliation()')
old_js_end = text.find('async function toggle(enable,apply)', old_js_start)
if old_js_start < 0 or old_js_end < 0:
    raise SystemExit('ERROR: Reconciliation JavaScript function not found.')
new_js = '''async function loadReconciliation(){let d=await j('/api/reconciliation');let s=d.summary||{};reconSummary.innerHTML=`<div class="dashcard"><h3>Matched</h3><div class="dashvalue">${s.match||0}</div></div><div class="dashcard"><h3>Warnings</h3><div class="dashvalue">${s.warning||0}</div></div><div class="dashcard"><h3>Critical</h3><div class="dashvalue">${s.critical||0}</div></div><div class="dashcard"><h3>Missing</h3><div class="dashvalue">${s.missing||0}</div></div><div class="dashcard"><h3>Orphaned FG</h3><div class="dashvalue">${s.orphaned||0}</div></div>`;reconciliation.innerHTML=table(d.results||[])}'''
text = text[:old_js_start] + new_js + text[old_js_end:]

main.write_text(text, encoding='utf-8')
print('SUCCESS: v3.4 VLAN + subnet reconciliation patch applied.')
print(f'Backup: {backup}')
print('Matching no longer depends on the customer-selected interface name.')
print('FortiGate interface IP is converted to its network CIDR by the existing parser.')
