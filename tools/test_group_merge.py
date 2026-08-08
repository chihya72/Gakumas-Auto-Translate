"""合并/拆分往返自检：合并翻译的结果必须能原样拆回各段。

行数错位是这条路径最危险的失败——拆错了整篇译文会串行，而且串得很隐蔽。
"""
import csv
import tempfile
from pathlib import Path

import sys
from pathlib import Path as _P
sys.path.insert(0, str(_P(__file__).resolve().parents[1]))
from gakumas_auto_translate.modules.utils import merge_groups, split_merged

FIELDS = ["id", "name", "text", "trans"]


def write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def row(i, text):
    return {"id": str(i), "name": "咲季", "text": text, "trans": ""}


with tempfile.TemporaryDirectory() as tmp:
    src, dst = Path(tmp) / "src", Path(tmp) / "dst"
    src.mkdir()
    dst.mkdir()

    # cidol 三段（行数各不相同，能暴露按固定长度切分的错误）+ 一个不合并的 dear。
    # 每个文件末尾都有 info 行——真实 CSV 就长这样，而引擎取【最后】一个 info
    # 当输出文件名，合并时多带一个 info 就会写错文件。
    parts = {"adv_cidol-atbm-3-018_01.csv": 3,
             "adv_cidol-atbm-3-018_02.csv": 5,
             "adv_cidol-atbm-3-018_03.csv": 2}
    for name, n in parts.items():
        body = [row(i, f"{name}#{i}") for i in range(n)]
        body.append({"id": "info", "name": name[:-4] + ".txt", "text": "", "trans": ""})
        write_csv(src / name, body)
    write_csv(src / "adv_dear_atbm_021.csv", [
        row(0, "dear#0"),
        {"id": "info", "name": "adv_dear_atbm_021.txt", "text": "", "trans": ""},
    ])

    manifest = merge_groups(sorted(src.glob("*.csv")), dst)

    # cidol 三段合并成一个文件，dear 原样单独一个。layout 只数台词行，不含 info
    assert set(manifest) == {"adv_cidol-atbm-3-018_01.csv"}, manifest
    assert manifest["adv_cidol-atbm-3-018_01.csv"] == [
        ("adv_cidol-atbm-3-018_01.csv", 3),
        ("adv_cidol-atbm-3-018_02.csv", 5),
        ("adv_cidol-atbm-3-018_03.csv", 2),
    ]
    assert (dst / "adv_dear_atbm_021.csv").exists()
    merged_rows = read_csv(dst / "adv_cidol-atbm-3-018_01.csv")
    infos = [r for r in merged_rows if r["id"] == "info"]
    assert len(infos) == 1, f"合并后应只剩一个 info，实际 {len(infos)}"
    assert infos[0]["name"] == "adv_cidol-atbm-3-018_01.txt", infos[0]
    assert len(merged_rows) == 10 + 1

    # 模拟引擎：填 trans，末尾追加自己的 info + 译者行
    merged = [r for r in merged_rows if r["id"] != "info"]
    for r in merged:
        r["trans"] = "译:" + r["text"]
    merged.append({"id": "info", "name": "adv_cidol-atbm-3-018_01.txt", "text": "", "trans": ""})
    merged.append({"id": "译者", "name": "test-model", "text": "", "trans": ""})
    write_csv(dst / "adv_cidol-atbm-3-018_01.csv", merged)

    out = Path(tmp) / "out"
    out.mkdir()
    written = split_merged(dst / "adv_cidol-atbm-3-018_01.csv",
                           manifest["adv_cidol-atbm-3-018_01.csv"], out)
    assert len(written) == 3, written

    for name, n in parts.items():
        got = read_csv(out / name)
        assert got[-1]["id"] == "译者", f"{name} 缺译者行"
        # 每段必须补回【它自己的】info，而不是共用第一段的
        assert got[-2]["id"] == "info", f"{name} 缺 info 行"
        assert got[-2]["name"] == name[:-4] + ".txt", got[-2]
        body = got[:-2]
        assert len(body) == n, f"{name} 行数 {len(body)} != {n}"
        # 每段拿回的必须是自己那几行，不能串到别段
        assert [r["text"] for r in body] == [f"{name}#{i}" for i in range(n)]
        assert all(r["trans"] == "译:" + r["text"] for r in body)

    # 行数对不上时必须拒绝拆分，而不是错位写出
    bad = [r for r in read_csv(dst / "adv_cidol-atbm-3-018_01.csv") if r["id"] == "0"]
    write_csv(dst / "bad.csv", bad)
    assert split_merged(dst / "bad.csv",
                        manifest["adv_cidol-atbm-3-018_01.csv"], out) == []

print("OK: 合并/拆分往返一致，行数不符时正确拒绝")
