from io import BytesIO
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.worksheet.table import Table, TableStyleInfo
from . import db


def style(ws):
    fill=PatternFill('solid',fgColor='1F4E78'); font=Font(color='FFFFFF',bold=True)
    for c in ws[1]: c.fill=fill; c.font=font; c.alignment=Alignment(horizontal='center')
    for col in ws.columns:
        ws.column_dimensions[col[0].column_letter].width=min(max(max(len(str(c.value)) if c.value is not None else 0 for c in col)+2,12),55)
    if ws.max_row>1:
        ref=f"A1:{ws.cell(ws.max_row,ws.max_column).coordinate}"; tab=Table(displayName=ws.title.replace(' ','')[:25]+'Table',ref=ref); tab.tableStyleInfo=TableStyleInfo(name='TableStyleMedium2',showRowStripes=True); ws.add_table(tab)

def build_report(cache):
    
#DEBUG

    print("===== REPORT CACHE =====")
    print("smartzone_dpsks:", len(cache.get("smartzone_dpsks", [])))
    print("ruckus_switches:", len(cache.get("ruckus_switches", [])))

    
# Build DPSK count lookup from SmartZone cache
    dpsk_count_by_vlan = {}

    for dpsk in cache.get("smartzone_dpsks", []):
        try:
            dpsk_vlan = int(dpsk.get("vlan"))
        except (TypeError, ValueError):
            continue

        dpsk_count_by_vlan[dpsk_vlan] = (
            dpsk_count_by_vlan.get(dpsk_vlan, 0) + 1
        )    
        
    
    wb=Workbook(); ws=wb.active; ws.title='Current Customers'
    ws.append([
        'ID',
        'Licensee',
        'Legal Name',
        'Booth Group',
        'VLAN',
        'Subnet',
        'Gateway',
        'FortiGate Interface',
        'FG Interface Status',
        'Internet Policy',
        'Policy Status',
        'Switch',
        'Switch Port',
        'Port Definition',
        'Switch Match',
        'DPSK Count',
        'Status'
    ])
    q="""
        SELECT
            c.id,
            c.licensee,
            c.legal_name,
            c.booth_group,
            c.vlan_id,
            c.subnet_cidr,
            s.gateway,
            c.fortigate_interface,
            f.interface_status,
            f.policy_name,
            f.policy_status,
            '' as switch_name,
            '' as port,
            '' as port_definition,
            '' as match_status,
            0 as dpsk_count,
            c.status
        FROM customers c

        LEFT JOIN subnets s
            ON s.cidr = c.subnet_cidr

        LEFT JOIN fortigate_interfaces f
            ON f.name = c.fortigate_interface


        ORDER BY c.licensee
    """
 
 
    for r in db.rows(q):
        try:
            vlan = int(r.get("vlan_id"))
        except (TypeError, ValueError):
            vlan = None

        # Insert DPSK Count before Status and Notes
        ws.append([
            r.get("id"),
            r.get("licensee"),
            r.get("legal_name"),
            r.get("booth_group"),
            r.get("vlan_id"),
            r.get("subnet_cidr"),
            r.get("gateway"),
            r.get("fortigate_interface"),
            r.get("interface_status"),
            r.get("policy_name"),
            r.get("policy_status"),
            r.get("switch_name"),
            r.get("port"),
            r.get("port_definition"),
            r.get("match_status"),
            dpsk_count_by_vlan.get(vlan, 0),
            r.get("status")
        ])
    rows = list(db.rows(q))
    
    if rows:
        print("Keys:", list(rows[0].keys()))
        print("Types:", [type(k) for k in rows[0].keys()])
 
    
    style(ws)
    ws2=wb.create_sheet('FG Interfaces vs Customer'); 
    ws2.append(['Interface','FG VLAN','FG CIDR','FG Gateway','Interface Status','Policy ID','Policy Name','Policy Status','Customer','Customer VLAN','Customer Subnet','Match Status'])
    q2="""
        SELECT f.name,
        f.vlan_id,
        f.cidr,
        f.gateway,
        f.interface_status,
        f.policy_id,
        f.policy_name,
        f.policy_status,
        c.licensee,
        c.vlan_id AS customer_vlan,
        c.subnet_cidr
    FROM fortigate_interfaces f
    LEFT JOIN customers c ON c.fortigate_interface = f.name AND c.status = 'active'
    ORDER BY f.name"""
    for r in db.rows(q2):
        status='UNASSIGNED'
        if r.get('licensee'): 
            status='MATCH' if str(r.get('vlan_id'))==str(r.get('customer_vlan')) and (not r.get('subnet_cidr') or r.get('cidr')==r.get('subnet_cidr')) else 'REVIEW'
        ws2.append(
            [
                r.get('name'),
                r.get('vlan_id'),
                r.get('cidr'),
                r.get('gateway'),
                r.get('interface_status'),
                r.get('policy_id'),
                r.get('policy_name'),
                r.get('policy_status'),
                r.get('licensee'),
                r.get('customer_vlan'),
                r.get('subnet_cidr')
            ]
        )
    style(ws2)
    ws3=wb.create_sheet('Object Pools'); 
    ws3.append(['Object Type','Value','Gateway','Status','Used By'])
    for r in db.rows("SELECT v.vlan_id AS value,v.status,GROUP_CONCAT(c.licensee, ', ') AS used_by FROM vlans v LEFT JOIN customers c ON c.vlan_id=v.vlan_id AND c.status='active' GROUP BY v.vlan_id,v.status ORDER BY v.vlan_id"): ws3.append(['VLAN',r['value'],'',r['status'],r['used_by']])
    for r in db.rows("SELECT s.cidr AS value,s.gateway,s.status,GROUP_CONCAT(c.licensee, ', ') AS used_by FROM subnets s LEFT JOIN customers c ON c.subnet_cidr=s.cidr AND c.status='active' GROUP BY s.cidr,s.gateway,s.status ORDER BY s.cidr"): ws3.append(['Subnet',r['value'],r['gateway'],r['status'],r['used_by']])
    for r in db.rows("SELECT b.booth_group AS value,b.status,GROUP_CONCAT(c.licensee, ', ') AS used_by FROM booths b LEFT JOIN customers c ON c.booth_group=b.booth_group AND c.status='active' GROUP BY b.booth_group,b.status ORDER BY b.booth_group"): ws3.append(['Booth Group',r['value'],'',r['status'],r['used_by']])
    style(ws3); 
    
    
    
    ws4 = wb.create_sheet('DPSK Summary')
    
    ws4.append([
        'VLAN',
        'Customer',
        'Booth Group',
        'DPSK Count',
        'Customer Match'
    ])
    

# DPSK Summary Sheet
    vlan_map = {}

    customer_by_vlan = {}

    for customer in db.rows("""
        SELECT
            licensee,
            booth_group,
            vlan_id
        FROM customers
        WHERE status='active'
        AND vlan_id IS NOT NULL
    """):
        try:
            customer_vlan = int(customer.get("vlan_id"))
        except (TypeError, ValueError):
            continue

        customer_by_vlan[customer_vlan] = customer


    
    #debug!!!!!!!!!!!!!!!!!!!!!!
    print("DPSK VLANs:", len(dpsk_count_by_vlan))
    print("Customers with VLANs:", len(customer_by_vlan))
    for vlan in sorted(dpsk_count_by_vlan):
        customer = customer_by_vlan.get(vlan)

        ws4.append([
            vlan,
            customer.get("licensee", "") if customer else "",
            customer.get("booth_group", "") if customer else "",
            dpsk_count_by_vlan[vlan],
            "MATCH" if customer else "NO CUSTOMER"
        ])

    # debug
    print("WS4 max row:", ws4.max_row)
    
    style(ws4)
    
    ws5 = wb.create_sheet('Switch Ports')

    ws5.append([
        'Switch',
        'Port',
        'Port Definition',
        'Untagged VLAN'
      ])
   
    for sw in cache.get("ruckus_switches", []):
        ws5.append([
            sw.get("switch", ""),
            sw.get("port", ""),
            sw.get("description", ""),  # Port Definition
            sw.get("vlan", "")         # Untagged VLAN
        ])

    
    style(ws5)
    
    bio=BytesIO(); wb.save(bio); bio.seek(0); return bio
