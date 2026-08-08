import tempfile
from pathlib import Path

from seed_work_repo import collect, is_unclaimed


# --refresh 的闸门：判错一次就会冲掉成员的在线编辑，宁可漏判不可误判
BOTH_EMPTY = "文件 `x`\n<!-- tr:: -->\n<!-- pr:: -->"
assert is_unclaimed(BOTH_EMPTY)
assert not is_unclaimed("文件 `x`\n<!-- tr::煉金術式 -->\n<!-- pr:: -->")
assert not is_unclaimed("文件 `x`\n<!-- tr:: -->\n<!-- pr::病毒 -->")
assert not is_unclaimed("文件 `x`\n<!-- tr::pm -->\n<!-- pr::mk2 -->")
# 空白不算认领人
assert is_unclaimed("<!-- tr::   -->\n<!-- pr:: -->")
# 老格式 / 缺标记 / 空 body：无从判断，一律当作有人在做
assert not is_unclaimed("文件 `x`\n<!-- path: ai_csv/adv/x/01.csv -->")
assert not is_unclaimed("<!-- tr:: -->")
assert not is_unclaimed("")
assert not is_unclaimed(None)


with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    history = root / "history"
    current = root / "current"
    history.mkdir()
    current.mkdir()
    (history / "adv_dear_hume_001.csv").touch()
    (current / "adv_dear_hume_029.csv").touch()

    plan = collect(["adv_dear_hume"], "", 0, current)
    assert [name for name, _ in plan["adv_dear_hume"]] == [
        "adv_dear_hume_029.csv"
    ]
