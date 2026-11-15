# Setting up Oracle + SQL Developer on your laptop (Windows)

The project works with **either** of these. Both were tested.

| | **Oracle AI Database 26ai Free** | **Oracle Database 21c** (`WINDOWS.X64_213000_db_home.zip`) |
|---|---|---|
| Size / effort | Smaller, simpler installer | Full edition, larger, a few more installer screens |
| Service name you'll use | `FREEPDB1` | `ORCLPDB` (the "pluggable database name" from the installer) |
| Port | `1521` | `1521` |
| SQL Developer | Separate download | Usually included in the Oracle home (`sqldeveloper` folder); otherwise download it |

> **You don't need to set any Windows environment variables.** The Oracle installer configures itself, and the project's Python code connects without any Oracle client software. The only setting, the service name, is asked for once by the setup script and saved in `backend\.env`.

> **SQL Developer is Oracle's tool.** MySQL Workbench cannot open an Oracle database.

> Prefer double-click scripts? Install Oracle (Part A), then follow [run-local/README.md](README.md); it automates Parts B–D.

## What you need
- Windows 10/11 (64-bit), at least 8 GB RAM, 10–15 GB free disk
- Python 3.10+ (tick **"Add python.exe to PATH"**) and Node.js 18+ (LTS)

---

## Part A: Install Oracle (choose ONE)

### Option 1: Oracle AI Database 26ai Free
1. Download **Oracle Database Free for Windows** (oracle.com/database/free) and unzip it.
2. Right-click **setup.exe** and choose **Run as administrator**. Click through, and **write down the password** you choose.
3. It finishes with host `localhost`, port `1521`, pluggable database **`FREEPDB1`**.

### Option 2: Oracle Database 21c (`WINDOWS.X64_213000_db_home.zip`)
1. Create the folder where Oracle will live, e.g. `C:\app\oracle\product\21c\dbhome_1`, and **unzip the file directly into it**. The unzipped folder *is* the Oracle installation, so don't move it afterwards. Avoid spaces in the path.
2. In that folder, right-click **setup.exe** and choose **Run as administrator**.
3. Choose **Create and configure a single instance database**, then **Desktop class**.
4. On the settings screen, write these down:
   - **Global database name**: e.g. `orcl`
   - **Password**: used for SYS and SYSTEM. Write it down.
   - **Create as Container database**: ticked, with **Pluggable database name** `orclpdb`
5. Click **Install** and wait (often 20–40 minutes).
6. **Make the pluggable database open automatically** after a restart. On 21c it sometimes stays closed, which gives `ORA-01109`. In SQL Developer, connect as **sys**, Role **SYSDBA**, service name **`orcl`**, and run once:
   ```sql
   ALTER PLUGGABLE DATABASE ALL OPEN;
   ALTER PLUGGABLE DATABASE ALL SAVE STATE;
   ```

The installer registers Oracle as Windows services that start automatically. It also sets its own `ORACLE_HOME`/`PATH`, so you don't need to do anything.

---

## Part B: SQL Developer
- **21c:** look for `sqldeveloper\sqldeveloper.exe` inside your Oracle folder.
- **26ai, or if it's missing:** download **Oracle SQL Developer** (Windows 64-bit, **with JDK included**), unzip it and run `sqldeveloper.exe`.

## Part C: Create the project user, tables and demo data

### Easiest: let the script do it
After installing the Python packages (`run-local\1-install.bat`, or `pip install -r requirements.txt`), double-click `run-local\2-setup-database.bat`, or run `python setup_db.py --create-user` in `backend`. It asks:
```
Service name [FREEPDB1]:     ← press Enter for 26ai, or type ORCLPDB for 21c
Port [1521]:                 ← press Enter
Oracle SYSTEM password:      ← the password from the install (hidden while typing)
```
It creates everything and saves the service name in `backend\.env`, so the app uses it too.

### Or by hand in SQL Developer
1. New connection as **system**: Hostname `localhost`, Port `1521`, **Service name** `FREEPDB1` (26ai) or `ORCLPDB` (21c). Click **Test**, then **Connect**.
2. Open `database/00_create_user.sql` and press **F5** (Run Script). It prints `User INVENTORY created in …`.
3. New connection as **inventory** / **inventory123**, with the same host, port and service name.
4. In that connection, run with **F5**, in order: `01_schema.sql`, `02_inventory_pkg.sql`, `03_seed_data.sql`.
5. **21c only:** create `backend\.env` containing `ORACLE_DSN=localhost:1521/ORCLPDB`. Copy `backend\.env.example` and edit it.

> Always use **F5 (Run Script)** for these files. **Ctrl+Enter** runs only one statement.

## Part D: Start the app
Double-click `run-local\START-APP.bat`, or start the backend (`uvicorn app.main:app`) and the website (`npm start`) by hand. Log in as `admin@inventory.com` / `admin123`.

---

## Day-of-demo checklist
- [ ] SQL Developer can connect as INVENTORY. If not, see `ORA-01109` / `ORA-12541` below.
- [ ] `START-APP.bat` is running, and http://localhost:8000/api/health shows `"status":"ok"` and your Oracle version
- [ ] SQL Developer open with `database/04_demo_queries.sql` loaded
- [ ] Optional: `5-reset-demo-data.bat` for fresh demo data

**Remember `COMMIT;`** after your own `INSERT`/`UPDATE` in SQL Developer, or the website won't see the change. The `inventory_pkg` procedures commit by themselves.

## Troubleshooting

| Error | Cause | Fix |
|---|---|---|
| `ORA-12541: Cannot connect. No listener` / `DPY-6005` | Oracle isn't running | Win+R → `services.msc`, then start the services whose names begin with **Oracle** (the listener, and `OracleServiceORCL` or `OracleServiceFREE`) |
| `ORA-12514: service ... not registered` | Wrong service name | 26ai: `FREEPDB1`. 21c: `ORCLPDB` (your pluggable database name). Use **Service name**, not SID. Wait 1–2 min after Oracle starts. |
| `ORA-01109: database not open` | 21c pluggable database is closed | Part A, Option 2, step 6 (`ALTER PLUGGABLE DATABASE ALL OPEN; … SAVE STATE;`) |
| `ORA-01017: invalid username/password` | Wrong password | SYSTEM: the password from the install. INVENTORY: `inventory123`. |
| `ORA-20000: You are connected to the root container` | You used the container's name (`orcl`, `FREE`) | Use the **pluggable** database's service name; the message lists it |
| `ORA-65096: invalid common user or role name` | Same as above | Same as above |
| `ORA-00942: table or view does not exist` | Scripts were run as SYSTEM | Run 01–03 using the **INVENTORY** connection |
| `ORA-20001: Not enough stock ...` | Expected: the database is enforcing the stock rule | — |
| Website: *Cannot connect to the Oracle database* | Oracle stopped, or wrong service in `backend\.env` | Start Oracle. Check `ORACLE_DSN` in `backend\.env`. |
| `.venv\Scripts\activate` "running scripts is disabled" | PowerShell security setting | Use the `.bat` scripts, or run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once |
