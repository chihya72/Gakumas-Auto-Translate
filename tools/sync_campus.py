#!/usr/bin/env python
"""
从权威源 DreamGallery/Campus-adv-txts 同步新增原始 txt —— 流水线最上游。

对比 campus 仓库 Resource/ 与本地（data/ 已翻备份 + csv_data/ 已机翻 + dump 目录已有），
把新增的 adv txt 下载到 dump_txt 目录。之后走 run.py 菜单1-3（检测/预处理/AI机翻），
再用 seed_work_repo.py 推工作仓库开认领 issue。

用法:
  python tools/sync_campus.py --dry-run        # 只列新增
  python tools/sync_campus.py                  # 下载全部新增
  python tools/sync_campus.py --prefix adv_cidol-amao --limit 10
"""
import argparse
import json
import os
import subprocess
import urllib.request

CAMPUS_REPO = "DreamGallery/Campus-adv-txts"
CAMPUS_DIR = "Resource"


def campus_file_list():
    out = subprocess.run(
        ["gh", "api", f"repos/{CAMPUS_REPO}/git/trees/main?recursive=1",
         "--jq", ".tree[].path"],
        check=True, text=True, capture_output=True, encoding="utf-8").stdout
    prefix = CAMPUS_DIR + "/"
    return [p[len(prefix):] for p in out.splitlines()
            if p.startswith(prefix) and p.endswith(".txt")]


def dump_dir():
    with open("config.json", encoding="utf-8") as f:
        return json.load(f)["dump_txt_path"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--prefix", default="adv_")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    dump = dump_dir()
    known = set()
    known.update(f for f in os.listdir(dump) if f.endswith(".txt"))
    if os.path.isdir("data"):
        known.update(f for f in os.listdir("data") if f.endswith(".txt"))
    if os.path.isdir("csv_data"):
        known.update(f.replace(".csv", ".txt")
                     for f in os.listdir("csv_data") if f.endswith(".csv"))

    remote = campus_file_list()
    new = sorted(f for f in remote
                 if f.startswith(args.prefix) and f not in known)
    if args.limit:
        new = new[:args.limit]

    print(f"campus 共 {len(remote)} 个 txt，本地已知 {len(known)}，新增 {len(new)}")
    for f in new:
        print(" ", f)
    if args.dry_run or not new:
        if not new:
            print("没有新增，流水线是最新的")
        return

    for f in new:
        url = f"https://raw.githubusercontent.com/{CAMPUS_REPO}/main/{CAMPUS_DIR}/{f}"
        with urllib.request.urlopen(url) as resp:
            data = resp.read()
        with open(os.path.join(dump, f), "wb") as out:
            out.write(data)
        print(f"下载: {f}")
    print(f"\n完成，已入 {dump}。接下来: run.py 菜单1-3 机翻，再 seed_work_repo.py 推工作仓库")


if __name__ == "__main__":
    main()
