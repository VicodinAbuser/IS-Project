# Option A: run everything on your laptop

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
│                              └── SQL / PL/SQL ──►  Oracle 26ai Free    │  Data tier
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

This folder contains only the guide and the start scripts. The application code is the same as for Option B, in `../backend`, `../frontend` and `../database`.

---

## One-time setup (about 1 hour, mostly downloads)

### Step 1: Install the software

| Software | Notes |
|---|---|
| **Oracle AI Database 26ai Free** (Windows) | Write down the **password** you choose during install (the SYSTEM password). See [../docs/ORACLE_SETUP.md](../docs/ORACLE_SETUP.md) steps 1–2. |
| **Oracle SQL Developer** | Windows 64-bit **with JDK included**. Just unzip and run `sqldeveloper.exe`. |
| **Python 3.10+** from python.org | On the first installer screen, tick **"Add python.exe to PATH"**. |
| **Node.js 18+ (LTS)** from nodejs.org | Click Next through the installer. |

You **don't** need to set any environment variables.

### Step 2: Get the project
On GitHub, click **Code → Download ZIP** and unzip it, for example to `C:\IS-Project`. Or run `git clone`.

### Step 3: Double-click `run-local\1-install.bat`
This installs the Python packages (backend) and Node packages (website). It takes about 3–10 minutes. It should end with **"Install finished"**.

### Step 4: Double-click `run-local\2-setup-database.bat`
Type your Oracle **SYSTEM password** when asked. Nothing appears while you type; that's normal. It creates:
- the `INVENTORY` database user (password `inventory123`)
- all tables, the PL/SQL package `INVENTORY_PKG`, the trigger and the views
- demo data, ending with `Seeded: 13 products, 4 outlets, 260 orders`

### Step 5: Connect SQL Developer (for showing the database)
New connection: **Username** `inventory`, **Password** `inventory123`, **Hostname** `localhost`, **Port** `1521`, **Service name** `FREEPDB1`.
Expand it to see **Tables**, **Views**, **Packages** and **Triggers**.

---

## Every time you use the app

**Double-click `run-local\START-APP.bat`**

It opens two windows, **Backend** and **Website**, and then the browser at **http://localhost:4200** after about 30 seconds.

- Log in as **admin@inventory.com / admin123** or **customer@inventory.com / customer123**.
- **Keep both windows open** while using the app.
- **To stop:** close the two windows, or press **Ctrl+C** in each.

Oracle starts automatically with Windows, so you don't need to start it yourself.

### The same thing by hand (if you prefer typing commands)
Open **Command Prompt** in the project folder.

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

## Presentation checklist
1. *(Optional)* Double-click `5-reset-demo-data.bat` for fresh demo data.
2. Double-click `START-APP.bat` and wait for the browser.
3. Open http://localhost:8000/api/health. It should say `"status":"ok"` and show the Oracle version.
4. Open SQL Developer with the INVENTORY connection and load `database\04_demo_queries.sql`.
5. Demo idea: buy something on the website, then `SELECT` it in SQL Developer. Then run `EXEC inventory_pkg.restock(...)` in SQL Developer and refresh the website's Inventory page.

**Remember `COMMIT;`** after your own `INSERT`/`UPDATE` in SQL Developer, or the website won't see the change. The `inventory_pkg` procedures commit by themselves.

## What each file does

| File | When | What it does |
|---|---|---|
| `1-install.bat` | once | Creates `backend\.venv` and installs the Python packages; runs `npm install` in `frontend` |
| `2-setup-database.bat` | once | Runs `database\00`–`03` against Oracle (asks for the SYSTEM password) |
| `START-APP.bat` | every time | Starts the backend and the website, then opens the browser |
| `3-start-backend.bat` | (used by START-APP) | `uvicorn app.main:app --reload` in `backend` |
| `4-start-website.bat` | (used by START-APP) | `npm start` in `frontend` |
| `5-reset-demo-data.bat` | optional | Wipes the project data and reloads fresh demo data |

## Problems?

| What you see | Fix |
|---|---|
| `[X] Python was not found` | Reinstall Python and tick **"Add python.exe to PATH"**, then open a new window |
| `Could not log in as SYSTEM ... ORA-01017` | Wrong SYSTEM password. Use the one from the Oracle install. |
| `Could not connect ... DPY-6005` or `ORA-12541` | Oracle isn't running. Open **Services** (Win+R → `services.msc`) and start the services whose names begin with **Oracle**. |
| Website says *Cannot reach the backend* | The Backend window was closed or shows an error. Run `3-start-backend.bat`. |
| Website says *Cannot connect to the Oracle database* | Backend is fine but Oracle isn't running (see above) |
| Login page **Test** shows *backend up, Oracle not reachable* | Same: start Oracle |
| Browser page is blank or can't connect | The website is still starting. Wait for "Local: http://localhost:4200/" in the Website window and refresh. |
| `Port 8000/4200 is already in use` | The app is already running in another window. Close the old windows first. |

More Oracle help: [../docs/ORACLE_SETUP.md](../docs/ORACLE_SETUP.md)
