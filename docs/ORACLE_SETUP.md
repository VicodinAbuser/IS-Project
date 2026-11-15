# Setting up Oracle 26ai Free + SQL Developer on your laptop (Windows)

Do this **once** on the laptop you'll use for the demo. It takes about 30–45 minutes.

> **SQL Developer is Oracle's tool.** MySQL Workbench cannot open an Oracle database.

## What you need
- Windows 10/11 (64-bit). Oracle Database Free doesn't run natively on macOS, so use a Windows laptop for the demo.
- At least 8 GB RAM and about 10 GB of free disk space
- Python 3.10 or newer, and Node.js 18 or newer

## Step 1: Install Oracle AI Database 26ai Free
1. Download **Oracle Database Free for Windows** from Oracle's website (oracle.com/database/free). It's a zip file.
2. Unzip it, right-click **setup.exe** and choose **Run as administrator**.
3. Click through the installer. When it asks for a **password**, write it down. This is the password for the `SYSTEM` user.
4. When it finishes, it shows connection details like these (the defaults):

   | Setting | Value |
   |---|---|
   | Host | `localhost` |
   | Port | `1521` |
   | Pluggable database (service name) | `FREEPDB1` |

Oracle now runs in the background as a Windows service and starts automatically with Windows.

## Step 2: Install SQL Developer
1. Download **Oracle SQL Developer**, choosing the Windows 64-bit version **with JDK included**.
2. Unzip it anywhere, for example `C:\sqldeveloper`, and run **sqldeveloper.exe**. There's no installer.

## Step 3: Create the project database user
1. In SQL Developer, click the green **+** (New Database Connection) and fill in:

   | Field | Value |
   |---|---|
   | Name | `SYSTEM local` |
   | Username | `system` |
   | Password | the password from Step 1 |
   | Hostname | `localhost` |
   | Port | `1521` |
   | **Service name** (not SID) | `FREEPDB1` |

2. Click **Test**. It should say *Success*. Then click **Connect**.
3. **File → Open** `database/00_create_user.sql` and press **F5** (Run Script).
   You should see `User created.` and `Grant succeeded.`

## Step 4: Create the tables, procedures and demo data
1. Make a second connection, the same as above but with username **`inventory`** and password **`inventory123`**. Name it `INVENTORY`.
2. Using the **INVENTORY** connection, open and run each file with **F5**, in this order:
   1. `database/01_schema.sql`: tables
   2. `database/02_inventory_pkg.sql`: package, trigger, views
   3. `database/03_seed_data.sql`: demo data. The last line prints `Seeded: 13 products, 4 outlets, 260 orders`.
3. In the left panel, expand the **INVENTORY** connection to see **Tables**, **Views**, **Packages** and **Triggers**.

> Always use **F5 (Run Script)** for these files. **Ctrl+Enter** runs only one statement.

## Step 5: Start the backend (Python)
Open **PowerShell** in the project folder:
```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```
Open http://localhost:8000/api/health. It should say `"status":"ok"`.

## Step 6: Start the website (Angular)
Open a **second** PowerShell window:
```powershell
cd frontend
npm install
npm start
```
Open http://localhost:4200 and log in as `admin@inventory.com` / `admin123`.

## Day-of-demo checklist
- [ ] Oracle is running. It starts with Windows; check that SQL Developer can connect.
- [ ] Backend window running `uvicorn` (step 5, without the `pip install`)
- [ ] Frontend window running `npm start`
- [ ] SQL Developer open with the INVENTORY connection and `database/04_demo_queries.sql` loaded
- [ ] Browser open at http://localhost:4200
- [ ] Optional: rerun `03_seed_data.sql` for fresh demo data

**Remember `COMMIT`.** SQL Developer doesn't save your own `INSERT`/`UPDATE`/`DELETE` until you run `COMMIT;`, so the website won't see them before that. The `inventory_pkg` procedures commit automatically.

## Troubleshooting

| Error | Cause | Fix |
|---|---|---|
| `ORA-12541: Cannot connect. No listener` | Oracle isn't running | Open **Services** (Win+R → `services.msc`), start the services whose names begin with **Oracle** (the listener and the database service), then try again |
| `ORA-12514: service ... not registered` | Wrong service name | Use **Service name** = `FREEPDB1` (not SID). Wait 1–2 minutes after Oracle starts. |
| `ORA-01017: invalid username/password` | Wrong password | SYSTEM uses the password you chose during install. INVENTORY uses `inventory123`. |
| `ORA-65096: invalid common user or role name` | User created in the root container | Run `00_create_user.sql` again; it switches to FREEPDB1 itself. Or connect SYSTEM with service name `FREEPDB1`. |
| `ORA-01031: insufficient privileges` on `ALTER SESSION SET CONTAINER` | | Connect SYSTEM with service name `FREEPDB1`, delete that one line from the script, and run it again |
| `ORA-00942: table or view does not exist` | Scripts were run as SYSTEM | Run 01–03 using the **INVENTORY** connection |
| `ORA-20001: Not enough stock ...` | Expected: the database is enforcing the stock rule | — |
| Backend: `DPY-6005: cannot connect to database` | Oracle not running, or different settings | Check that SQL Developer can connect. If your port or service is different, copy `backend/.env.example` to `backend/.env` and edit it. |
| `.venv\Scripts\activate` "running scripts is disabled" | PowerShell security setting | Run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, then try again |
| Website says "Cannot reach the server" | Backend not running | Start step 5 and keep that window open |
| Website shows no products | Demo data not loaded | Run `03_seed_data.sql` as INVENTORY |
