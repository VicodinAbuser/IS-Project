# run-local: run everything on your laptop

Pick the folder for the Oracle version installed on your laptop. Each folder is complete on its own:
its own `database/` (Oracle SQL), `backend/` (Python FastAPI), `frontend/` (Angular), double-click
scripts and step-by-step instructions.

| Your Oracle | Folder | Service name |
|---|---|---|
| **Oracle Database 21c** (`WINDOWS.X64_213000_db_home.zip`) | [oracle21c/](oracle21c/README.md) | `ORCLPDB` |
| **Oracle AI Database 26ai Free** | [oracle26ai/](oracle26ai/README.md) | `FREEPDB1` |

```
run-local/
├── oracle21c/     database/  backend/  frontend/  *.bat  README.md  ORACLE_SETUP.md
└── oracle26ai/    database/  backend/  frontend/  *.bat  README.md  ORACLE_SETUP.md
```

Use only one folder. Both create the same `INVENTORY` user and tables, so if you ever install both
Oracle versions, each folder talks only to its own database.

*For developers:* these folders are generated. Edit the code in the top-level `backend/`, `frontend/`
and `database/` folders, then run `python tools/build_run_local.py`.
