from pathlib import Path
import shutil

main = Path('app/main.py')
if not main.exists():
    raise SystemExit('ERROR: Run this script from the citypoint_cmdb_app_v3 folder. app/main.py was not found.')

text = main.read_text(encoding='utf-8')
backup = main.with_suffix('.py.pre_v3_1_backup')
if not backup.exists():
    shutil.copy2(main, backup)

if 'def validate_unique_assignment(' not in text:
    marker = "@app.post('/api/customers')\n"
    helper = '''def validate_unique_assignment(p: CustomerPayload, exclude_customer_id: int | None = None):
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

'''
    if marker not in text:
        raise SystemExit('ERROR: Could not find POST customer endpoint marker. No changes made.')
    text = text.replace(marker, helper + marker, 1)

post_old = "def add_customer(p:CustomerPayload):\n    cid=db.execute("
post_new = "def add_customer(p:CustomerPayload):\n    validate_unique_assignment(p)\n    cid=db.execute("
if post_old in text and 'def add_customer(p:CustomerPayload):\n    validate_unique_assignment(p)' not in text:
    text = text.replace(post_old, post_new, 1)
elif 'def add_customer(p:CustomerPayload):\n    validate_unique_assignment(p)' not in text:
    raise SystemExit('ERROR: Could not patch add_customer endpoint. Restore backup if needed.')

put_old = "def edit_customer(customer_id:int,p:CustomerPayload):\n    db.execute("
put_new = "def edit_customer(customer_id:int,p:CustomerPayload):\n    validate_unique_assignment(p, exclude_customer_id=customer_id)\n    db.execute("
if put_old in text and 'def edit_customer(customer_id:int,p:CustomerPayload):\n    validate_unique_assignment(p, exclude_customer_id=customer_id)' not in text:
    text = text.replace(put_old, put_new, 1)
elif 'def edit_customer(customer_id:int,p:CustomerPayload):\n    validate_unique_assignment(p, exclude_customer_id=customer_id)' not in text:
    raise SystemExit('ERROR: Could not patch edit_customer endpoint. Restore backup if needed.')

main.write_text(text, encoding='utf-8')
print('SUCCESS: v3.1 uniqueness validation applied.')
print(f'Backup: {backup}')
print('Validated resources: Booth Group, VLAN, Subnet.')
print('HTTP conflict response: 409 with current assigned customer details.')
