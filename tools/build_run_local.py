"""Build the two self-contained laptop folders inside run-local/ from the main code:

    run-local/oracle21c/    Oracle Database 21c          (service ORCLPDB)
    run-local/oracle26ai/   Oracle AI Database 26ai Free (service FREEPDB1)

Each has its own database/, backend/ and frontend/ code, scripts and instructions.

The code is edited in backend/, frontend/ and database/; the double-click scripts and
README are templates in tools/run_local_template/. Run this after any change:
    python tools/build_run_local.py
Both folders contain the same code. They differ only in the default Oracle service name
and in the instructions, which describe just that one Oracle version.
"""
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "run-local"
TEMPLATE = ROOT / "tools" / "run_local_template"
DEFAULT_DSN = "localhost:1521/FREEPDB1"

# folder -> names to leave out (installed packages, caches, build output, secrets, hosting-only files)
COPIES = {
    "backend": {".venv", "__pycache__", ".pytest_cache", ".env", "inventory.db", "test_inventory.db"},
    "frontend": {"node_modules", "dist", ".angular", "vercel.json", "README.md"},
    "database": set(),
}

ORA01109_ROW = ("| `ORA-01109: database not open` | See [ORACLE_SETUP.md](ORACLE_SETUP.md), "
                "Part A, step 6 (`ALTER PLUGGABLE DATABASE ALL OPEN; ... SAVE STATE;`) |\n")

VARIANTS = {
    "oracle21c": {
        "ORACLE": "Oracle Database 21c",
        "ORACLE_SHORT": "Oracle 21c",
        "ORACLE_BOX": "Oracle Database 21c ",
        "ORACLE_FILE": " (`WINDOWS.X64_213000_db_home.zip`)",
        "SERVICE": "ORCLPDB",
        "PAD": "    ",
        "SQLDEV": "Usually included with 21c: `sqldeveloper\\sqldeveloper.exe` inside your Oracle folder. If it's missing, d",
        "ORA01109_ROW": ORA01109_ROW,
        "OTHER": "Oracle 26ai Free",
        "OTHER_FOLDER": "oracle26ai",
        "keep_option": 2,
        "guide_lines": {
            "Service name [FREEPDB1]:     ← press Enter for 26ai, or type ORCLPDB for 21c":
                "Service name [ORCLPDB]:      ← press Enter (or type the pluggable database name you chose)",
            "**Service name** `FREEPDB1` (26ai) or `ORCLPDB` (21c).": "**Service name** `ORCLPDB`.",
                        "| 26ai: `FREEPDB1`. 21c: `ORCLPDB` (your pluggable database name).":
                "| `ORCLPDB` (your pluggable database name).",
            "Part A, Option 2, step 6": "Part A, step 6",
            "- **26ai, or if it's missing:** download": "- **If it's missing:** download",
        },
        # the default service is already ORCLPDB in this folder, so no .env step is needed
        "drop_lines": ["5. **21c only:** create"],
    },
    "oracle26ai": {
        "ORACLE": "Oracle AI Database 26ai Free",
        "ORACLE_SHORT": "Oracle 26ai Free",
        "ORACLE_BOX": "Oracle 26ai Free    ",
        "ORACLE_FILE": "",
        "SERVICE": "FREEPDB1",
        "PAD": "   ",
        "SQLDEV": "D",
        "ORA01109_ROW": "",
        "OTHER": "Oracle 21c",
        "OTHER_FOLDER": "oracle21c",
        "keep_option": 1,
        "guide_lines": {
            "Service name [FREEPDB1]:     ← press Enter for 26ai, or type ORCLPDB for 21c":
                "Service name [FREEPDB1]:     ← press Enter",
            "**Service name** `FREEPDB1` (26ai) or `ORCLPDB` (21c).": "**Service name** `FREEPDB1`.",
            "| 26ai: `FREEPDB1`. 21c: `ORCLPDB` (your pluggable database name).": "| Use `FREEPDB1`.",
            "- **26ai, or if it's missing:** download": "- Download",
        },
        # lines that only apply to 21c
        "drop_lines": ["- **21c:** look for", "5. **21c only:** create", "| `ORA-01109: database not open`"],
    },
}


def fill(text: str, values: dict) -> str:
    for key, value in values.items():
        if isinstance(value, str):
            text = text.replace("{{" + key + "}}", value)
    left = re.findall(r"\{\{\w+\}\}", text)
    assert not left, f"unfilled placeholders: {left}"
    return text


def must_replace(text: str, old: str, new: str, where: str) -> str:
    assert old in text, f"{where}: text not found: {old!r}"
    return text.replace(old, new)


def oracle_guide(v: dict) -> str:
    """docs/ORACLE_SETUP.md cut down to the one Oracle version this folder is for."""
    text = (ROOT / "docs" / "ORACLE_SETUP.md").read_text(encoding="utf-8")
    # intro: replace the 26ai-vs-21c comparison table with a line about this version
    start = text.index("The project works with **either**")
    end = text.index("> **You don't need to set")
    text = (text[:start] + f"This folder is for **{v['ORACLE']}**. You'll use host `localhost`, port `1521`, "
            f"service name **`{v['SERVICE']}`**.\n\n" + text[end:])
    text = must_replace(text, "then follow the README in [run-local/oracle21c](../run-local/oracle21c/README.md) or "
                        "[run-local/oracle26ai](../run-local/oracle26ai/README.md)",
                        "then follow [README.md](README.md)", "guide")
    # Part A: keep only this version's install option
    start = text.index("### Option 1:")
    middle = text.index("### Option 2:")
    end = text.index("The installer registers Oracle")
    option = text[start:middle] if v["keep_option"] == 1 else text[middle:end]
    option = re.sub(r"^### Option \d: ", "### ", option)
    text = text[:start] + option.rstrip() + "\n\n" + text[end:]
    text = must_replace(text, "## Part A: Install Oracle (choose ONE)", f"## Part A: Install {v['ORACLE']}", "guide")
    for old, new in v["guide_lines"].items():
        text = must_replace(text, old, new, "guide")
    lines = text.splitlines(keepends=True)
    for prefix in v.get("drop_lines", []):
        assert any(l.startswith(prefix) for l in lines), f"guide: line not found: {prefix!r}"
        lines = [l for l in lines if not l.startswith(prefix)]
    return "".join(lines)


def build(folder: str, v: dict) -> None:
    out = OUT_DIR / folder
    v = {**v, "FOLDER": folder}
    if out.exists():
        shutil.rmtree(out)
    out.mkdir()
    for name, skip in COPIES.items():
        shutil.copytree(ROOT / name, out / name,
                        ignore=lambda _d, names, skip=skip: [n for n in names if n in skip or n.endswith(".pyc")])

    # default Oracle service for this version (setup_db.py still lets you type another one)
    dsn = f"localhost:1521/{v['SERVICE']}"
    for rel in ("backend/app/config.py", "backend/.env.example"):
        path = out / rel
        path.write_text(must_replace(path.read_text(encoding="utf-8"), DEFAULT_DSN, dsn, rel), encoding="utf-8")

    for src in TEMPLATE.iterdir():
        if src.suffix == ".bat":   # keep Windows CRLF line endings
            (out / src.name).write_bytes(fill(src.read_bytes().decode("ascii"), v).encode("ascii"))
        else:
            (out / src.name).write_text(fill(src.read_text(encoding="utf-8"), v), encoding="utf-8")
    (out / "ORACLE_SETUP.md").write_text(oracle_guide(v), encoding="utf-8")

    print(f"built run-local/{folder}/")

def main() -> None:
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir()
    for folder, v in VARIANTS.items():
        build(folder, v)
    (OUT_DIR / "README.md").write_text(INDEX, encoding="utf-8")


INDEX = """# run-local: run everything on your laptop

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
"""


if __name__ == "__main__":
    main()
