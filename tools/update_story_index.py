#!/usr/bin/env python
"""从规范仓库 gakuen-adapted-stories 生成剧情分类索引 tools/vendor/story-index.json。

规范分类来自 imas-tools/gakuen-adapted-stories 的 data/adv/ 目录结构：
  cidol-<角色>-3-<话>/NN.csv   好感度（每话 3 段）
  csprt-<批次>-<卡号>/NN.csv   支援卡（每卡 2~3 段）
  pstory/<卡>/<角色>/<文件>     P卡剧情
  pevent/<号>/<角色>/<事件>/NN  P事件
  dear/<角色>/<话>.csv         デア
  live/event/gasha/unit/pgrowth/presult/produce/pstep/pweek/startup/tutorial...

扁平文件名 = "adv_" + data/adv 下相对路径（去 .csv，"/" 换 "_"）。
输出：{ "扁平名": {"c":分类, "g":分组, "ch":角色码, "ep":话数, "card":卡号, "batch":批次} }
"""
import argparse
import json
import re
import subprocess
from collections import Counter
from pathlib import Path

REPO = "imas-tools/gakuen-adapted-stories"
BRANCH = "main"
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tools" / "vendor" / "story-index.json"


def fetch_tree() -> list:
    """优先 gh api（已登录），失败退回匿名 GitHub API。"""
    try:
        out = subprocess.run(
            ["gh", "api", f"repos/{REPO}/git/trees/{BRANCH}?recursive=1",
             "--jq", ".tree[].path"],
            check=True, capture_output=True, text=True, encoding="utf-8",
        ).stdout
        return [l for l in out.splitlines() if l]
    except (subprocess.CalledProcessError, FileNotFoundError):
        import urllib.request

        url = f"https://api.github.com/repos/{REPO}/git/trees/{BRANCH}?recursive=1"
        req = urllib.request.Request(url, headers={"User-Agent": "codex-story-index"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.load(resp)
        return [t["path"] for t in data.get("tree", [])]


def classify(seg: list) -> dict:
    """根据规范路径段生成分类条目（缺省字段省略）。"""
    first = seg[0].removesuffix(".csv")
    if first.startswith("cidol-"):
        m = re.match(r"^cidol-([a-z0-9]+)-(\d+)-(\d+)$", first)
        if m:
            return {"c": "cidol", "g": first, "ch": m.group(1), "ep": int(m.group(3))}
    if first.startswith("csprt-"):
        m = re.match(r"^csprt-(\d+)-(\d+)$", first)
        if m:
            return {"c": "csprt", "g": first, "card": f"{m.group(1)}-{m.group(2)}", "batch": m.group(1)}
        return {"c": first, "g": first}
    if first == "pstory" and len(seg) >= 3:
        return {"c": "pstory", "g": "/".join(seg[:3]), "ch": seg[2], "card": seg[1]}
    if first == "pevent" and len(seg) >= 4:
        return {"c": "pevent", "g": "/".join(seg[:4]), "ch": seg[2], "card": f"{seg[1]}-{seg[3]}"}
    if first == "dear" and len(seg) >= 3:
        file_base = seg[2].rsplit(".", 1)[0]
        ep = int(re.match(r"^(\d+)", file_base).group(1))
        return {"c": "dear", "g": f"dear/{seg[1]}/{ep:03d}", "ch": seg[1], "ep": ep}
    if first == "live" and len(seg) >= 3:
        return {"c": "live", "g": "/".join(seg[:3]), "ch": seg[1]}
    if first == "event" and len(seg) >= 2:
        return {"c": "event", "g": "/".join(seg[:2])}
    if first == "gasha" and len(seg) >= 2:
        return {"c": "gasha", "g": "/".join(seg[:2])}
    if first == "unit" and len(seg) >= 2:
        return {"c": "unit", "g": "/".join(seg[:2])}
    if first == "pgrowth" and len(seg) >= 3:
        return {"c": "pgrowth", "g": "/".join(seg[:3]), "ch": seg[2]}
    if first == "presult" and len(seg) >= 2:
        return {"c": "presult", "g": "/".join(seg[:2])}
    if len(seg) >= 2:
        return {"c": first, "g": "/".join(seg[:2])}
    return {"c": first, "g": first}


def build_index(tree: list) -> dict:
    index = {}
    for p in tree:
        if not (p.startswith("data/adv/") and p.endswith(".csv")):
            continue
        rel = p[len("data/adv/"):]
        flat = "adv_" + rel[:-4].replace("/", "_")
        index[flat] = classify(rel.split("/"))
    return index


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tree-file", help="本地规范树清单（跳过网络请求）")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    tree = [l.strip() for l in Path(args.tree_file).read_text(encoding="utf-8").splitlines() if l.strip()] if args.tree_file else fetch_tree()
    index = build_index(tree)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(index, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"生成 {len(index)} 条分类索引 -> {out} ({out.stat().st_size} bytes)")

    # 本地 csv_data 覆盖率校验
    local = ROOT / "csv_data"
    if local.exists():
        local_files = [f.stem for f in local.glob("*.csv")]
        missing = [f for f in local_files if f not in index]
        print(f"本地 csv_data 共 {len(local_files)} 个文件，未覆盖 {len(missing)} 个")
        for f in missing[:10]:
            print("  未覆盖:", f)
        cats = Counter(index[f]["c"] for f in local_files if f in index)
        print("本地文件分类统计:", dict(cats.most_common()))


if __name__ == "__main__":
    main()
