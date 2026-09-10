import os, shutil, json
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel
from . import db
from .pools import initialize_pools, refresh_statuses
from .importer import import_excel
from .fortigate import refresh_fortigate_cache, action_plan, FortiGateClient, apply_or_dry_run, FortiGateError
from .reports import build_report
from .ruckus import collect_ruckus_cache
# main.py
from app.smartzone import (
    collect_smartzone_cache
)
app=FastAPI(title='CityPoint CMDB v3'); db.init_db(); initialize_pools(); refresh_statuses()


fg = FortiGateClient()

CACHE = {
    "ruckus_switches": [],
    "smartzone_dpsks": []
}

try:
    CACHE["ruckus_switches"] = collect_ruckus_cache()
except Exception as e:
    print("Ruckus preload failed:", e)
try:
    CACHE["smartzone_dpsks"] = collect_smartzone_cache()
except Exception as e:
    print("SmartZone preload failed:", e)
    
    
INFRA_VLANS = set(range(191, 200)) | {900}

IGNORED_INTERFACES = {
    "GADC",
    "CalixtoAP",

    "Management",
    "mgmt",
    "fortilink",
    "ha",
    "l2t.root",
    "naf.root",
    "ssl.root",
    "default-mesh",
    "modem",
    "lan",

    "port1","port2","port3","port4",
    "port5","port6","port7","port8",
    "port9","port10","port11","port12",
    "port13","port14","port15","port16",
    "port17","port18","port19","port20",
    "port21","port22","port23","port24",

    "x1","x2","x3","x4"
}

IGNORED_INTERFACES_LOWER = {
    x.lower() for x in IGNORED_INTERFACES
}


class CustomerPayload(BaseModel):
    licensee:str; legal_name:str|None=None; booth_group:str|None=None; vlan_id:int|None=None; subnet_cidr:str|None=None; fortigate_interface:str|None=None; notes:str|None=None
class TogglePayload(BaseModel):
    interface_name:str; policy_id:str|None=None; enable:bool; apply:bool=False

class DpskCreatePayload(BaseModel):
    vlan: int
    licensee: str
    quantity: int = 1
    group_enabled: bool = True
     
    
@app.get('/',response_class=HTMLResponse)
def home():
    return render_home()

def render_home():
    return """
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>CityPoint CMDB v3.4</title>

<style>
body{
    font-family:Segoe UI,Arial;
    margin:18px;
    background:#f5f6f8
}

.card{
    background:#fff;
    border:1px solid #ddd;
    border-radius:8px;
    padding:14px;
    margin:12px 0
}

button{
    background:#2563eb;
    color:#fff;
    border:0;
    padding:7px 10px;
    border-radius:5px;
    margin:3px
}

button.red{
    background:#b91c1c
}

button.green{
    background:#15803d
}

button.gray{
    background:#64748b
}

button.nav{
    background:#1f4e78;
    font-weight:600
}

input,select{
    padding:6px;
    margin:3px;
    border:1px solid #bbb;
    border-radius:4px;
    min-width:150px
}

table{
    border-collapse:collapse;
    width:100%;
    font-size:12px;
    background:white
}

th{
    background:#1f4e78;
    color:white;
    position:sticky;
    top:0
}

td,th{
    border-bottom:1px solid #eee;
    padding:5px;
    text-align:left
}

tr.deleted{
    color:#888;
    background:#f1f5f9
}

pre{
    background:#0b1020;
    color:#75ff99;
    padding:10px;
    overflow:auto;
    max-height:300px
}

.hint{
    color:#475569
}

.dashgrid{
    display:grid;
    grid-template-columns:
        repeat(auto-fit,minmax(175px,1fr));
    gap:10px
}

.dashcard{
    border:1px solid #dbe3ee;
    border-radius:8px;
    padding:12px;
    background:#f8fbff
}

.dashcard h3{
    margin:0 0 8px;
    color:#1f4e78
}

.dashvalue{
    font-size:24px;
    font-weight:700
}

.dashdetail{
    font-size:12px;
    color:#475569;
    margin-top:4px
}
</style>

</head>

<body>

<h1>CityPoint CMDB v3.4</h1>

<div class="card">
    <button class="nav"
            onclick="showTab('dashboardTab')">
    Dashboard
    </button>

    <button class="nav"
            onclick="showTab('customersTab')">
    Customers
    </button>
    <button class="nav"
            onclick="showTab('boothsTab')">
    Booths
    </button>
    <button class="nav"
            onclick="showTab('subnetsTab')">
    Subnets
    </button>
    <button class="nav"
            onclick="showTab('fortigateTab')">
    FortiGate
    </button>
    <button class="nav"
            onclick="showTab('switchesTab')">
    Switches
    </button>
    <button class="nav"
            onclick="showTab('dpskTab')">
    DPSK
    </button>
    <button class="nav"
            onclick="showTab('utilitiesTab')">
    Utilities
    </button>
</div>




<div id="dashboardTab">
    <div class="card">
        <h2>Dashboard</h2>
        <button id="updateDataBtn" onclick="updateAllData()">
            Update Data (DPSK / Switches / FortiGate)
        </button>
        <span id="updateDataStatus"></span>
        <div id="dashboard"
             class="dashgrid">
            <p>Loading...</p>
        </div>
    </div>
</div>

<div id="customersTab" class="tab-content" style="display:none">
    <div class="card">
        <h2>Add / Edit Customer</h2>
            <input id="cid" placeholder="ID for edit only">
            <input id="licensee" placeholder="Licensee">
            <input id="legal" placeholder="Legal Name">
            <select id="booth"></select>
            <select id="vlan"></select>
            <select id="subnet"></select>
            <select id="fgif"></select>
            <input id="notes" placeholder="Notes">
            <button onclick="saveCustomer()">
                Add / Save Edit
            </button>
            <button class="gray"
                    onclick="clearForm()">
                Clear Add Form
            </button>
    </div>

    <div class="card">
        <h2>Customer List</h2>
        <input
            id="customerSearch"
            placeholder="Search customer / booth / vlan / subnet"
            onkeyup="filterCustomers()">
        <div id="customers"></div>
    </div>
</div>

<div id="dpskTab" class="tab" style="display:none">
    <h2>DPSK Summary</h2>
    <div id="dpskSummary"></div>
    <hr>
    <h2>DPSK Details</h2>
    <div id="dpskDetails">
        Select a VLAN
    </div>
</div>

<div id="boothsTab"
     style="display:none">
    <div class="card">
        <h2>Booths</h2>
        <button onclick="loadBooths()">
            Refresh Booths
        </button>
        <div id="boothsView"></div>
    </div>
</div>

<div id="subnetsTab"class="tab-content" style="display:none" >
    <div class="card">
        <h2>Subnets</h2>
        <button onclick="loadSubnets()">
            Refresh Subnets
           </button>
            <div id="subnetsView"></div>
    </div>
</div>

<!-- FortiGate -->
<div id="fortigateTab" style="display:none">
    <div class="card">
        <h2>Collect From FortiGate</h2>
        <button onclick="fgRefresh()">
            Pull FG Interfaces / Policies
        </button>
        <button onclick="loadFg()">
            Customer vs FG Interfaces
        </button>
        <div id="fg"></div>
    </div>
    <div class="card">
        <h2>FortiGate Reconciliation</h2>
        <button onclick="loadReconciliation()">
            Run Reconciliation
        </button>
        <div id="reconSummary"
                class="dashgrid"></div>
        <div id="reconciliation"></div>
    </div>

    <div class="card">
        <h2>Interface / Policy Operations</h2>
        <select id="opif"></select>
        <input id="oppolicy"
                placeholder="Policy ID">
        <button class="green"
                onclick="toggle(true,false)">
            Dry Run Enable
        </button>
        <button class="red"
                onclick="toggle(false,false)">
            Dry Run Disable
        </button>
        <pre id="opresult"></pre>
    </div>
</div>

<div id="switchesTab" class="tab-content" style="display:none;">
  <h2>Switch Inventory</h2>
  <table class="grid">
    <thead>
      <tr>
        <th>Switch</th>
        <th>Port</th>
        <th>Description</th>
        <th>VLAN</th>
        <th>Link</th>
        <th>Speed</th>
      </tr>
    </thead>
    <tbody id="switchesBody"></tbody>
  </table>
</div>

<!-- Utilities -->
<div id="utilitiesTab" class="tab-content" style="display:none">
    <div class="card">
        <h2>Import Excel</h2>
        <input type="file" id="file">
        <button onclick="upload()">
            Import
        </button>
        <span id="msg"></span>
        <p class="hint">
            Multi-VLAN source rows are imported with
            VLAN blank and notes populated.
        </p>
    </div>
    <div class="card">
        <h2>Export</h2>
        <button
            onclick="window.location='/api/report.xlsx'">
            Download Excel Report
        </button>
    </div>

    <div class="card">
        <h2>Object Pools</h2>
        <button onclick="loadObjects()">
            Refresh Pools
        </button>
        <div id="objects"></div>
    </div>
</div>
	
<script>
    let currentCustomers=[];
    async function j(url,opts){
    let r=await fetch(url,opts);
    let t=await r.text();
    try{return JSON.parse(t)}
    catch(e)
    {return {error:t}}
    }
    
    function esc(s){
        return String(s??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;')
    }
    
    function table(rows,actions=false){
        if(!rows||!rows.length)
        return '<p>No data</p>';
        let keys=Object.keys(rows[0]);
        let h='<table><tr>'+keys.map(k=>'<th>'+esc(k)+'</th>').join('')+(actions?'<th>Operations</th>':'')+'</tr>';
        for(let row of rows){
            
            h += '<tr class="' +
                (row.status === 'deleted' ? 'deleted' : '')
                + '">';

            for (let k of keys) {

                let value = row[k];

                if (k === 'dpsk_linked') {

                    let color =
                        value === 'Yes'
                            ? '#16a34a'
                            : '#dc2626';

                    h += `
                        <td>
                            <span style="
                                color:${color};
                                font-weight:bold">
                                ${esc(value)}
                            </span>
                        </td>
                    `;

                } else if (k === 'physical_status') {

                    let color = '#ea580c';

                    if (value === 'Up')
                        color = '#16a34a';

                    if (value === 'Down')
                        color = '#dc2626';

                    h += `
                        <td>
                            <span style="
                                color:${color};
                                font-weight:bold">
                                ${esc(value)}
                            </span>
                        </td>
                    `;

                } else {

                    h += `<td>${esc(value)}</td>`;
                }
            }
                
            if(actions)h+=`<td><button onclick="editRow(${row.id})">Edit</button>
            <button class="red" onclick="delCustomer(${row.id})">Delete</button>
            </td>`;
            h+='</tr>'
         }
        return h+'</table>'
	}
	 
    async function upload(){
        let f=file.files[0];
        let fd=new FormData();
        fd.append('file',f);
        msg.innerText=JSON.stringify(await j('/api/import/excel',{method:'POST',body:fd}));
        refreshAll()
    }

   
    async function loadSwitches() {
        const body =
            document.getElementById(
                "switchesBody"
            );
        const response =
            await fetch('/api/switches');
        const data =
            await response.json();
        body.innerHTML = '';
        data.forEach(sw => {
            body.innerHTML += `
            <tr>
                <td>${sw.switch}</td>
                <td>${sw.port}</td>
                <td>${sw.description || ''}</td>
                <td>${sw.vlan || ''}</td>
                <td>${sw.link || ''}</td>
                <td>${sw.speed || ''}</td>
            </tr>
            `;
        });
    }


    async function loadDpskSummary() {

        const r = await fetch("/api/dpsks-summary");
        const data = await r.json();
        data.sort((a,b) => a.vlan - b.vlan);
        let html = `
        <div class="card">
            <div class="dashvalue">
                ${data.length}
            </div>
            <div class="dashdetail">
                DPSK VLANs
            </div>
        </div>
        <table class="table">
            <thead>
                <tr>
                    <th>VLAN</th>
                    <th>DPSKs</th>
                    <th>Example Username</th>
                    <th>Latest Created</th>
                    <th>Action</th>
                </tr>
            </thead>
            <tbody>
        `;
        data.forEach(row => {
            html += `
            <tr>
                <td>
                    ${row.vlan}
                </td>
                <td>
                    ${row.dpsk_count}
                </td>
                <td>
                    ${row.sample_username || ""}
                </td>
                <td>
                    ${row.latest_created || ""}
                </td>
                <td>
                    <button
                        onclick="loadDpskVlan(${row.vlan})">
                        View
                    </button>
                </td>
            </tr>
            `;
        });
        html += `
            </tbody>
        </table>
        `;
        document.getElementById(
            "dpskSummary"
        ).innerHTML = html;
    }




async function loadDashboard(){
	   let d=await j('/api/dashboard');dashboard.innerHTML=
	     `<div class="dashcard">
		  <h3>Customers</h3>
		  <div class="dashvalue">${d.customers.active}</div>
		  <div class="dashdetail">Active | ${d.customers.deleted} deleted | ${d.customers.total} total</div></div>
		  <div class="dashcard">
		  <h3>Booths</h3>
		  <div class="dashvalue">${d.booths.used} / ${d.booths.total}</div>
		  <div class="dashdetail">Used | ${d.booths.available} available</div></div>
		  <div class="dashcard">
		    <h3>VLANs</h3>
		    <div class="dashvalue">${d.vlans.used} / ${d.vlans.total}</div>
		    <div class="dashdetail">Used | ${d.vlans.available} available</div>
		  </div>
		  <div class="dashcard">
		   <h3>Subnets</h3>
		   <div class="dashvalue">${d.subnets.used} / ${d.subnets.total}</div>
		   <div class="dashdetail">Used | ${d.subnets.available} available</div>
		  </div>
		  <div class="dashcard">
		    <h3>FortiGate Interfaces</h3>
		    <div class="dashvalue">${d.fortigate_interfaces.assigned} / ${d.fortigate_interfaces.total_cached}</div>
		    <div class="dashdetail">Assigned | ${d.fortigate_interfaces.unassigned} unassigned</div>
		  </div>
    `
        + `<div class="dashcard"
     style="border-left:5px solid ${
        d.physical.down > 0 ? '#dc2626' : '#16a34a'
     }">
            <h3 onclick="showTab('dpskTab')">DPSK Coverage</h3>
            <div class="dashvalue">${d.dpsk.linked}</div>
            <div class="dashdetail">
                Linked | ${d.dpsk.missing} missing
            </div>
        </div>`

        + `<div class="dashcard"
     style="border-left:5px solid ${
        d.physical.down > 0 ? '#dc2626' : '#16a34a'
     }">
            <h3>Physical Links</h3>
            <div class="dashvalue">${d.physical.up}</div>
            <div class="dashdetail">
                Up | ${d.physical.down} down |
                ${d.physical.nomatch} no match
            </div>
        </div>`
    
}

async function loadDpskVlan(vlan) {
    console.log("Loading VLAN", vlan);
    const r = await fetch(`/api/dpsks/${vlan}`);
    console.log("HTTP", r.status);
    const data = await r.json();
    console.log("Records", data.length);
    let html = `
        <h3>
            VLAN ${vlan}
            (${data.length} DPSKs)
        </h3>
        <div style="margin-bottom:10px">
<button disabled>
    Create DPSK
</button>
            <button disabled>
                Delete Selected
            </button>
        </div>
        <table class="table">
            <thead>
                <tr>
                    <th></th>
                    <th>Username</th>
                    <th>Passphrase</th>
                    <th>Created</th>
                    <th>Expires</th>
                </tr>
            </thead>
            <tbody>
    `;

    data.forEach(row => {
        html += `
            <tr>
                <td>
                    <input
                        type="checkbox"
                        value="${row.id}">
                </td>
                <td>${row.username}</td>
                <td>${row.passphrase}</td>
                <td>${row.created}</td>
                <td>${row.expires}</td>
            </tr>
        `;
    });

    html += `
            </tbody>
        </table>
    `;

    const details =
        document.getElementById("dpskDetails");

    details.innerHTML = html;

    details.scrollIntoView({
        behavior: "smooth",
        block: "start"
    });
}

async function createDpsk(vlan) {

    const licensee =
        prompt("Licensee");

    if (!licensee) return;

    const quantity =
        Number(prompt("Number of DPSKs", "1"));

    if (!quantity || quantity < 1) return;

    const result = await fetch(
        "/api/dpsks",
        {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                vlan: vlan,
                licensee: licensee,
                quantity: quantity,
                group_enabled: true
            })
        }
    );

    alert(await result.text());

    await loadDpskSummary();
    await loadDpskVlan(vlan);
}
	
async function loadDropdowns(){
	  let d=await j('/api/dropdowns');
	  booth.innerHTML='<option value="">-- booth --</option>'+d.booths.map(x=>`<option value="${esc(x.booth_group)}">${esc(x.booth_group)} (${x.status})</option>`).join('');vlan.innerHTML='<option value="">-- vlan --</option>'+d.vlans.map(x=>`<option value="${x.vlan_id}">${x.vlan_id} (${x.status})</option>`).join('');subnet.innerHTML='<option value="">-- subnet --</option>'+d.subnets.map(x=>`<option value="${x.cidr}">${x.cidr} gw ${x.gateway} (${x.status})</option>`).join('');fgif.innerHTML='<option value="">-- FortiGate interface --</option>'+d.fg_interfaces.map(x=>`<option value="${esc(x.name)}">${esc(x.name)}</option>`).join('');opif.innerHTML=fgif.innerHTML}

    async function loadCustomers(){
    currentCustomers=await j('/api/customers');
    customers.innerHTML=table(currentCustomers,true)
    }

    function filterCustomers(){

        const search =
            customerSearch.value.toLowerCase().trim();

        if(!search){
            customers.innerHTML =
                table(currentCustomers,true);
            return;
        }

    const filtered =
        currentCustomers.filter(x =>
            JSON.stringify(x)
                .toLowerCase()
                .includes(search)
        );

    customers.innerHTML =
        table(filtered,true);
}
 
 
async function loadObjects(){
     let o=await j('/api/objects');
     objects.innerHTML='<h3>Booths</h3>'+table(o.booths)+'<h3>VLANs</h3>'+table(o.vlans)+'<h3>Subnets</h3>'+table(o.subnets)
}
     
async function refreshAll(){
    await loadDashboard();
    await loadDropdowns();
    await loadCustomers();
    await loadObjects();

    }

async function updateAllData(){
    let btn=document.getElementById('updateDataBtn');
    let status=document.getElementById('updateDataStatus');
    btn.disabled=true;
    status.textContent='Updating...';
    try{
        let [dpsk,switches,fg]=await Promise.all([
            j('/api/dpsks/refresh'),
            j('/api/ruckus/refresh'),
            j('/api/fortigate/refresh',{method:'POST'})
        ]);
        await refreshAll();
        status.textContent=`Updated ${new Date().toLocaleTimeString()} — `
            +`DPSK: ${dpsk.records??dpsk.error??'?'} | `
            +`Switches: ${switches.records??switches.error??'?'} | `
            +`FortiGate: ${fg.interfaces??fg.error??'?'} interfaces`;
    }catch(e){
        status.textContent='Update failed: '+e;
    }finally{
        btn.disabled=false;
    }
    }

function setSelect(sel,val){
    let s=String(val??'');
    sel.value=s;
    if(sel.value!==s&&s){let opt=document.createElement('option');opt.value=s;opt.textContent=s+' (current)';sel.appendChild(opt);sel.value=s}
    }

function editRow(id){
    let r=currentCustomers.find(x=>x.id===id);
    if(!r)return;cid.value=r.id;licensee.value=r.licensee||'';
    legal.value=r.legal_name||'';
    setSelect(booth,r.booth_group);
    setSelect(vlan,r.vlan_id);
    setSelect(subnet,r.subnet_cidr);
    setSelect(fgif,r.fortigate_interface);notes.value=r.notes||'';
    window.scrollTo({top:0,behavior:'smooth'})
    }
    
function clearForm(){
    cid.value='';
    licensee.value='';
    legal.value='';
    booth.value='';
    vlan.value='';
    subnet.value='';
    fgif.value='';
    notes.value=''
    }
    
async function saveCustomer(){
    let payload={licensee:licensee.value,legal_name:legal.value,booth_group:booth.value||null,vlan_id:vlan.value?Number(vlan.value):null,subnet_cidr:subnet.value||null,fortigate_interface:fgif.value||null,notes:notes.value};let id=cid.value.trim();
    let url=id?'/api/customers/'+id:'/api/customers';
    let method=id?'PUT':'POST';alert(JSON.stringify(await j(url,{method,headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)})));
    clearForm();
    refreshAll()
    }
    
async function delCustomer(id){
    if(!confirm('Delete customer assignment '+id+'?'))return;
    alert(JSON.stringify(await j('/api/customers/'+id,{method:'DELETE'})));
    refreshAll()
    }
    
async function fgRefresh(){
    fg.innerHTML='<p>Loading...</p>';
    fg.innerHTML='<pre>'+JSON.stringify(await j('/api/fortigate/refresh',{method:'POST'}),null,2)+'</pre>';
    refreshAll()
    }
    
async function loadFg(){
    fg.innerHTML=table(await j('/api/fortigate/report'))
    }
    
async function loadReconciliation(){
    let d=await j('/api/reconciliation');
    let s=d.summary||{};
    reconSummary.innerHTML=`<div class="dashcard"><h3>Matched</h3><div class="dashvalue">${s.match||0}</div></div><div class="dashcard"><h3>Review</h3><div class="dashvalue">${s.review||0}</div></div><div class="dashcard"><h3>Missing</h3><div class="dashvalue">${s.missing||0}</div></div><div class="dashcard"><h3>Unassigned FG</h3><div class="dashvalue">${s.unassigned||0}</div></div>`;
    reconciliation.innerHTML=table(d.results||[])}async function toggle(enable,apply){let payload={interface_name:opif.value,policy_id:oppolicy.value||null,enable,apply};
    opresult.textContent=JSON.stringify(await j('/api/fortigate/toggle',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}),null,2)
    }
 
 
function showTab(tabName){

    const tabs = [
        'dashboardTab',
        'customersTab',
        'boothsTab',
        'subnetsTab',
        'fortigateTab',
        'switchesTab',
        'dpskTab',
        'utilitiesTab'
    ];

    tabs.forEach(t=>{
        const el=document.getElementById(t);
        if(el){
            el.style.display='none';
        }
    });
    const active =
        document.getElementById(tabName);
    if(active){
        active.style.display='block';
    }
    if(tabName==='boothsTab'){
        loadBooths();
    }
    if(tabName==='subnetsTab'){
        loadSubnets();
    }
    if(tabName==='switchesTab'){
        loadSwitches();
    }
    if(tabName==='dpskTab'){
        loadDpskSummary();
    }
}

function filterCustomers(){

    const search =
      customerSearch.value.toLowerCase();

    const filtered =
      currentCustomers.filter(
        x => JSON.stringify(x)
             .toLowerCase()
             .includes(search)
      );

    customers.innerHTML =
      table(filtered,true);
}

async function loadBooths(){
    let o = await j('/api/objects');
    boothsView.innerHTML =
        table(o.booths);
}

async function loadSubnets(){
    let o = await j('/api/objects');
    subnetsView.innerHTML =
        table(o.subnets);
}
 refreshAll()

    </script>
	 </body>
 </html>"""
  

@app.get("/api/ruckus/refresh")
def ruckus_refresh():

    data = collect_ruckus_cache()
    CACHE["ruckus_switches"] = data

    return {
        "status": "success",
        "records": len(data)
    }

@app.post('/api/import/excel')
def upload_excel(file:UploadFile=File(...)):
    os.makedirs('data',exist_ok=True); dest=os.path.join('data',file.filename)
    with open(dest,'wb') as f: shutil.copyfileobj(file.file,f)
    return import_excel(dest)

@app.get('/api/dashboard')
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
    customers_full = customers()
    dpsk_linked = sum(
        1 for c in customers_full
        if c.get("dpsk_count", 0) > 0
    )
    dpsk_missing = sum(
        1 for c in customers_full
        if c.get("dpsk_count", 0) == 0
    )
    physical_up = sum(
        1 for c in customers_full
        if c.get("physical_status") == "Up"
    )
    physical_down = sum(
        1 for c in customers_full
        if c.get("physical_status") == "Down"
    )
    physical_nomatch = sum(
        1 for c in customers_full
        if c.get("physical_status") == "No Match"
    )
    
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
        "dpsk": {
            "linked": dpsk_linked,
            "missing": dpsk_missing
        },
        "physical": {
            "up": physical_up,
            "down": physical_down,
            "nomatch": physical_nomatch
        },
    }

@app.get("/api/debug/customer/{cid}")
def debug_customer(cid: int):
	return db.rows(
		"SELECT * FROM customers WHERE id=?",
		(cid,)
	)

@app.get('/api/dropdowns')
def dropdowns():
    refresh_statuses(); return {'booths':db.rows('SELECT booth_group,status FROM booths ORDER BY booth_group'),'vlans':db.rows(
    '''
    SELECT vlan_id,status
    FROM vlans
    WHERE vlan_id NOT BETWEEN 191 AND 199
      AND vlan_id <> 900
    ORDER BY vlan_id
    '''
),'subnets':db.rows('SELECT cidr,gateway,status FROM subnets ORDER BY cidr'),'fg_interfaces':db.rows('SELECT name FROM fortigate_interfaces ORDER BY name')}
@app.get('/api/objects')
def objects():
    refresh_statuses(); return {'booths':db.rows("SELECT b.booth_group,b.status,GROUP_CONCAT(c.licensee SEPARATOR ', ') AS used_by FROM booths b LEFT JOIN customers c ON c.booth_group=b.booth_group AND c.status='active' GROUP BY b.booth_group,b.status ORDER BY b.booth_group"),'vlans':db.rows("SELECT v.vlan_id,v.status,GROUP_CONCAT(c.licensee SEPARATOR ', ') AS used_by FROM vlans v LEFT JOIN customers c ON c.vlan_id=v.vlan_id AND c.status='active' GROUP BY v.vlan_id,v.status ORDER BY v.vlan_id"),'subnets':db.rows("SELECT s.cidr,s.gateway,s.mask,s.status,GROUP_CONCAT(c.licensee SEPARATOR ', ') AS used_by FROM subnets s LEFT JOIN customers c ON c.subnet_cidr=s.cidr AND c.status='active' GROUP BY s.cidr,s.gateway,s.mask,s.status ORDER BY s.cidr")}


@app.get("/api/dpsks/{vlan}")
def api_dpsk_vlan(vlan: int):
    dpsks = CACHE.get("smartzone_dpsks", [])
    return [
        d
        for d in dpsks
        if int(d["vlan"]) == vlan
    ]


@app.get("/api/dpsks-summary")
def api_dpsks_summary():
    dpsks = CACHE.get("smartzone_dpsks", [])
    vlan_map = {}
    for row in dpsks:
        vlan = row["vlan"]
        if vlan not in vlan_map:
            vlan_map[vlan] = []
        vlan_map[vlan].append(row)
    results = []
    for vlan, entries in vlan_map.items():
        results.append({
            "vlan": vlan,
            "dpsk_count": len(entries),
            # useful later
            "sample_username":
                entries[0]["username"],
            "latest_created":
                max(
                    x["created"]
                    for x in entries
                )
        })

    return sorted(
        results,
        key=lambda x: x["vlan"]
    )
        
@app.get('/api/customers')
def customers():

    refresh_statuses()
    rows = db.rows(
        """
        SELECT
            id,
            licensee,
            legal_name,
            booth_group,
            vlan_id,
            subnet_cidr,
            fortigate_interface,
            status,
            notes
        FROM customers
        ORDER BY
            CASE WHEN status='active' THEN 0 ELSE 1 END,
            licensee
        """
    )

    import time
    #
    # Build Ruckus lookup
    #
     #ruckus_data = collect_ruckus_cache()
    ruckus_data = CACHE.get("ruckus_switches", [])

    ruckus_map = {}
    #print("RUCKUS CACHE TYPE:", type(ruckus_data))
    #print("RUCKUS CACHE VALUE:", ruckus_data)
    for r in ruckus_data:
        desc = (r.get("description") or "").strip()
        if desc.startswith("DMH-Booth-"):
            booth = desc.replace(
                "DMH-Booth-",
                ""
            )
            ruckus_map[booth] = r

    #
    # Attach switch info
    #
    for row in rows:
        booth_group = row.get("booth_group") or ""
        booths = [
            b.strip()
            for b in booth_group.split(",")
            if b.strip()
        ]
        ruckus = None
        matched_booth = ""
        for booth in booths:
            if booth in ruckus_map:
                matched_booth = booth
                ruckus = ruckus_map[booth]
                break
        if ruckus:
            row["ruckus_switch"] = ruckus.get("switch")
            row["ruckus_port"] = ruckus.get("port")
            row["ruckus_vlan"] = ruckus.get("vlan")
            row["ruckus_link"] = ruckus.get("link")
            row["ruckus_speed"] = ruckus.get("speed")
            row["matched_booth"] = matched_booth
            row["switch_description"] = ruckus.get(
            "description"
            )
            if ruckus.get("link") == "Up":
                row["physical_status"] = "Up"
            else:
                row["physical_status"] = "Down"
        else:
            row["ruckus_switch"] = ""
            row["ruckus_port"] = ""
            row["ruckus_vlan"] = ""
            row["ruckus_link"] = ""
            row["ruckus_speed"] = ""
            row["physical_status"] = "No Match"
            row["matched_booth"] = ""
            row["switch_description"] = "" 
  
    # Build DPSK lookup by VLAN
    #
    #dpsk_data = collect_smartzone_cache()
    dpsk_data = CACHE.get( "smartzone_dpsks",  [])

    dpsk_count_by_vlan = {}
    for dpsk in dpsk_data:
        try:
            dpsk_vlan = int(dpsk.get("vlan"))
        except (TypeError, ValueError):
            continue
        dpsk_count_by_vlan[dpsk_vlan] = (
            dpsk_count_by_vlan.get(dpsk_vlan, 0) + 1
        )

    #
    # Attach DPSK status to every customer
    #
    for row in rows:
        customer_vlan = row.get("vlan_id")
        try:
            customer_vlan = int(customer_vlan)
        except (TypeError, ValueError):
            customer_vlan = None
        dpsk_count = (
            dpsk_count_by_vlan.get(customer_vlan, 0)
            if customer_vlan is not None
            else 0
        )

        row["dpsk_count"] = dpsk_count
        row["dpsk_linked"] = "Yes" if dpsk_count else "No"

 
    for row in rows[:20]:
        booth_group = row.get("booth_group") or ""
        booths = [
            b.strip()
            for b in booth_group.split(",")
            if b.strip()
        ]
        matched = None
        for booth in booths:
            if booth in ruckus_map:
                matched = booth
                break

    recon = reconciliation()
    policy_map = {}
    for r in recon["results"]:
        cid = r.get("customer_id")
        if cid:
            policy_map[cid] = (
                r.get("reconciliation_status")
            )            
    
    
    final_rows = []

    for row in rows:
        final_rows.append({
            "id": row["id"],
            "licensee": row["licensee"],
            "booth_group": row["booth_group"],
            "vlan_id": row["vlan_id"],
            "subnet_cidr": row["subnet_cidr"],

            "dpsk_count": row["dpsk_count"],
            "dpsk_linked": row["dpsk_linked"],

            "ruckus_switch": row["ruckus_switch"],
            "ruckus_port": row["ruckus_port"],

            "physical_status": row["physical_status"],

            "fortigate_interface":
                row["fortigate_interface"],

            "status": row["status"]
        })

    return final_rows
    #return rows

def refresh_dpsk_cache():
    CACHE["smartzone_dpsks"] = collect_smartzone_cache()
    return len(CACHE["smartzone_dpsks"])

@app.get("/api/dpsks/refresh")
def dpsk_refresh():
    return {
        "records": refresh_dpsk_cache()
    }

def validate_unique_assignment(p: CustomerPayload, exclude_customer_id: int | None = None):
    """Hard-stop duplicate active booth, VLAN, or subnet assignments."""
    checks = [
        ("booth_group", p.booth_group, "Booth Group"),
        ("vlan_id", p.vlan_id, "VLAN"),
        ("subnet_cidr", p.subnet_cidr, "Subnet"),
    ]
    conflicts = []
    for column, value, label in checks:
        if value is None or str(value).strip() == "":
            continue
        sql = f"SELECT id, licensee FROM customers WHERE status='active' AND {column}=?"
        params = [value]
        if exclude_customer_id is not None:
            sql += " AND id<>?"
            params.append(exclude_customer_id)
        matches = db.rows(sql, tuple(params))
        if matches:
            owners = ", ".join(sorted({m["licensee"] for m in matches}))
            conflicts.append({"object_type": label, "value": value, "assigned_to": owners})
    if conflicts:
        detail = {
            "error": "assignment_conflict",
            "message": "Booth, VLAN, and subnet assignments must be unique across active customers.",
            "conflicts": conflicts,
        }
        raise HTTPException(status_code=409, detail=detail)

@app.post('/api/customers')
def add_customer(p:CustomerPayload):
    validate_unique_assignment(p)
    cid=db.execute('INSERT INTO customers(licensee,legal_name,booth_group,vlan_id,subnet_cidr,fortigate_interface,notes) VALUES (?, ?, ?, ?, ?, ?, ?)',(p.licensee,p.legal_name,p.booth_group,p.vlan_id,p.subnet_cidr,p.fortigate_interface,p.notes)); refresh_statuses(); db.audit('customer_add',p.licensee,p.model_dump_json(),'ok'); return {'id':cid,'status':'added'}
@app.put('/api/customers/{customer_id}')
def edit_customer(customer_id:int,p:CustomerPayload):
    validate_unique_assignment(p, exclude_customer_id=customer_id)
    db.execute("UPDATE customers SET licensee=?,legal_name=?,booth_group=?,vlan_id=?,subnet_cidr=?,fortigate_interface=?,notes=?,status='active',updated_at=CURRENT_TIMESTAMP WHERE id=?",(p.licensee,p.legal_name,p.booth_group,p.vlan_id,p.subnet_cidr,p.fortigate_interface,p.notes,customer_id)); refresh_statuses(); db.audit('customer_edit',str(customer_id),p.model_dump_json(),'ok'); return {'id':customer_id,'status':'updated'}
@app.delete('/api/customers/{customer_id}')
def delete_customer(customer_id:int):
    db.execute("UPDATE customers SET status='deleted',updated_at=CURRENT_TIMESTAMP WHERE id=?",(customer_id,)); refresh_statuses(); db.audit('customer_delete',str(customer_id),None,'marked deleted'); return {'id':customer_id,'status':'marked deleted'}
@app.post('/api/fortigate/refresh')
def fg_refresh():
    #try: return refresh_fortigate_cache()
    try:
        pepe = refresh_fortigate_cache()
        interfaces = fg.get_interfaces()
        policies = fg.get_policies()
        return pepe
    except FortiGateError as e: raise HTTPException(status_code=400,detail=str(e))
    
    
@app.get('/api/reconciliation')
def reconciliation():
    customers = db.rows("""
      SELECT id,
             licensee,
             legal_name,
             booth_group,
             vlan_id,
             subnet_cidr,
             fortigate_interface
      FROM customers
      WHERE status='active'
      ORDER BY licensee
    """)

    interfaces = db.rows("""
      SELECT *
      FROM fortigate_interfaces
      ORDER BY name
    """)

    def is_ignored(fg):
        return (
            (fg.get("name") or "").strip().lower()
            in IGNORED_INTERFACES_LOWER
        )

    by_name = {}
    by_vlan_subnet = {}

    for fg in interfaces:

        if is_ignored(fg):
            continue
        name = (fg.get("name") or "").strip()
        if name:
            by_name[name] = fg
        vlan = fg.get("vlan_id")
        cidr = (fg.get("cidr") or "").strip()
        if vlan is not None and cidr:
            by_vlan_subnet[(str(vlan), cidr)] = fg
    assigned_names = set()
    
    fg = FortiGateClient()
    policies = fg.get_policies().get("results", [])
    policy_map = {}

    for p in policies:
        dst = [
            x.get("name","").lower()
            for x in p.get("dstintf", [])
        ]
        if "virtual-wan-link" not in dst:
            continue

        for src in p.get("srcintf", []):
            iface = src.get("name")
            if not iface:
                continue
            policy_map.setdefault(iface, []).append({
                "policyid": p.get("policyid"),
                "name": p.get("name"),
                "status": p.get("status")
            })
        
    findings = []

    counts = {
        "match": 0,
        "review": 0,
        "missing": 0,
        "unassigned": 0,
        "infrastructure": 0
    }

    #
    # CUSTOMER RECONCILIATION
    #
    for c in customers:
        interface_name = (
            c.get("fortigate_interface") or ""
        ).strip()

        fg = None
        details = []
        
        internet_policies = policy_map.get(
            interface_name,
            []
        )

        #
        # Match by VLAN+CIDR
        #
        if c.get("vlan_id") is not None and c.get("subnet_cidr"):
            fg = by_vlan_subnet.get(
                (
                    str(c.get("vlan_id")),
                    (c.get("subnet_cidr") or "").strip()
                )
            )
        #
        # Fallback to existing interface assignment
        #
        if not fg and interface_name:
            fg = by_name.get(interface_name)
        #
        # Auto-populate interface
        #
        if fg and not interface_name:
            interface_name = fg.get("name")
            db.execute(
                """
                UPDATE customers
                SET fortigate_interface=?,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (
                    interface_name,
                    c.get("id")
                )
            )
        status = "MATCH"
        if not fg:
            status = "NO_VLAN_SUBNET_MATCH"
            details.append(
                "No FortiGate interface matches VLAN + subnet"
            )
        else:
            assigned_names.add(
                fg.get("name")
            )
            internet_policies = policy_map.get(
                interface_name,
                []
            )
            #
            # Internet Policy Validation
            #

            if not internet_policies:
                status = "NO_INTERNET_POLICY"
                details.append(
                    "No SD-WAN Internet policy found"
                )
            elif any(
                p.get("status") != "enable"
                for p in internet_policies
            ):
                status = "DISABLED_INTERNET_POLICY"
                details.append(
                    "Internet policy disabled"
                )
            #
            # VLAN validation
            #
            if (
                c.get("vlan_id") is not None
                and fg.get("vlan_id") is not None
                and str(c.get("vlan_id"))
                != str(fg.get("vlan_id"))
            ):

                status = "VLAN_MISMATCH"

                details.append(
                    f"Customer VLAN {c.get('vlan_id')} differs from FortiGate VLAN {fg.get('vlan_id')}"
                )

            #
            # SUBNET validation
            #
            if (
                c.get("subnet_cidr")
                and fg.get("cidr")
                and c.get("subnet_cidr").strip()
                != fg.get("cidr").strip()
            ):

                status = (
                    "SUBNET_MISMATCH"
                    if status == "MATCH"
                    else "VLAN_AND_SUBNET_MISMATCH"
                )

                details.append(
                    f"Customer subnet {c.get('subnet_cidr')} differs from FortiGate subnet {fg.get('cidr')}"
                )

            #
            # Interface health
            #
            if (
                fg.get("interface_status")
                and fg.get("interface_status").lower() != "up"
            ):

                if status == "MATCH":
                    status = "INTERFACE_DOWN"

                details.append(
                    f"Interface status is {fg.get('interface_status')}"
                )


        if status == "MATCH":
            counts["match"] += 1

        elif status in (
            "NO_VLAN_SUBNET_MATCH",
            "NO_INTERNET_POLICY"
        ):
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
            "internet_policy_count":
                len(internet_policies),
            "internet_policy_ids":
                ",".join(
                    str(p.get("policyid"))
                    for p in internet_policies
                ),
            "internet_policy_status":
                ",".join(
                    p.get("status")
                    for p in internet_policies
                ),
        })

    #
    # INFRASTRUCTURE / UNASSIGNED
    #
    for fg in interfaces:

        if is_ignored(fg):
            continue

        name = (fg.get("name") or "").strip()

        if fg.get("vlan_id") in INFRA_VLANS:

            counts["infrastructure"] += 1

            findings.append({
                "customer_id": None,
                "licensee": None,
                "booth_group": None,
                "customer_vlan": None,
                "customer_subnet": None,
                "fortigate_interface": name,
                "fg_vlan": fg.get("vlan_id"),
                "fg_subnet": fg.get("cidr"),
                "interface_status": fg.get("interface_status"),
                "policy_id": fg.get("policy_id"),
                "policy_name": fg.get("policy_name"),
                "policy_status": fg.get("policy_status"),
                "reconciliation_status": "INFRASTRUCTURE",
                "details": "Reserved non-customer VLAN"
            })

            continue

        if name not in assigned_names:

            counts["unassigned"] += 1

            findings.append({
                "customer_id": None,
                "licensee": None,
                "booth_group": None,
                "customer_vlan": None,
                "customer_subnet": None,
                "fortigate_interface": name,
                "fg_vlan": fg.get("vlan_id"),
                "fg_subnet": fg.get("cidr"),
                "interface_status": fg.get("interface_status"),
                "policy_id": fg.get("policy_id"),
                "policy_name": fg.get("policy_name"),
                "policy_status": fg.get("policy_status"),
                "reconciliation_status": "UNASSIGNED_INTERFACE",
                "details": "Customer-facing interface not assigned"
            })

    return {
        "summary": counts,
        "results": findings
    }


@app.get('/api/fortigate/report')
def fg_report():
    rows = db.rows(
    """
        SELECT
            f.name AS interface_name,
            f.vlan_id AS fg_vlan,
            f.cidr AS fg_subnet,
            f.gateway AS fg_gateway,
            f.interface_status,
            c.licensee AS current_customer,
            c.booth_group,
            c.vlan_id AS customer_vlan,
            c.subnet_cidr AS customer_subnet
        FROM fortigate_interfaces f
        LEFT JOIN customers c
            ON c.fortigate_interface = f.name
        AND c.status='active'
        ORDER BY f.name
    """)

    
    fg = FortiGateClient()
    policies = fg.get_policies().get("results", [])
    
    policy_map = {}
    for p in policies:
        dst = [
            x.get("name","").lower()
            for x in p.get("dstintf", [])
        ]
        if "virtual-wan-link" not in dst:
            continue
        for src in p.get("srcintf", []):
            iface = src.get("name")
            if not iface:
                continue
            policy_map.setdefault(
                iface,
                []
            ).append({
                "policyid": p.get("policyid"),
                "name": p.get("name"),
                "status": p.get("status")
            })
            
        for r in rows:
            iface = r.get("interface_name")
            internet_policies = policy_map.get(
                iface,
                []
            )
            iface_status = (
                r.get("interface_status") or ""
            ).lower()

            if not internet_policies:
                if iface_status == "up":
                    result = "NO INTERNET POLICY"
                else:
                    result = "INTERFACE DOWN"
            elif any(
                p["status"] != "enable"
                for p in internet_policies
            ):
                if iface_status == "up":
                        result = "POLICY DISABLED"
                else:
                        result = "INTERFACE DOWN"
            else:
                if iface_status == "up":
                    result = "OK"
                else:
                    result = "INTERFACE DOWN"

            r["internet_policy_ids"] = ",".join(
                str(p["policyid"])
                for p in internet_policies
            )


            r["internet_policy_result"] = result      
 
    return rows
  
    
@app.post('/api/fortigate/toggle')
def fg_toggle(p:TogglePayload):
    plans=[action_plan('interface',p.interface_name,enable=p.enable)]
    if p.policy_id: plans.append(action_plan('policy',p.interface_name,p.policy_id,p.enable))
    res=[apply_or_dry_run(x) if p.apply else {'applied':False,'mode':'dry-run','plan':x} for x in plans]
    db.audit('fg_toggle',p.interface_name,p.model_dump_json(),json.dumps(res)); return {'results':res}

@app.get('/api/report.xlsx')
def report_xlsx():
    return StreamingResponse(build_report(CACHE),media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':'attachment; filename=citypoint_cmdb_report.xlsx'})

          
            
@app.get("/api/switches")
def api_switches():
    return CACHE.get(
    "ruckus_switches",
    []
    )

