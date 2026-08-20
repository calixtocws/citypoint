# CityPoint CMDB App v3

Customer-list workflow for CityPoint booth/VLAN/subnet/FortiGate assignments.

## Features

- Main customer table linked to Subnet, Booth, VLAN, and FortiGate interface.
- Add operation at the top of the page.
- Each customer row has Edit and Delete buttons.
- Import uses the original `citypoint customers 8-2026.xlsx` workbook.
- Booths are kept as original booth-group objects.
- Customer object is Licensee + Legal Name.
- If a workbook row has more than one VLAN, VLAN is left empty and the VLANs are added to Notes.
- VLAN, booth, and subnet objects keep available/used status plus used_by.
- FortiGate API inventory: interface name, VLAN, subnet, and policy to SD-WAN.
- Dry-run only by default for interface/policy enable/disable operations.
- Excel report export with customer assignments and FortiGate interface mapping.

## Run

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
python -m uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000`.

Keep `ENABLE_FORTIGATE_WRITE=false` while testing.
