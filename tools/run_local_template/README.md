# Option A: run everything on your laptop ({{ORACLE}})

> This folder is set up for **{{ORACLE}}** (service name **`{{SERVICE}}`**). Using {{OTHER}} instead? Use the **[{{OTHER_FOLDER}}](../{{OTHER_FOLDER}}/README.md)** folder next to this one.

In this option **your laptop is the server** for all three tiers. Nothing is hosted online, and nothing needs internet once it's installed. It's the most reliable setup for a classroom demo.

```
Your laptop
┌──────────────────────────────────────────────────────────────────────┐
│  Browser  ──►  Website (Angular)         http://localhost:4200        │  Presentation tier
│     │          started by 4-start-website.bat (npm start)              │
│     │                                                                  │
│     └── API calls ──►  Backend (FastAPI)  http://localhost:8000        │  Application tier
│                        started by 3-start-backend.bat                  │  (= uvicorn app.main:app)
│                              │                                         │
│                              └── SQL / PL/SQL ──►  {{ORACLE_BOX}}│  Data tier
│                                                    localhost:1521      │
│                                                    (Windows service)   │
│  SQL Developer ──────────────────────────────────►  same database     │
└──────────────────────────────────────────────────────────────────────┘
```

**What is `uvicorn app.main:app`?**
- **`uvicorn`** is the **application server**: a program that listens on port 8000, accepts HTTP requests and passes them to your Python code.
- **`app.main`** is the file `backend/app/main.py`.
- **`:app`** is the FastAPI object called `app` inside that file.

So the command means: *start the application server and run the FastAPI app defined in `backend/app/main.py`*. It must be run inside the `backend` folder, using the Python environment created by `1-install.bat`. `3-start-backend.bat` does exactly that for you.

**This folder is complete on its own.** It contains all the code needed to run the app:

```
run-local/{{FOLDER}}/
├── START-APP.bat, 1-install.bat, 2-setup-database.bat …   double-click scripts
├── README.md            this guide
├── ORACLE_SETUP.md      detailed Oracle + SQL Developer help
├── backend/             Python code (application server); app/main.py is what uvicorn starts
├── frontend/            Angular website code (src/app/...)
└── database/            Oracle SQL: tables, stored procedures, triggers, views, demo data, demo queries
```

---

## One-time setup (about 1 hour, mostly downloads)

### Step 1: Install the software

| Software | Notes |
|---|---|
| **{{ORACLE}}**{{ORACLE_FILE}} | Write down the **password** you choose during install (the SYSTEM password). Install steps: [ORACLE_SETUP.md](ORACLE_SETUP.md), Part A. |
| **Oracle SQL Developer** | {{SQLDEV}}ownload the Windows 64-bit version **with JDK included**, unzip it and run `sqldeveloper.exe`. |
| **Python 3.13** from python.org (Downloads → Windows → *Windows installer (64-bit)* of 3.13.x) | On the first installer screen, tick **"Add python.exe to PATH"**. Not 3.14/3.15: some packages aren't ready for them yet. |
| **Node.js 22 LTS** from nodejs.org/dist/latest-v22.x (the `-x64.msi` file) | Click Next through the installer; leave "Tools for Native Modules" unticked. |

You **don't** need to set any environment variables.

### Step 2: Get the code
Clone the repository (`git clone https://github.com/VicodinAbuser/IS-Project.git`), or on GitHub click **Code → Download ZIP** and extract it, to for example `C:\IS-Project`.
Then open the folder **`run-local\{{FOLDER}}`**. Everything below happens inside it.
*(Keep the folder structure as it is. The scripts look for `backend`, `frontend` and `database` next to them.)*
Later, to get a newer version of the code, double-click **`UPDATE.bat`** (see *Updating to a new version* below).

### Step 3: Double-click `run-local\{{FOLDER}}\1-install.bat`
This installs the Python packages (backend) and Node packages (website). It takes about 3–10 minutes. It should end with **"Install finished"**.

### Step 4: Double-click `run-local\{{FOLDER}}\2-setup-database.bat`
It asks three things:
```
Service name [{{SERVICE}}]:{{PAD}}← press Enter ({{SERVICE}} is right for {{ORACLE_SHORT}}; type your own name only if you chose a different one)
Port [1521]:               ← press Enter
Oracle SYSTEM password:    ← the password from the Oracle install (nothing appears while you type)
```
It creates:
- the `INVENTORY` database user (password `inventory123`)
- all 16 tables (users, profiles, permissions, products, orders ...), the stored procedures (`INVENTORY_PKG`), the triggers and the views
- demo data, ending with `Seeded: 13 products, 4 outlets, 7 users, 260 orders`

It also saves your service name in `backend\.env`, so the app connects to the same database. You don't need to set any environment variables.

### Step 5: Connect SQL Developer (for showing the database)
New connection: **Username** `inventory`, **Password** `inventory123`, **Hostname** `localhost`, **Port** `1521`, **Service name** `{{SERVICE}}`.
Expand it to see **Tables**, **Views**, **Packages** and **Triggers**. Click a table and open the **Columns** tab: every column has a description.

---

## Every time you use the app

**Double-click `run-local\{{FOLDER}}\START-APP.bat`**

It opens two windows, **Backend** and **Website**, and then the browser at **http://localhost:4200** after about 30 seconds.

- Log in by typing the email and password:

  | Who | Email | Password |
  |---|---|---|
  | Administrator (everything, incl. Users & access) | admin@inventory.com | admin123 |
  | Store manager | manager@inventory.com | admin123 |
  | Warehouse staff (stock and deliveries only) | warehouse@inventory.com | admin123 |
  | Customer | customer@inventory.com | customer123 |
- **Keep both windows open** while using the app.
- **To stop:** close the two windows, or press **Ctrl+C** in each.

Oracle starts automatically with Windows, so you don't need to start it yourself.

### The same thing by hand (if you prefer typing commands)
Open **Command Prompt** in the `run-local\{{FOLDER}}` folder.

Window 1, the backend:
```bat
cd backend
.venv\Scripts\activate
uvicorn app.main:app --reload
```
Window 2, the website:
```bat
cd frontend
npm start
```
Then open http://localhost:4200.

`--reload` restarts the backend automatically when you edit Python code.

---

## Share it online with your group (Vercel)

The website goes on Vercel (free); the backend and Oracle stay on this laptop and are reached
through a free **ngrok** tunnel with a fixed address. Full guide: `docs/DEPLOY_VERCEL.md` in the repository.

**One time:**
1. **ngrok:** sign up free at ngrok.com → *Share Localhost*, install it and run the `ngrok config add-authtoken ...`
   command it shows. Your free fixed domain is shown there (e.g. `your-name.ngrok-free.dev`).
2. **The website must know that domain:** it is written in `frontend/vercel.json` in the repository
   (`"destination": "https://<your domain>/api/:path*"`). If yours is different, change it there and push to GitHub.
3. **Vercel:** sign in with GitHub → **Add New → Project** → import the repository → *Import single project* for
   **`frontend`** → **Deploy**. The link under **Domains** (e.g. `https://is-project-inventory.vercel.app`) is the one your group uses, always.

**Every time your group should be able to use it:** double-click **`START-ONLINE.bat`**
(first time it asks for your ngrok domain and remembers it). Keep its windows open; Ctrl+C in the ngrok window to go offline.

**Local and online at the same time:** double-click `START-APP.bat` *and* `START-ONLINE.bat`, in any order.
They share one backend and the same Oracle data, so an order placed on the Vercel link shows up at
http://localhost:4200 and in SQL Developer, and the other way round.

| You want | Double-click | Website address |
|---|---|---|
| Only on your laptop | `START-APP.bat` | http://localhost:4200 |
| Only the public link | `START-ONLINE.bat` | your Vercel link |
| Both | both files | both addresses, same data |

Every `git push` to GitHub redeploys the website by itself. Changes to the backend or database only need
the laptop's copy updated (`UPDATE.bat`), then restart `START-ONLINE.bat`.

---

## Updating to a new version

Double-click **`UPDATE.bat`**. It downloads the latest code from GitHub and replaces the code in this folder,
but keeps your installed packages (`backend\.venv`, `frontend\node_modules`), your settings (`backend\.env`)
and your ngrok domain. Close the app's windows first. If the new version changed the database, also run
`2-setup-database.bat` (and `6-load-big-dataset.bat` if you use the large data set).

---

## Presentation checklist
1. *(Optional)* Double-click `5-reset-demo-data.bat` for fresh demo data.
2. Double-click `START-APP.bat` and wait for the browser.
3. Open http://localhost:8000/api/health. It should say `"status":"ok"` and show the Oracle version.
4. Open SQL Developer with the INVENTORY connection and load `database\04_demo_queries.sql`.
5. Demo idea: buy something on the website, then run query 13 in SQL Developer: the order is there, with the customer's name.
   Then run block 8 (a restock through the stored procedures) and refresh the website's Inventory page.

**Always end your own changes in SQL Developer with `COMMIT;` (or `ROLLBACK;`).** Until then the website can't see
the change, and a row you changed stays locked, so the website waits for it. The `inventory_pkg` procedures never
commit by themselves: the Python backend (or you) decides when the whole action is complete.

## The large dataset (50,000 customers)

The normal setup loads a small demo dataset (5 customers, ~260 orders). For a realistic demo,
double-click **`6-load-big-dataset.bat`** after `2-setup-database.bat`. It loads the CSV files in
`database\dataset\` (about 2–5 minutes):

| Table | Rows |
|---|---|
| users / customer_profiles / user_profiles | 50,003 / 50,000 / 50,003 (50,000 customers + 3 staff) |
| profiles / permissions / authorizations | 4 / 12 / 29 |
| orders / payments / deliveries | 89,260 each |
| order_items | 172,140 |
| stock_movements | 192,254 |
| products / outlets / inventory | 89 / 10 / 890 |

Every customer's password is `customer123` (e.g. `customer@inventory.com`); the 3 staff accounts use `admin123`.
To go back to the small demo data, run `5-reset-demo-data.bat`. Details: `database\dataset\README.md`.

## What each file does

| File | When | What it does |
|---|---|---|
| `1-install.bat` | once | Creates `backend\.venv` and installs the Python packages; runs `npm install` in `frontend` |
| `2-setup-database.bat` | once | Runs `database\00`–`03` against Oracle (asks for the SYSTEM password) |
| `START-APP.bat` | every time | Starts the backend and the website, then opens the browser |
| `START-ONLINE.bat` | to share online | Starts the backend and the ngrok tunnel, so the Vercel website reaches this laptop |
| `3-start-backend.bat` | (used by START-APP) | `uvicorn app.main:app --reload` in `backend` |
| `4-start-website.bat` | (used by START-APP) | `npm start` in `frontend` |
| `5-reset-demo-data.bat` | optional | Wipes the project data and reloads fresh demo data |
| `6-load-big-dataset.bat` | optional | Replaces the data with the large dataset: 50,000 customers, ~89,000 orders (`database\dataset\*.csv`) |
| `UPDATE.bat` | for new versions | Downloads the latest code from GitHub, keeps your packages and settings |

## Problems?

| What you see | Fix |
|---|---|
| `[X] Python was not found` | Reinstall Python and tick **"Add python.exe to PATH"**, then open a new window |
| `Could not log in as SYSTEM ... ORA-01017` | Wrong SYSTEM password. Use the one from the Oracle install. |
| `Could not connect ... DPY-6005` or `ORA-12541` | Oracle isn't running. Open **Services** (Win+R → `services.msc`) and start the services whose names begin with **Oracle**. |
| `ORA-12514` (service not registered) | Wrong service name. Run `2-setup-database.bat` again and type the pluggable database name you chose in the Oracle installer (default `{{SERVICE}}`). |
{{ORA01109_ROW}}| Website says *Cannot reach the server* | The Backend window was closed or shows an error. Run `3-start-backend.bat`. |
| Website says *Cannot connect to the Oracle database* | Backend is fine but Oracle isn't running (see above) |
| Login page says **We can’t connect right now**, and `http://localhost:8000/api/health` answers `"error"` | Same: start Oracle (the backend window prints the exact error) |
| *Too many wrong passwords* | The account is locked for 15 minutes after 5 wrong passwords. An admin can unlock it in **Users & access**. |
| The website hangs on a save after you used SQL Developer | You changed a row there without `COMMIT;` / `ROLLBACK;`. Run one of them in SQL Developer. |
| Browser page is blank or can't connect | The website is still starting. Wait for "Local: http://localhost:4200/" in the Website window and refresh. |
| `Port 8000/4200 is already in use` | The app is already running in another window. Close the old windows first. |

More Oracle help: [ORACLE_SETUP.md](ORACLE_SETUP.md)
