import ipaddress, json, requests
from . import config, db
class FortiGateError(Exception): pass
class FortiGateClient:
    def __init__(self):
        if not config.FORTIGATE_BASE_URL: raise FortiGateError('FORTIGATE_BASE_URL not configured')
        if not config.FORTIGATE_API_TOKEN: raise FortiGateError('FORTIGATE_API_TOKEN not configured')
        self.base=config.FORTIGATE_BASE_URL; self.session=requests.Session(); self.session.headers.update({'Authorization':f'Bearer {config.FORTIGATE_API_TOKEN}'})
        #print(self.url("/api/v2/cmdb/system/interface"))
    def url(self,path):
        sep='&' if '?' in path else '?'; return f"{self.base}{path}{sep}vdom={config.FORTIGATE_VDOM}"
    def request(self,method,path,payload=None):
        r=self.session.request(method,self.url(path),json=payload,verify=config.FORTIGATE_VERIFY_SSL,timeout=20)
        if r.status_code>=400: raise FortiGateError(f"{method} {path} failed: {r.status_code} {r.text[:500]}")
        try: return r.json()
        except Exception: return {'raw':r.text}
    def get_interfaces(self): return self.request('GET','/api/v2/cmdb/system/interface')
    def get_policies(self): return self.request('GET','/api/v2/cmdb/firewall/policy')
    def put(self,path,payload): return self.request('PUT',path,payload)
def results(x): return x.get('results',[]) if isinstance(x,dict) and isinstance(x.get('results'),list) else []
def ip_to_cidr(ip_raw):
    parts=str(ip_raw or '').split()
    if len(parts)<2: return (None, ip_raw or '')
    try:
        net=ipaddress.ip_network(f"{parts[0]}/{parts[1]}", strict=False); return (str(net), parts[0])
    except Exception: return (None, parts[0])
def names(obj): return [x.get('name') for x in obj if isinstance(x,dict)] if isinstance(obj,list) else []
def refresh_fortigate_cache():
    c=FortiGateClient(); ifaces=results(c.get_interfaces()); policies=results(c.get_policies()); bysrc={}; sdwan=config.FORTIGATE_SDWAN_INTERFACE.lower()
    for p in policies:
        if sdwan not in [str(x).lower() for x in names(p.get('dstintf'))]: continue
        for src in names(p.get('srcintf')): bysrc[src]=p
    db.execute('DELETE FROM fortigate_interfaces')
    for i in ifaces:
        name=i.get('name')
        if not name: continue
        cidr,gw=ip_to_cidr(i.get('ip')); p=bysrc.get(name,{})
        db.execute("REPLACE INTO fortigate_interfaces(name,vlan_id,cidr,gateway,ip_raw,policy_id,policy_name,policy_status,interface_status,raw_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (name,i.get('vlanid'),cidr,gw,i.get('ip'),str(p.get('policyid','')),p.get('name',''),p.get('status',''),i.get('status',''),json.dumps(i)))
    return {'interfaces':len(ifaces),'sdwan_policies':len(bysrc)}
def action_plan(kind,interface_name,policy_id=None,enable=True):
    if kind=='interface': return {'method':'PUT','path':f'/api/v2/cmdb/system/interface/{interface_name}','payload':{'status':'up' if enable else 'down'}}
    if kind=='policy': return {'method':'PUT','path':f'/api/v2/cmdb/firewall/policy/{policy_id}','payload':{'status':'enable' if enable else 'disable'}}
    raise ValueError('unknown kind')
def apply_or_dry_run(plan):
    if not config.ENABLE_FORTIGATE_WRITE: return {'applied':False,'reason':'ENABLE_FORTIGATE_WRITE=false','plan':plan}
    c=FortiGateClient(); return {'applied':True,'result':c.put(plan['path'],plan['payload'])}
