"""把本仓维护的翻译引擎文件同步到 GakumasPreTranslation/src。"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import Callable


# dear-summaries.json 是运行时状态，始终从 tools/vendor 原件读取，不能复制到
# 上游仓库的 src。translate-folder.ts 是入口脚本，由自动管线单独覆盖。
SYNCED_VENDOR_FILES = (
    "tm.ts",
    "translate.ts",
    "prompts.ts",
    "story-index.json",
    "character-cards.json",
    "glossary.json",
    "build-dear-summaries.ts",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sync_vendor_files(
    repository_root: Path,
    pretranslation_dir: Path,
    report: Callable[[str], None] = print,
) -> list[str]:
    """仅复制内容哈希不同的文件；缺少任一源文件时失败关闭。"""

    vendor_dir = repository_root / "tools" / "vendor"
    destination_dir = pretranslation_dir / "src"
    if not destination_dir.is_dir():
        raise FileNotFoundError(f"GakumasPreTranslation/src 不存在: {destination_dir}")

    missing = [name for name in SYNCED_VENDOR_FILES if not (vendor_dir / name).is_file()]
    if missing:
        raise FileNotFoundError("缺少 vendor 文件: " + ", ".join(missing))

    changed: list[str] = []
    for name in SYNCED_VENDOR_FILES:
        source = vendor_dir / name
        destination = destination_dir / name
        if destination.is_file() and _sha256(source) == _sha256(destination):
            continue
        shutil.copy2(source, destination)
        changed.append(name)
        report(f"已同步翻译引擎文件: {name}")
    if not changed:
        report("翻译引擎文件已是最新，无需同步")
    return changed
