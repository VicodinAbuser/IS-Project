# Setting up Oracle + SQL Developer on your laptop (Windows)

This folder is for **Oracle AI Database 26ai Free**. You'll use host `localhost`, port `1521`, service name **`FREEPDB1`**.

> **You don't need to set any Windows environment variables.** The Oracle installer configures itself, and the project's Python code connects without any Oracle client software. The only setting, the service name, is asked for once by the setup script and saved in `backend\.env`.

> **SQL Developer is Oracle's tool.** MySQL Workbench cannot open an Oracle database.

> Prefer double-click scripts? Install Oracle (Part A), then follow [README.md](README.md); it automates Parts B–D.

## What you need
- Windows 10/11 (64-bit), at least 8 GB RAM, 10–15 GB free disk
- Python 3.10+ (tick **"Add python.exe to PATH"**) and Node.js 18+ (LTS)

---

## Part A: Install Oracle AI Database 26ai Free

### Oracle AI Database 26ai Free
1. Download **Oracle Database Free for Windows** (oracle.com/database/free) and unzip it.
2. Right-click **setup.exe** and choose **Run as administrator**. Click through, and **write down the password** you choose.
3. It finishes with host `localhost`, port `1521`, pluggable database **`FREEPDB1`**.

The installer registers Oracle as Windows services that start automatically. It also sets its own `ORACLE_HOME`/`PATH`, so you don't need to do anything.

---

## Part B: SQL Developer
- Download **Oracle SQL Developer** (Windows 64-bit, **with JDK included**) from oracle.com/database/sqldeveloper, extract it to `C:\` and run `C:\sqldeveloper\sqldeveloper.exe`. Nothing to install.

## Part C: Create the project user, tables and demo data

### Easiest: let the script do it
After installing the Python packages (`1-install.bat`, or `pip install -r requirements.txt`), double-click `2-setup-database.bat`, or run `python setup_db.py --create-user` in `backend`. It asks:
```
Service name [FREEPDB1]:     ← press Enter
Port [1521]:                 ← press Enter
Oracle SYSTEM password:      ← the password from the install (hidden while typing)
```
It creates everything and saves the service name in `backend\.env`, so the app uses it too.

### Or by hand in SQL Developer
1. New connection as **system**: Hostname `localhost`, Port `1521`, **Service name** `FREEPDB1`. Click **Test**, then **Connect**.
2. Open `database/00_create_user.sql` and press **F5** (Run Script). It prints `User INVENTORY created in …`.
3. New connection as **inventory** / **inventory123**, with the same host, port and service name.
4. In that connection, run with **F5**, in order: `01_schema.sql`, `02_inventory_pkg.sql`, `03_seed_data.sql`.

> Always use **F5 (Run Script)** for these files. **Ctrl+Enter** runs only one statement.

## Part D: Start the app
Double-click `START-APP.bat`, or start the backend (`uvicorn app.main:app`) and the website (`npm start`) by hand. Log in as `admin@inventory.com` / `admin123`.

---

## Day-of-demo checklist
- [ ] SQL Developer can connect as INVENTORY. If not, see `ORA-01109` / `ORA-12541` below.
- [ ] `START-APP.bat` is running, and http://localhost:8000/api/health shows `"status":"ok"` and your Oracle version
- [ ] SQL Developer open with `database/04_demo_queries.sql` loaded
- [ ] Optional: `5-reset-demo-data.bat` for fresh demo data

**Always end your own changes in SQL Developer with `COMMIT;` (or `ROLLBACK;`).** Until then the website can't see the change, and the changed row stays locked, so the website waits for it. The `inventory_pkg` procedures never commit by themselves: the Python backend commits each whole action.

## Troubleshooting

| Error | Cause | Fix |
|---|---|---|
| `ORA-12541: Cannot connect. No listener` / `DPY-6005` | Oracle isn't running | Win+R → `services.msc`, then start the services whose names begin with **Oracle** (the listener, and `OracleServiceORCL` or `OracleServiceFREE`) |
| `ORA-12514: service ... not registered` | Wrong service name | Use `FREEPDB1`. Use **Service name**, not SID. Wait 1–2 min after Oracle starts. |
| `ORA-01017: invalid username/password` | Wrong password | SYSTEM: the password from the install. INVENTORY: `inventory123`. |
| `ORA-20000: You are connected to the root container` | You used the container's name (`orcl`, `FREE`) | Use the **pluggable** database's service name; the message lists it |
| `ORA-65096: invalid common user or role name` | Same as above | Same as above |
| `ORA-00942: table or view does not exist` | Scripts were run as SYSTEM | Run 01–03 using the **INVENTORY** connection |
| `ORA-20001: Not enough stock ...` | Expected: the database is enforcing the stock rule | — |
| Website: *Cannot connect to the Oracle database* | Oracle stopped, or wrong service in `backend\.env` | Start Oracle. Check `ORACLE_DSN` in `backend\.env`. |
| `.venv\Scripts\activate` "running scripts is disabled" | PowerShell security setting | Use the `.bat` scripts, or run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once |
