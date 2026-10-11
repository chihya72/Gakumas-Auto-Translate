"""Editable filenames excluded after preprocessing finds no translation rows."""

import json
from pathlib import Path


SKIP_LIST_FILE = Path(__file__).resolve().parents[2] / "untranslatable_files.json"


def load_untranslatable_files() -> set[str]:
    if not SKIP_LIST_FILE.exists():
        return set()
    filenames = json.loads(SKIP_LIST_FILE.read_text(encoding="utf-8-sig"))
    if not isinstance(filenames, list) or any(
        not isinstance(name, str) or not name.endswith(".txt") or Path(name).name != name
        for name in filenames
    ):
        raise ValueError(f"跳过名单必须是 TXT 文件名组成的 JSON 数组：{SKIP_LIST_FILE}")
    return set(filenames)


def add_untranslatable_file(filename: str) -> bool:
    filenames = load_untranslatable_files()
    if filename in filenames:
        return False
    filenames.add(filename)
    temporary = SKIP_LIST_FILE.with_suffix(".json.part")
    temporary.write_text(json.dumps(sorted(filenames), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(SKIP_LIST_FILE)
    return True
