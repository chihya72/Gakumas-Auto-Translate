"""显式同步 tools/vendor 到 GakumasPreTranslation/src。"""

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if __name__ == "__main__":
    from gakumas_auto_translate.modules.vendor_sync import sync_vendor_files

    sync_vendor_files(ROOT, ROOT / "GakumasPreTranslation")
