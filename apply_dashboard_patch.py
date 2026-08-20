from pathlib import Path
import shutil

main = Path('app/main.py')
if not main.exists():
    raise SystemExit('ERROR: Run this script from the citypoint_cmdb_app_v3 folder. app/main.py was not found.')

text = main.read_text(encoding='utf-8')
backup = main.with_suffix('.py.pre_v3_2_dashboard_backup')
if not backup.exists():
    shutil.copy2(main, backup)

# 1) Add dashboard API endpoint before dropdown API.
if "@app.get('/api/dashboard')" not in text:
    marker = "@app.get('/api/dropdowns')\n"
    endpoint = '''@app.get('/api/dashboard')
def dashboard():
    refresh_statuses()
    customer_counts = db.rows("SELECT status, COUNT(*) AS total FROM customers GROUP BY status")
    customer_map = {r["status"]: r["total"] for r in customer_counts}
    booths = db.rows("SELECT status, COUNT(*) AS total FROM booths GROUP BY status")
    booth_map = {r["status"]: r["total"] for r in booths}
    vlans = db.rows("SELECT status, COUNT(*) AS total FROM vlans GROUP BY status")
    vlan_map = {r["status"]: r["total"] for r in vlans}
    subnets = db.rows("SELECT status, COUNT(*) AS total FROM subnets GROUP BY status")
    subnet_map = {r["status"]: r["total"] for r in subnets}
    assigned_interfaces = db.rows("SELECT COUNT(DISTINCT fortigate_interface) AS total FROM customers WHERE status='active' AND fortigate_interface IS NOT NULL AND TRIM(fortigate_interface)<>''")[0]["total"]
    fg_total = db.rows("SELECT COUNT(*) AS total FROM fortigate_interfaces")[0]["total"]
    return {
        "customers": {
            "active": customer_map.get("active", 0),
            "deleted": customer_map.get("deleted", 0),
            "total": sum(customer_map.values()),
        },
        "booths": {
            "used": booth_map.get("used", 0),
            "available": booth_map.get("available", 0),
            "total": sum(booth_map.values()),
        },
        "vlans": {
            "used": vlan_map.get("used", 0),
            "available": vlan_map.get("available", 0),
            "total": sum(vlan_map.values()),
        },
        "subnets": {
            "used": subnet_map.get("used", 0),
            "available": subnet_map.get("available", 0),
            "total": sum(subnet_map.values()),
        },
        "fortigate_interfaces": {
            "assigned": assigned_interfaces,
            "unassigned": max(fg_total - assigned_interfaces, 0),
            "total_cached": fg_total,
        },
    }

'''
    if marker not in text:
        raise SystemExit('ERROR: Could not find dropdown endpoint marker. No changes made.')
    text = text.replace(marker, endpoint + marker, 1)

# 2) Add dashboard CSS.
if '.dashgrid{' not in text:
    css_marker = '.hint{color:#475569}'
    css_extra = ".hint{color:#475569}.dashgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(175px,1fr));gap:10px}.dashcard{border:1px solid #dbe3ee;border-radius:8px;padding:12px;background:#f8fbff}.dashcard h3{margin:0 0 8px;color:#1f4e78}.dashvalue{font-size:24px;font-weight:700}.dashdetail{font-size:12px;color:#475569;margin-top:4px}"
    if css_marker not in text:
        raise SystemExit('ERROR: Could not find CSS marker. No changes made.')
    text = text.replace(css_marker, css_extra, 1)

# 3) Insert dashboard below title, before import card.
if '<h2>Dashboard</h2>' not in text:
    html_marker = '<h1>CityPoint CMDB v3</h1><div class="card"><h2>Import original Excel</h2>'
    html_replacement = '''<h1>CityPoint CMDB v3.2</h1><div class="card"><h2>Dashboard</h2><div id="dashboard" class="dashgrid"><p>Loading...</p></div></div><div class="card"><h2>Import original Excel</h2>'''
    if html_marker not in text:
        raise SystemExit('ERROR: Could not find page title/import marker. No changes made.')
    text = text.replace(html_marker, html_replacement, 1)

# 4) Add JS dashboard loader and call it during refreshAll.
if 'async function loadDashboard()' not in text:
    js_marker = 'async function loadDropdowns()'
    js_func = '''async function loadDashboard(){let d=await j('/api/dashboard');dashboard.innerHTML=`<div class="dashcard"><h3>Customers</h3><div class="dashvalue">${d.customers.active}</div><div class="dashdetail">Active | ${d.customers.deleted} deleted | ${d.customers.total} total</div></div><div class="dashcard"><h3>Booths</h3><div class="dashvalue">${d.booths.used} / ${d.booths.total}</div><div class="dashdetail">Used | ${d.booths.available} available</div></div><div class="dashcard"><h3>VLANs</h3><div class="dashvalue">${d.vlans.used} / ${d.vlans.total}</div><div class="dashdetail">Used | ${d.vlans.available} available</div></div><div class="dashcard"><h3>Subnets</h3><div class="dashvalue">${d.subnets.used} / ${d.subnets.total}</div><div class="dashdetail">Used | ${d.subnets.available} available</div></div><div class="dashcard"><h3>FortiGate Interfaces</h3><div class="dashvalue">${d.fortigate_interfaces.assigned} / ${d.fortigate_interfaces.total_cached}</div><div class="dashdetail">Assigned | ${d.fortigate_interfaces.unassigned} unassigned</div></div>`}'''
    if js_marker not in text:
        raise SystemExit('ERROR: Could not find JavaScript dropdown marker. No changes made.')
    text = text.replace(js_marker, js_func + js_marker, 1)

old_refresh = 'async function refreshAll(){await loadDropdowns();await loadCustomers();await loadObjects()}'
new_refresh = 'async function refreshAll(){await loadDashboard();await loadDropdowns();await loadCustomers();await loadObjects()}'
if old_refresh in text:
    text = text.replace(old_refresh, new_refresh, 1)
elif new_refresh not in text:
    raise SystemExit('ERROR: Could not patch refreshAll. Restore backup if needed.')

main.write_text(text, encoding='utf-8')
print('SUCCESS: v3.2 dashboard patch applied.')
print(f'Backup: {backup}')
print('No search feature was added.')
print('Dashboard cards: Customers, Booths, VLANs, Subnets, FortiGate Interfaces.')
