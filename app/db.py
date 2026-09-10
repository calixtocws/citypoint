import pymysql
import pymysql.cursors
from dbutils.pooled_db import PooledDB
from .config import MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE
SCHEMA = """
CREATE TABLE IF NOT EXISTS booths (
  booth_group VARCHAR(255) PRIMARY KEY,
  status VARCHAR(32) DEFAULT 'available'
);
CREATE TABLE IF NOT EXISTS vlans (
  vlan_id INT PRIMARY KEY,
  status VARCHAR(32) DEFAULT 'available'
);
CREATE TABLE IF NOT EXISTS subnets (
  cidr VARCHAR(64) PRIMARY KEY,
  gateway VARCHAR(64) NOT NULL,
  mask VARCHAR(64) NOT NULL,
  status VARCHAR(32) DEFAULT 'available'
);
CREATE TABLE IF NOT EXISTS customers (
  id INT PRIMARY KEY AUTO_INCREMENT,
  licensee TEXT NOT NULL,
  legal_name TEXT,
  booth_group VARCHAR(255),
  vlan_id INT,
  subnet_cidr VARCHAR(64),
  fortigate_interface VARCHAR(255),
  status VARCHAR(32) DEFAULT 'active',
  notes TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS fortigate_interfaces (
  name VARCHAR(255) PRIMARY KEY,
  vlan_id INT,
  cidr VARCHAR(64),
  gateway VARCHAR(64),
  ip_raw VARCHAR(64),
  policy_id VARCHAR(64),
  policy_name VARCHAR(255),
  policy_status VARCHAR(64),
  interface_status VARCHAR(64),
  raw_json TEXT,
  refreshed_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS audit_log (
  id INT PRIMARY KEY AUTO_INCREMENT,
  action VARCHAR(255) NOT NULL,
  object_name TEXT,
  payload TEXT,
  result TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""
_pool = PooledDB(
    creator=pymysql,
    mincached=1,
    maxcached=5,
    maxconnections=20,
    blocking=True,
    ping=1,
    host=MYSQL_HOST,
    port=MYSQL_PORT,
    user=MYSQL_USER,
    password=MYSQL_PASSWORD,
    database=MYSQL_DATABASE,
    charset='utf8mb4',
    cursorclass=pymysql.cursors.DictCursor,
    autocommit=False,
    connect_timeout=10,
    read_timeout=20,
    write_timeout=20,
)
def connect():
    return _pool.connection()
def init_db():
    with connect() as con:
        with con.cursor() as cur:
            for statement in SCHEMA.split(';'):
                statement = statement.strip()
                if statement:
                    cur.execute(statement)
        con.commit()
def to_pymysql(sql):
    return sql.replace('%', '%%').replace('?', '%s')
def rows(sql, params=()):
    with connect() as con:
        with con.cursor() as cur:
            cur.execute(to_pymysql(sql), params)
            return cur.fetchall()
def execute(sql, params=()):
    with connect() as con:
        with con.cursor() as cur:
            cur.execute(to_pymysql(sql), params)
            con.commit()
            return cur.lastrowid
def audit(action, object_name=None, payload=None, result=None):
    execute("INSERT INTO audit_log(action, object_name, payload, result) VALUES (?, ?, ?, ?)", (action, object_name, payload, result))
