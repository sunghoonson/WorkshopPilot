from __future__ import annotations

import json
import zipfile
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SETTINGS_PATH = Path(__file__).with_name("snapshot_settings.json")
OUTPUT_DIR = PROJECT_ROOT / "snapshots"

def load_settings() -> dict:
    if not SETTINGS_PATH.is_file():
        return {}
    with SETTINGS_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)

def should_skip(path: Path, cfg: dict) -> bool:
    rel = path.relative_to(PROJECT_ROOT)
    excluded_dirs = set(cfg.get("exclude_dirs", []))
    excluded_exts = {x.lower() for x in cfg.get("exclude_extensions", [])}
    max_size = int(cfg.get("max_file_size_mb", 5)) * 1024 * 1024

    if any(part in excluded_dirs for part in rel.parts):
        return True

    if path.is_file():
        if path.suffix.lower() in excluded_exts:
            return True
        try:
            if path.stat().st_size > max_size:
                return True
        except OSError:
            return True

    return False

def collect_files(cfg: dict) -> list[Path]:
    items = []
    for path in PROJECT_ROOT.rglob("*"):
        if path.is_file() and not should_skip(path, cfg):
            items.append(path)
    return sorted(items, key=lambda p: str(p.relative_to(PROJECT_ROOT)).lower())

def make_tree(files: list[Path]) -> str:
    lines = [
        f"# {PROJECT_ROOT.name} project tree",
        "",
        f"Generated: {datetime.now():%Y-%m-%d %H:%M:%S}",
        "",
        "```text",
        PROJECT_ROOT.name,
    ]

    tree = {}
    for file in files:
        node = tree
        for part in file.relative_to(PROJECT_ROOT).parts:
            node = node.setdefault(part, {})

    def walk(node: dict, prefix: str = "") -> None:
        entries = list(node.items())
        for index, (name, child) in enumerate(entries):
            last = index == len(entries) - 1
            lines.append(prefix + ("└─ " if last else "├─ ") + name)
            if child:
                walk(child, prefix + ("   " if last else "│  "))

    walk(tree)
    lines.extend(["```", ""])
    return "\n".join(lines)

def main() -> int:
    cfg = load_settings()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = PROJECT_ROOT.name

    zip_path = OUTPUT_DIR / f"{base}_snapshot_{stamp}.zip"
    tree_path = OUTPUT_DIR / f"{base}_tree_{stamp}.md"
    log_path = OUTPUT_DIR / f"{base}_snapshot_{stamp}.log"

    files = collect_files(cfg)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in files:
            zf.write(file, file.relative_to(PROJECT_ROOT))

    tree_path.write_text(make_tree(files), encoding="utf-8")

    log_lines = [
        f"Project: {PROJECT_ROOT}",
        f"Generated: {datetime.now():%Y-%m-%d %H:%M:%S}",
        f"Files: {len(files)}",
        "",
        "Included files:",
        *[str(p.relative_to(PROJECT_ROOT)) for p in files],
    ]
    log_path.write_text("\n".join(log_lines), encoding="utf-8")

    print(f"[OK] ZIP : {zip_path}")
    print(f"[OK] TREE: {tree_path}")
    print(f"[OK] LOG : {log_path}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
