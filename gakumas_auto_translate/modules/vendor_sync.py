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
    "build-dear-summaries.ts",
)

# 术语表只留一份：仓库根的 name_dictionary.json（本地菜单的人名替换用的
# 也是它），避免线上线下两套译名分叉。引擎侧保留 glossary.json 这个文件名，
# 不用改 tm.ts 的 import。
RENAMED_VENDOR_FILES = {"glossary.json": "name_dictionary.json"}


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

    sources = {name: vendor_dir / name for name in SYNCED_VENDOR_FILES}
    for name, origin in RENAMED_VENDOR_FILES.items():
        sources[name] = repository_root / origin
    missing = [str(path) for path in sources.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError("缺少 vendor 文件: " + ", ".join(missing))

    changed: list[str] = []
    for name, source in sources.items():
        destination = destination_dir / name
        if destination.is_file() and _sha256(source) == _sha256(destination):
            continue
        shutil.copy2(source, destination)
        changed.append(name)
        report(f"已同步翻译引擎文件: {name}")
    if not changed:
        report("翻译引擎文件已是最新，无需同步")
    return changed
