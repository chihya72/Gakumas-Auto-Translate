#!/usr/bin/env python
"""
把指定剧情推进【工作仓库】并开认领 Issue —— 在线协作工作流的播种/入库脚本。

工作仓库(默认 chihya72/gakumas-translation-work)存放成员在线翻译/校对的 CSV，
认领台账用其 GitHub Issues：每篇剧情一个 Issue，标签=工序阶段，assignee=认领人。

用法:
  # 干跑，只打印计划(默认)
  python tools/seed_work_repo.py --stories adv_cidol-amao-3-000 adv_cidol-amao-3-001
  # 真正执行(建仓/推文件/开Issue)。缺仓库时加 --create-repo
  python tools/seed_work_repo.py --stories adv_cidol-amao-3-000 --push --issues [--create-repo]
  # 按前缀选一批(如某偶像)，配合 --limit 控数量
  python tools/seed_work_repo.py --prefix adv_cidol-amao --limit 3 --push --issues

依赖: git、gh(已登录) 命令行；无第三方 Python 包。
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile

CSV_SRC = "csv_data"
DEFAULT_REPO = "chihya72/gakumas-translation-work"
STAGE_LABELS = ["待翻译", "翻译中", "待校对", "校对中", "完成"]
INIT_STAGE = "待翻译"


def run(cmd, **kw):
    print("  $", " ".join(cmd))
    return subprocess.run(cmd, check=True, text=True, capture_output=True, **kw)


def story_of(filename):
    # adv_cidol-amao-3-000_01.csv -> (story='adv_cidol-amao-3-000', part='01')
    base = filename[:-4] if filename.endswith(".csv") else filename
    story, _, part = base.rpartition("_")
    return story, part


def repo_path_of(filename):
    # adv_cidol-amao-3-000_01.csv -> ai_csv/adv/cidol-amao-3-000/01.csv
    base = filename[:-4]
    return "ai_csv/" + "/".join(base.split("_")) + ".csv"


def stage_path(rpath, stage):
    return stage + "/" + "/".join(rpath.split("/")[1:])


def collect(stories, prefix, limit):
    """返回 {story: [(filename, repo_path), ...]}"""
    files = sorted(f for f in os.listdir(CSV_SRC) if f.endswith(".csv"))
    result = {}
    for f in files:
        story, _ = story_of(f)
        if stories and story not in stories:
            continue
        if prefix and not story.startswith(prefix):
            continue
        result.setdefault(story, []).append((f, repo_path_of(f)))
    if limit:
        result = dict(list(result.items())[:limit])
    return result


def existing_issue_titles(repo):
    out = run(["gh", "issue", "list", "-R", repo, "--state", "all",
               "--limit", "1000", "--json", "title"]).stdout
    return {i["title"] for i in json.loads(out or "[]")}


def ensure_repo(repo, create):
    try:
        run(["gh", "repo", "view", repo])
        return True
    except subprocess.CalledProcessError:
        if not create:
            print(f"!! 工作仓库 {repo} 不存在，加 --create-repo 创建")
            return False
        run(["gh", "repo", "create", repo, "--public",
             "--description", "学马仕汉化在线协作工作仓库"])
        return True


def ensure_labels(repo):
    for name in STAGE_LABELS:
        try:
            run(["gh", "label", "create", name, "-R", repo, "--force"])
        except subprocess.CalledProcessError as e:
            print("   (label)", e.stderr.strip())


def push_files(repo, plan, raw_dir=""):
    with tempfile.TemporaryDirectory() as tmp:
        run(["gh", "repo", "clone", repo, tmp, "--", "--depth", "1"])
        # 拷文件到工作树
        for story, parts in plan.items():
            for filename, rpath in parts:
                dst = os.path.join(tmp, rpath)
                # 已在仓库的 CSV 不覆盖——里面可能有成员的在线编辑
                if os.path.exists(dst):
                    print(f"   skip csv (exists): {rpath}")
                else:
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    with open(os.path.join(CSV_SRC, filename), "rb") as s, open(dst, "wb") as d:
                        d.write(s.read())
                if raw_dir:
                    raw_name = filename.replace(".csv", ".txt")
                    raw_src = os.path.join(raw_dir, raw_name)
                    raw_dst = os.path.join(tmp, "raw_txt", raw_name)
                    if os.path.exists(raw_src) and not os.path.exists(raw_dst):
                        os.makedirs(os.path.dirname(raw_dst), exist_ok=True)
                        with open(raw_src, "rb") as s, open(raw_dst, "wb") as d:
                            d.write(s.read())
        # 重建 index.json: 原始txt名 -> 相对csv路径
        index = {}
        data_root = os.path.join(tmp, "ai_csv")
        for sub, _, files in os.walk(data_root):
            for f in files:
                if f.endswith(".csv"):
                    rel = os.path.relpath(os.path.join(sub, f), tmp).replace("\\", "/")
                    # ai_csv/adv/cidol-amao-3-000/01.csv -> adv_cidol-amao-3-000_01.txt
                    origin = "_".join(rel[len("ai_csv/"):-len(".csv")].split("/")) + ".txt"
                    index[origin] = "./" + rel
        with open(os.path.join(tmp, "index.json"), "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=2)
        # 空仓库首推：强制切到 main 分支并设 upstream
        run(["git", "-C", tmp, "switch", "-C", "main"])
        run(["git", "-C", tmp, "config", "user.name", "github-actions[bot]"])
        run(["git", "-C", tmp, "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"])
        run(["git", "-C", tmp, "add", "-A"])
        # 无改动时 commit 会失败，容忍
        try:
            run(["git", "-C", tmp, "commit", "-m", f"seed {len(plan)} stories"])
            run(["git", "-C", tmp, "push", "-u", "origin", "main"])
        except subprocess.CalledProcessError as e:
            msg = (e.stderr or e.stdout or "").strip()
            if "nothing to commit" in msg or "no changes added" in msg:
                print("   (push)", msg)
            else:
                raise


def make_issues(repo, plan):
    # 每个文件(话)一个 issue，标题即文件名 adv_..._NN
    existing = existing_issue_titles(repo)
    for story, parts in plan.items():
        for filename, rpath in parts:
            title = filename[:-4] if filename.endswith(".csv") else filename
            if title in existing:
                print(f"   skip issue (exists): {title}")
                continue
            # 双轨认领标记：翻译(tr)/校对(pr)，初始都待认领
            body = (
                f"文件 `{title}`\n\n"
                f"<!-- path: {rpath} -->\n"
                f"<!-- raw_path: raw_txt/{title}.txt -->\n"
                f"<!-- ai_path: {rpath} -->\n"
                f"<!-- translated_path: {stage_path(rpath, 'translated_csv')} -->\n"
                f"<!-- proofread_path: {stage_path(rpath, 'proofread_csv')} -->\n"
                f"<!-- tr:: -->\n<!-- pr:: -->"
            )
            run(["gh", "issue", "create", "-R", repo, "--title", title,
                 "--body", body, "--label", INIT_STAGE])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=DEFAULT_REPO)
    ap.add_argument("--stories", nargs="*", default=[])
    ap.add_argument("--prefix", default="")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--create-repo", action="store_true")
    ap.add_argument("--push", action="store_true", help="推送文件到工作仓库")
    ap.add_argument("--issues", action="store_true", help="创建认领 Issue")
    ap.add_argument("--raw-dir", default="", help="同时上传原始 txt 到工作仓库 raw/")
    args = ap.parse_args()

    if not args.stories and not args.prefix:
        ap.error("需指定 --stories 或 --prefix")

    plan = collect(args.stories, args.prefix, args.limit)
    if not plan:
        print("没有匹配的剧情"); sys.exit(1)

    print(f"计划入库 {len(plan)} 篇剧情 -> {args.repo}:")
    for story, parts in plan.items():
        print(f"  {story}  ({len(parts)} 话)  -> {parts[0][1]} ...")

    if not (args.push or args.issues):
        print("\n[干跑] 加 --push 推文件、--issues 开Issue 才会实际执行")
        return

    if not ensure_repo(args.repo, args.create_repo):
        sys.exit(1)
    if args.push:
        push_files(args.repo, plan, args.raw_dir)
    if args.issues:
        ensure_labels(args.repo)
        make_issues(args.repo, plan)
    print("完成。")


if __name__ == "__main__":
    main()
