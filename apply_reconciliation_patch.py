from pathlib import Path
import shutil

main = Path('app/main.py')
if not main.exists():
    raise SystemExit('ERROR: Run this script from the citypoint_cmdb_app_v3 folder. app/main.py was not found.')

text = main.read_text(encoding='utf-8')
backup = main.with_suffix('.py.pre_v3_3_reconciliation_backup')
if not backup.exists():
    shutil.copy2(main, backup)

# Add reconciliation API endpoint before FortiGate report endpoint.
if "@app.get('/api/reconciliation')" not in text:
    marker = "@app.get('/api/fortigate/report')\n"
    endpoint = '''@app.get('/api/reconciliation')
def reconciliation():
    customers = db.rows("""
      SELECT id, licensee, legal_name, booth_group, vlan_id, subnet_cidr,
             fortigate_interface
      FROM customers
      WHERE status='active'
      ORDER BY licensee
    """)
    interfaces = db.rows("SELECT * FROM fortigate_interfaces ORDER BY name")
    by_name = {r["name"]: r for r in interfaces}
    assigned_names = set()
    findings = []
    counts = {"match": 0, "review": 0, "missing": 0, "unassigned": 0}

    for c in customers:
        interface_name = (c.get("fortigate_interface") or "").strip()
        fg = by_name.get(interface_name) if interface_name else None
        status = "MATCH"
        details = []

        if not interface_name:
            status = "MISSING_INTERFACE_ASSIGNMENT"
            details.append("Customer has no FortiGate interface selected")
        elif not fg:
            status = "INTERFACE_NOT_IN_CACHE"
            details.append("Selected interface was not found in the latest FortiGate cache")
        else:
            assigned_names.add(interface_name)
            if c.get("vlan_id") is not None and str(c.get("vlan_id")) != str(fg.get("vlan_id")):
                status = "VLAN_MISMATCH"
                details.append(f"Customer VLAN {c.get('vlan_id')} differs from FortiGate VLAN {fg.get('vlan_id')}")
            if c.get("subnet_cidr") and fg.get("cidr") and c.get("subnet_cidr") != fg.get("cidr"):
                if status == "MATCH":
                    status = "SUBNET_MISMATCH"
                else:
                    status = "VLAN_AND_SUBNET_MISMATCH"
                details.append(f"Customer subnet {c.get('subnet_cidr')} differs from FortiGate subnet {fg.get('cidr')}")

        if status == "MATCH":
            counts["match"] += 1
        elif status in ("MISSING_INTERFACE_ASSIGNMENT", "INTERFACE_NOT_IN_CACHE"):
            counts["missing"] += 1
        else:
            counts["review"] += 1

        findings.append({
            "customer_id": c.get("id"),
            "licensee": c.get("licensee"),
            "booth_group": c.get("booth_group"),
            "customer_vlan": c.get("vlan_id"),
            "customer_subnet": c.get("subnet_cidr"),
            "fortigate_interface": interface_name,
            "fg_vlan": fg.get("vlan_id") if fg else None,
            "fg_subnet": fg.get("cidr") if fg else None,
            "interface_status": fg.get("interface_status") if fg else None,
            "policy_id": fg.get("policy_id") if fg else None,
            "policy_name": fg.get("policy_name") if fg else None,
            "policy_status": fg.get("policy_status") if fg else None,
            "reconciliation_status": status,
            "details": "; ".join(details),
        })

    for fg in interfaces:
        if fg.get("name") not in assigned_names:
            counts["unassigned"] += 1
            findings.append({
                "customer_id": None,
                "licensee": None,
                "booth_group": None,
                "customer_vlan": None,
                "customer_subnet": None,
                "fortigate_interface": fg.get("name"),
                "fg_vlan": fg.get("vlan_id"),
                "fg_subnet": fg.get("cidr"),
                "interface_status": fg.get("interface_status"),
                "policy_id": fg.get("policy_id"),
                "policy_name": fg.get("policy_name"),
                "policy_status": fg.get("policy_status"),
                "reconciliation_status": "UNASSIGNED_INTERFACE",
                "details": "FortiGate interface is not assigned to an active customer",
            })

    return {"summary": counts, "results": findings}

'''
    if marker not in text:
        raise SystemExit('ERROR: Could not find FortiGate report endpoint marker. No changes made.')
    text = text.replace(marker, endpoint + marker, 1)

# Insert reconciliation card/section after FortiGate card, before operations card.
if '<h2>FortiGate Reconciliation</h2>' not in text:
    marker = '<div class="card"><h2>Interface / Policy Operations</h2>'
    section = '''<div class="card"><h2>FortiGate Reconciliation</h2><button onclick="loadReconciliation()">Run Reconciliation</button><div id="reconSummary" class="dashgrid"></div><div id="reconciliation"></div></div>'''
    if marker not in text:
        raise SystemExit('ERROR: Could not find Interface/Policy Operations section. No changes made.')
    text = text.replace(marker, section + marker, 1)

# Add JavaScript loader before toggle function.
if 'async function loadReconciliation()' not in text:
    marker = 'async function toggle(enable,apply)'
    function = '''async function loadReconciliation(){let d=await j('/api/reconciliation');let s=d.summary||{};reconSummary.innerHTML=`<div class="dashcard"><h3>Matched</h3><div class="dashvalue">${s.match||0}</div></div><div class="dashcard"><h3>Review</h3><div class="dashvalue">${s.review||0}</div></div><div class="dashcard"><h3>Missing</h3><div class="dashvalue">${s.missing||0}</div></div><div class="dashcard"><h3>Unassigned FG</h3><div class="dashvalue">${s.unassigned||0}</div></div>`;reconciliation.innerHTML=table(d.results||[])}'''
    if marker not in text:
        raise SystemExit('ERROR: Could not find JavaScript toggle function marker. No changes made.')
    text = text.replace(marker, function + marker, 1)

main.write_text(text, encoding='utf-8')
print('SUCCESS: v3.3 FortiGate reconciliation patch applied.')
print(f'Backup: {backup}')
print('No FortiGate write behavior was enabled or changed.')
