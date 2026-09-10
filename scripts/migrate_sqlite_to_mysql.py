"""
One-off migration: copy data from the legacy SQLite database into MySQL.

Usage:
    python -m scripts.migrate_sqlite_to_mysql [--source PATH]

The target MySQL connection is read from .env (MYSQL_HOST/PORT/USER/PASSWORD/DATABASE),
same as the app. Run `python -c "from app import db; db.init_db()"` first (or just start
the app once) so the MySQL schema exists before migrating.
"""
import argparse
import sqlite3

from app import db

TABLES = ["booths", "vlans", "subnets", "customers", "fortigate_interfaces", "audit_log"]


def read_sqlite(path):
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    data = {}
    for table in TABLES:
        data[table] = [dict(r) for r in con.execute(f"SELECT * FROM {table}").fetchall()]
    con.close()
    return data


def load_mysql(data):
    with db.connect() as con:
        with con.cursor() as cur:
            for table in reversed(TABLES):
                cur.execute(f"DELETE FROM {table}")
            for table in TABLES:
                rows = data[table]
                if not rows:
                    continue
                columns = list(rows[0].keys())
                placeholders = ", ".join(["%s"] * len(columns))
                col_list = ", ".join(columns)
                sql = f"INSERT INTO {table}({col_list}) VALUES ({placeholders})"
                cur.executemany(sql, [[r[c] for c in columns] for r in rows])
                print(f"{table}: inserted {len(rows)} rows")
        con.commit()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="./data/citypoint_cmdb.sqlite3")
    args = parser.parse_args()

    db.init_db()
    data = read_sqlite(args.source)
    load_mysql(data)
    print("Migration complete.")


if __name__ == "__main__":
    main()
