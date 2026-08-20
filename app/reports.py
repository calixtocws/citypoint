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
def build_report():
    wb=Workbook(); ws=wb.active; ws.title='Current Customers'
    ws.append(['ID','Licensee','Legal Name','Booth Group','VLAN','Subnet','Gateway','FortiGate Interface','Status','Notes'])
    q="""SELECT c.id,c.licensee,c.legal_name,c.booth_group,c.vlan_id,c.subnet_cidr,s.gateway,c.fortigate_interface,c.status,c.notes FROM customers c LEFT JOIN subnets s ON s.cidr=c.subnet_cidr ORDER BY c.licensee"""
    for r in db.rows(q): ws.append(list(r.values()))
    style(ws)
    ws2=wb.create_sheet('FG Interfaces vs Customer'); ws2.append(['Interface','FG VLAN','FG CIDR','FG Gateway','Interface Status','Policy ID','Policy Name','Policy Status','Customer','Customer VLAN','Customer Subnet','Match Status'])
    q2="""SELECT f.name,f.vlan_id,f.cidr,f.gateway,f.interface_status,f.policy_id,f.policy_name,f.policy_status,c.licensee,c.vlan_id AS customer_vlan,c.subnet_cidr FROM fortigate_interfaces f LEFT JOIN customers c ON c.fortigate_interface=f.name AND c.status='active' ORDER BY f.name"""
    for r in db.rows(q2):
        status='UNASSIGNED'
        if r.get('licensee'): status='MATCH' if str(r.get('vlan_id'))==str(r.get('customer_vlan')) and (not r.get('subnet_cidr') or r.get('cidr')==r.get('subnet_cidr')) else 'REVIEW'
        ws2.append([r.get('name'),r.get('vlan_id'),r.get('cidr'),r.get('gateway'),r.get('interface_status'),r.get('policy_id'),r.get('policy_name'),r.get('policy_status'),r.get('licensee'),r.get('customer_vlan'),r.get('subnet_cidr'),status])
    style(ws2)
    ws3=wb.create_sheet('Object Pools'); ws3.append(['Object Type','Value','Gateway','Status','Used By'])
    for r in db.rows("SELECT v.vlan_id AS value,v.status,GROUP_CONCAT(c.licensee, ', ') AS used_by FROM vlans v LEFT JOIN customers c ON c.vlan_id=v.vlan_id AND c.status='active' GROUP BY v.vlan_id,v.status ORDER BY v.vlan_id"): ws3.append(['VLAN',r['value'],'',r['status'],r['used_by']])
    for r in db.rows("SELECT s.cidr AS value,s.gateway,s.status,GROUP_CONCAT(c.licensee, ', ') AS used_by FROM subnets s LEFT JOIN customers c ON c.subnet_cidr=s.cidr AND c.status='active' GROUP BY s.cidr,s.gateway,s.status ORDER BY s.cidr"): ws3.append(['Subnet',r['value'],r['gateway'],r['status'],r['used_by']])
    for r in db.rows("SELECT b.booth_group AS value,b.status,GROUP_CONCAT(c.licensee, ', ') AS used_by FROM booths b LEFT JOIN customers c ON c.booth_group=b.booth_group AND c.status='active' GROUP BY b.booth_group,b.status ORDER BY b.booth_group"): ws3.append(['Booth Group',r['value'],'',r['status'],r['used_by']])
    style(ws3); bio=BytesIO(); wb.save(bio); bio.seek(0); return bio
