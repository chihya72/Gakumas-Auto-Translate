#!/usr/bin/env python
"""
收割工作仓库的完成稿 —— 在线协作流水线的回收端。

两轨(翻译+校对)都完成的文件其 issue 会被自动关闭。本脚本：
  1. 列出工作仓库已关闭且未标"已入库"的 issue
  2. 从 raw.githubusercontent 下载对应 CSV 到 ./todo/translated/csv/<扁平名>.csv
  3. 给 issue 打"已入库"标签（防重复收割）

之后走 run.py 菜单 4（合并生成 纯中文/中日双语 txt）→ 菜单 5（归档清理）即可。

用法:
  python tools/harvest_work_repo.py            # 收割全部待入库
  python tools/harvest_work_repo.py --dry-run  # 只看不动
"""
import argparse
import json
import os
import re
import subprocess
import urllib.request

REPO = "chihya72/gakumas-translation-work"
BRANCH = "main"
DEST = "./todo/translated/csv"
DONE_LABEL = "已入库"
PATH_RE = re.compile(r"<!--\s*path:\s*(.+?)\s*-->")


def gh(args):
    r = subprocess.run(["gh"] + args, check=True, text=True,
                       capture_output=True, encoding="utf-8")
    return r.stdout


def flat_name(repo_path):
    # data/adv/cidol-amao-3-000/01.csv -> adv_cidol-amao-3-000_01.csv
    parts = repo_path[len("data/"):-len(".csv")].split("/")
    return "_".join(parts) + ".csv"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    issues = json.loads(gh(["issue", "list", "-R", REPO, "--state", "closed",
                            "--limit", "200", "--json", "number,title,body,labels"]))
    todo = [i for i in issues
            if DONE_LABEL not in [l["name"] for l in i["labels"]]]
    if not todo:
        print("没有待入库的完成稿")
        return

    os.makedirs(DEST, exist_ok=True)
    # 确保标签存在（幂等）
    if not args.dry_run:
        subprocess.run(["gh", "label", "create", DONE_LABEL, "-R", REPO,
                        "--force"], capture_output=True)

    for i in todo:
        m = PATH_RE.search(i["body"] or "")
        if not m:
            print(f"!! #{i['number']} {i['title']} 缺 path 标记，跳过")
            continue
        rpath = m.group(1)
        fname = flat_name(rpath)
        url = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/{rpath}"
        print(f"#{i['number']} {i['title']} -> {DEST}/{fname}")
        if args.dry_run:
            continue
        with urllib.request.urlopen(url) as resp:
            data = resp.read()
        with open(os.path.join(DEST, fname), "wb") as f:
            f.write(data)
        gh(["issue", "edit", str(i["number"]), "-R", REPO,
            "--add-label", DONE_LABEL])

    print("完成。接下来: run.py 菜单4 合并生成 纯中文/双语 txt，菜单5 归档")


if __name__ == "__main__":
    main()
