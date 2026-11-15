"""Refresh the self-contained run-local/ folder and run-local.zip from the main code.

The code is edited in backend/, frontend/ and database/. Run this after any change:
    python tools/build_run_local.py
It copies the files needed to run the app on a laptop (Option A) into run-local/,
leaving out installed packages and build output, and rebuilds run-local.zip.
"""
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "run-local"

# folder -> names to leave out (installed packages, caches, build output, secrets, hosting-only files)
COPIES = {
    "backend": {".venv", "__pycache__", ".pytest_cache", ".env", "inventory.db", "test_inventory.db"},
    "frontend": {"node_modules", "dist", ".angular", "vercel.json", "README.md"},
    "database": set(),
}


def copy_tree(name: str, skip: set[str]) -> None:
    src, dst = ROOT / name, OUT / name
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=lambda _dir, names: [n for n in names if n in skip or n.endswith(".pyc")])


def main() -> None:
    for name, skip in COPIES.items():
        copy_tree(name, skip)
        print(f"copied {name}/")

    guide = (ROOT / "docs" / "ORACLE_SETUP.md").read_text(encoding="utf-8")
    guide = guide.replace("../run-local/README.md", "README.md")
    (OUT / "ORACLE_SETUP.md").write_text(guide, encoding="utf-8")
    print("copied ORACLE_SETUP.md")

    zip_path = ROOT / "run-local.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(OUT.rglob("*")):
            if path.is_file():
                zf.write(path, Path("run-local") / path.relative_to(OUT))
    print(f"wrote {zip_path.name} ({zip_path.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
