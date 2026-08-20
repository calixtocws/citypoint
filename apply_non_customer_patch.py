from pathlib import Path
from datetime import datetime
import ast
import re
import shutil
import sys


MAIN_FILE = Path("app/main.py")

INFRA_CONSTANTS = '''
# VLANs reserved for non-customer infrastructure.
# These VLANs remain visible in the object pool as "used",
# but cannot be selected when adding or editing customers.
INFRA_VLANS = set(range(191, 200)) | {900}

# FortiGate interfaces that are not customer-facing and therefore
# do not participate in CMDB reconciliation.
IGNORED_INTERFACES = {
    # VPN interfaces
    "GADC",
    "CalixtoAP",

    # FortiGate management/system interfaces
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

    # Physical FortiGate ports
    "port1", "port2", "port3", "port4",
    "port5", "port6", "port7", "port8",
    "port9", "port10", "port11", "port12",
    "port13", "port14", "port15", "port16",
    "port17", "port18", "port19", "port20",
    "port21", "port22", "port23", "port24",

    # Non-customer/remnant interfaces
    "x1", "x2", "x3", "x4",
}

IGNORED_INTERFACES_LOWER = {
    name.lower() for name in IGNORED_INTERFACES
}
'''.strip()


NEW_RECONCILIATION = r'''@app.get('/api/reconciliation')
def reconciliation():
    customers = db.rows("""
      SELECT id, licensee, legal_name, booth_group,
             vlan_id, subnet_cidr, fortigate_interface
      FROM customers
      WHERE status='active'
      ORDER BY licensee
    """)

    interfaces = db.rows("""
      SELECT *
      FROM fortigate_interfaces
      ORDER BY name
    """)

    def normalized_vlan(value):
        if value is None or value == "":
            return None

        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def normalized_cidr(value):
        return (value or "").strip()

    def is_ignored_interface(interface):
        name = (interface.get("name") or "").strip().lower()
        return name in IGNORED_INTERFACES_LOWER

    def is_infrastructure_interface(interface):
        vlan_id = normalized_vlan(interface.get("vlan_id"))
        return vlan_id in INFRA_VLANS

    # Ignored interfaces do not take part in customer reconciliation.
    customer_interfaces = [
        interface
        for interface in interfaces
        if not is_ignored_interface(interface)
        and not is_infrastructure_interface(interface)
    ]

    infrastructure_interfaces = [
        interface
        for interface in interfaces
        if not is_ignored_interface(interface)
        and is_infrastructure_interface(interface)
    ]

    by_name = {
        (interface.get("name") or "").strip(): interface
        for interface in customer_interfaces
        if (interface.get("name") or "").strip()
    }

    by_vlan_subnet = {
        (
            normalized_vlan(interface.get("vlan_id")),
            normalized_cidr(interface.get("cidr"))
        ): interface
        for interface in customer_interfaces
        if normalized_vlan(interface.get("vlan_id")) is not None
        and normalized_cidr(interface.get("cidr"))
    }

    assigned_names = set()
    findings = []

    counts = {
        "match": 0,
        "review": 0,
        "missing": 0,
        "unassigned": 0,
        "infrastructure": 0,
        "ignored": sum(
            1 for interface in interfaces
            if is_ignored_interface(interface)
        )
    }

    for customer in customers:
        customer_vlan = normalized_vlan(customer.get("vlan_id"))
        customer_subnet = normalized_cidr(
            customer.get("subnet_cidr")
        )

        interface_name = (
            customer.get("fortigate_interface") or ""
        ).strip()

        details = []
        fg = None

        # Customer records should never use reserved infrastructure VLANs.
        if customer_vlan in INFRA_VLANS:
            status = "RESERVED_NON_CUSTOMER_VLAN"

            details.append(
                f"VLAN {customer_vlan} is reserved for non-customer infrastructure"
            )

            counts["review"] += 1

            findings.append({
                "customer_id": customer.get("id"),
                "licensee": customer.get("licensee"),
                "booth_group": customer.get("booth_group"),
                "customer_vlan": customer_vlan,
                "customer_subnet": customer_subnet,
                "fortigate_interface": interface_name,
                "fg_vlan": None,
                "fg_subnet": None,
                "interface_status": None,
                "policy_id": None,
                "policy_name": None,
                "policy_status": None,
                "reconciliation_status": status,
                "details": "; ".join(details),
            })

            continue

        # Primary correlation: VLAN ID plus subnet CIDR.
        if customer_vlan is not None and customer_subnet:
            fg = by_vlan_subnet.get(
                (customer_vlan, customer_subnet)
            )

        # Fallback for an existing manual interface assignment.
        if not fg and interface_name:
            fg = by_name.get(interface_name)

        # Write the automatically correlated interface back to the customer.
        if fg:
            matched_name = (fg.get("name") or "").strip()

            if matched_name:
                assigned_names.add(matched_name)

            if matched_name and interface_name != matched_name:
                db.execute(
                    """
                    UPDATE customers
                    SET fortigate_interface=?,
                        updated_at=CURRENT_TIMESTAMP
                    WHERE id=?
                    """,
                    (
                        matched_name,
                        customer.get("id")
                    )
                )

                if interface_name:
                    details.append(
                        f"Interface assignment updated from "
                        f"{interface_name} to {matched_name}"
                    )
                else:
                    details.append(
                        f"Interface automatically assigned as {matched_name}"
                    )

                interface_name = matched_name

        status = "MATCH"

        if not fg:
            status = "NO_VLAN_SUBNET_MATCH"

            details.append(
                "No customer-facing FortiGate interface matches "
                "the customer VLAN and subnet"
            )

        else:
            fg_vlan = normalized_vlan(fg.get("vlan_id"))
            fg_subnet = normalized_cidr(fg.get("cidr"))

            vlan_mismatch = (
                customer_vlan is not None
                and fg_vlan is not None
                and customer_vlan != fg_vlan
            )

            subnet_mismatch = (
                bool(customer_subnet)
                and bool(fg_subnet)
                and customer_subnet != fg_subnet
            )

            if vlan_mismatch and subnet_mismatch:
                status = "VLAN_AND_SUBNET_MISMATCH"

            elif vlan_mismatch:
                status = "VLAN_MISMATCH"

            elif subnet_mismatch:
                status = "SUBNET_MISMATCH"

            if vlan_mismatch:
                details.append(
                    f"Customer VLAN {customer_vlan} differs from "
                    f"FortiGate VLAN {fg_vlan}"
                )

            if subnet_mismatch:
                details.append(
                    f"Customer subnet {customer_subnet} differs from "
                    f"FortiGate subnet {fg_subnet}"
                )

            interface_status = (
                fg.get("interface_status") or ""
            ).strip().lower()

            if interface_status and interface_status != "up":
                if status == "MATCH":
                    status = "INTERFACE_DOWN"

                details.append(
                    f"Interface status is "
                    f"{fg.get('interface_status')}"
                )

        if status == "MATCH":
            counts["match"] += 1

        elif status == "NO_VLAN_SUBNET_MATCH":
            counts["missing"] += 1

        else:
            counts["review"] += 1

        findings.append({
            "customer_id": customer.get("id"),
            "licensee": customer.get("licensee"),
            "booth_group": customer.get("booth_group"),
            "customer_vlan": customer_vlan,
            "customer_subnet": customer_subnet,
            "fortigate_interface": interface_name,
            "fg_vlan": (
                normalized_vlan(fg.get("vlan_id"))
                if fg else None
            ),
            "fg_subnet": (
                normalized_cidr(fg.get("cidr"))
                if fg else None
            ),
            "interface_status": (
                fg.get("interface_status")
                if fg else None
            ),
            "policy_id": (
                fg.get("policy_id")
                if fg else None
            ),
            "policy_name": (
                fg.get("policy_name")
                if fg else None
            ),
            "policy_status": (
                fg.get("policy_status")
                if fg else None
            ),
            "reconciliation_status": status,
            "details": "; ".join(details),
        })

    # Reserved non-customer interfaces remain visible for documentation,
    # but do not count as unassigned customer interfaces.
    for fg in infrastructure_interfaces:
        counts["infrastructure"] += 1

        findings.append({
            "customer_id": None,
            "licensee": None,
            "booth_group": None,
            "customer_vlan": None,
            "customer_subnet": None,
            "fortigate_interface": fg.get("name"),
            "fg_vlan": normalized_vlan(fg.get("vlan_id")),
            "fg_subnet": normalized_cidr(fg.get("cidr")),
            "interface_status": fg.get("interface_status"),
            "policy_id": fg.get("policy_id"),
            "policy_name": fg.get("policy_name"),
            "policy_status": fg.get("policy_status"),
            "reconciliation_status": "INFRASTRUCTURE",
            "details": (
                "Reserved non-customer infrastructure VLAN; "
                "not available for customer assignments"
            ),
        })

    # Only customer-facing interfaces can be reported as unassigned.
    for fg in customer_interfaces:
        interface_name = (fg.get("name") or "").strip()

        if interface_name not in assigned_names:
            counts["unassigned"] += 1

            findings.append({
                "customer_id": None,
                "licensee": None,
                "booth_group": None,
                "customer_vlan": None,
                "customer_subnet": None,
                "fortigate_interface": interface_name,
                "fg_vlan": normalized_vlan(fg.get("vlan_id")),
                "fg_subnet": normalized_cidr(fg.get("cidr")),
                "interface_status": fg.get("interface_status"),
                "policy_id": fg.get("policy_id"),
                "policy_name": fg.get("policy_name"),
                "policy_status": fg.get("policy_status"),
                "reconciliation_status": "UNASSIGNED_INTERFACE",
                "details": (
                    "Customer-facing FortiGate interface is not "
                    "assigned to an active customer"
                ),
            })

    return {
        "summary": counts,
        "results": findings
    }
'''


def find_function(tree, function_name):
    for node in tree.body:
        if isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef)
        ) and node.name == function_name:
            return node

    return None


def line_start_offset(lines, line_number):
    return sum(len(line) for line in lines[:line_number - 1])


def insert_constants(source):
    if "INFRA_VLANS =" in source:
        print("[SKIP] INFRA_VLANS already exists")
        return source

    tree = ast.parse(source)

    insertion_line = 1

    if tree.body:
        last_import = None

        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                last_import = node
            else:
                break

        if last_import:
            insertion_line = last_import.end_lineno + 1

    lines = source.splitlines(keepends=True)
    offset = line_start_offset(lines, insertion_line)

    block = "\n" + INFRA_CONSTANTS + "\n\n"

    return source[:offset] + block + source[offset:]


def patch_refresh_statuses(source):
    tree = ast.parse(source)
    node = find_function(tree, "refresh_statuses")

    if not node:
        raise RuntimeError(
            "Could not find refresh_statuses() in app/main.py"
        )

    marker = "Reserved non-customer VLANs must always remain used"

    if marker in source:
        print("[SKIP] refresh_statuses already patched")
        return source

    lines = source.splitlines(keepends=True)

    insertion_offset = sum(
        len(line) for line in lines[:node.end_lineno]
    )

    block = '''
    # Reserved non-customer VLANs must always remain used.
    # This final override prevents normal availability calculations
    # from returning VLANs 191-199 or VLAN 900 to "available".
    db.execute("""
        UPDATE vlans
        SET status='used'
        WHERE vlan_id BETWEEN 191 AND 199
           OR vlan_id=900
    """)
'''

    return (
        source[:insertion_offset]
        + block
        + source[insertion_offset:]
    )


def patch_vlan_dropdown(source):
    old_sql = (
        "'SELECT vlan_id,status FROM vlans ORDER BY vlan_id'"
    )

    new_sql = (
        "\"SELECT vlan_id,status FROM vlans "
        "WHERE vlan_id NOT BETWEEN 191 AND 199 "
        "AND vlan_id<>900 ORDER BY vlan_id\""
    )

    if old_sql in source:
        source = source.replace(old_sql, new_sql, 1)
        print("[OK] Customer VLAN dropdown patched")
        return source

    if (
        "WHERE vlan_id NOT BETWEEN 191 AND 199"
        in source
        and "vlan_id<>900" in source
    ):
        print("[SKIP] Customer VLAN dropdown already patched")
        return source

    raise RuntimeError(
        "Could not locate the VLAN dropdown query in app/main.py"
    )


def replace_reconciliation(source):
    tree = ast.parse(source)
    node = find_function(tree, "reconciliation")

    if not node:
        raise RuntimeError(
            "Could not find reconciliation() in app/main.py"
        )

    lines = source.splitlines(keepends=True)

    start_line = node.lineno

    if node.decorator_list:
        start_line = min(
            decorator.lineno
            for decorator in node.decorator_list
        )

    start_offset = line_start_offset(lines, start_line)

    end_offset = sum(
        len(line) for line in lines[:node.end_lineno]
    )

    replacement = NEW_RECONCILIATION.rstrip() + "\n\n"

    print("[OK] Reconciliation function replaced")

    return (
        source[:start_offset]
        + replacement
        + source[end_offset:]
    )


def validate_source(source):
    ast.parse(source)

    required = [
        "INFRA_VLANS",
        "IGNORED_INTERFACES",
        "RESERVED_NON_CUSTOMER_VLAN",
        "INFRASTRUCTURE",
        "UNASSIGNED_INTERFACE",
        "NO_VLAN_SUBNET_MATCH",
        "vlan_id NOT BETWEEN 191 AND 199",
        "vlan_id<>900",
    ]

    missing = [
        item for item in required
        if item not in source
    ]

    if missing:
        raise RuntimeError(
            "Patch validation failed. Missing: "
            + ", ".join(missing)
        )


def main():
    if not MAIN_FILE.exists():
        print(
            f"ERROR: {MAIN_FILE} was not found.\n"
            "Run this script from the project root."
        )
        sys.exit(1)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = MAIN_FILE.with_name(
        f"main.py.before_non_customer_patch_{timestamp}.bak"
    )

    shutil.copy2(MAIN_FILE, backup)

    print(f"[OK] Backup created: {backup}")

    source = MAIN_FILE.read_text(encoding="utf-8")

    try:
        source = insert_constants(source)
        source = patch_refresh_statuses(source)
        source = patch_vlan_dropdown(source)
        source = replace_reconciliation(source)
        validate_source(source)

        MAIN_FILE.write_text(
            source,
            encoding="utf-8",
            newline="\n"
        )

        print("[OK] Python syntax validation passed")
        print(f"[OK] Patched: {MAIN_FILE}")
        print()
        print("Next:")
        print("  1. Restart uvicorn")
        print("  2. Refresh the browser")
        print("  3. Run FortiGate Reconciliation")

    except Exception as error:
        shutil.copy2(backup, MAIN_FILE)

        print()
        print(f"ERROR: {error}")
        print(
            "The original app/main.py was restored "
            "from the backup."
        )

        sys.exit(1)


if __name__ == "__main__":
    main()