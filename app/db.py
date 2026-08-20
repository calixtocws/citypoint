import os, sqlite3
from .config import DATABASE_PATH
SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS booths (booth_group TEXT PRIMARY KEY, status TEXT DEFAULT 'available');
CREATE TABLE IF NOT EXISTS vlans (vlan_id INTEGER PRIMARY KEY, status TEXT DEFAULT 'available');
CREATE TABLE IF NOT EXISTS subnets (cidr TEXT PRIMARY KEY, gateway TEXT NOT NULL, mask TEXT NOT NULL, status TEXT DEFAULT 'available');
CREATE TABLE IF NOT EXISTS customers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  licensee TEXT NOT NULL,
  legal_name TEXT,
  booth_group TEXT,
  vlan_id INTEGER,
  subnet_cidr TEXT,
  fortigate_interface TEXT,
  status TEXT DEFAULT 'active',
  notes TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS fortigate_interfaces (
  name TEXT PRIMARY KEY,
  vlan_id INTEGER,
  cidr TEXT,
  gateway TEXT,
  ip_raw TEXT,
  policy_id TEXT,
  policy_name TEXT,
  policy_status TEXT,
  interface_status TEXT,
  raw_json TEXT,
  refreshed_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  action TEXT NOT NULL,
  object_name TEXT,
  payload TEXT,
  result TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""
def connect():
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    con = sqlite3.connect(DATABASE_PATH)
    con.row_factory = sqlite3.Row
    return con
def init_db():
    with connect() as con:
        con.executescript(SCHEMA); con.commit()
def rows(sql, params=()):
    with connect() as con:
        return [dict(r) for r in con.execute(sql, params).fetchall()]
def execute(sql, params=()):
    with connect() as con:
        cur = con.execute(sql, params); con.commit(); return cur.lastrowid
def audit(action, object_name=None, payload=None, result=None):
    execute("INSERT INTO audit_log(action, object_name, payload, result) VALUES (?, ?, ?, ?)", (action, object_name, payload, result))
