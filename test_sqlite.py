import sqlite3

con = sqlite3.connect("C:\\Users\\CSanchez\\Documents\\python\\citypoint_cmdb_app_v3\\data\\citypoint_cmdb.sqlite3")

for row in con.execute(
    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
):
    print(row[0])