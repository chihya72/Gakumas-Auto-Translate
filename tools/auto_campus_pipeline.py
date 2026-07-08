#!/usr/bin/env python
"""
Campus -> AI pretranslate -> workbench.

Find new Campus txt files, pretranslate them, push CSV/raw txt to the work repo,
and create claim issues. Intended for GitHub Actions, but works locally too.
"""
import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gakumas_auto_translate.modules import preprocessor

CAMPUS_REPO = "DreamGallery/Campus-adv-txts"
CAMPUS_DIR = "Resource"
PRETRANS_REPO = "https://github.com/imas-tools/GakumasPreTranslation.git"
WORK_REPO = "chihya72/gakumas-translation-work"
TAG_RE = re.compile(r"</?[A-Za-z][A-Za-z0-9_:-]*(?:\\=[^>]*)?>")
ROOT = Path(__file__).resolve().parents[1]
PRETRANS_DIR = ROOT / "GakumasPreTranslation"
YARN = shutil.which("yarn.cmd") or shutil.which("yarn") or "yarn"


def run(cmd, **kw):
    print("  $", " ".join(map(str, cmd)))
    return subprocess.run(cmd, check=True, text=True, encoding="utf-8", **kw)


def out(cmd):
    return run(cmd, capture_output=True).stdout


def clear_dir(path):
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    for child in p.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def campus_file_list(repo, campus_dir):
    lines = out([
        "gh", "api", f"repos/{repo}/git/trees/main?recursive=1",
        "--jq", ".tree[].path",
    ]).splitlines()
    prefix = campus_dir + "/"
    return [p[len(prefix):] for p in lines
            if p.startswith(prefix) and p.endswith(".txt")]


def flat_txt_from_work_path(path):
    if not path.startswith("data/") or not path.endswith(".csv"):
        return ""
    return "_".join(path[len("data/"):-len(".csv")].split("/")) + ".txt"


def known_files(work_repo, branch):
    known = set()
    for folder in ["data", "csv_data"]:
        p = ROOT / folder
        if not p.exists():
            continue
        suffix = ".txt" if folder == "data" else ".csv"
        for f in p.glob(f"*{suffix}"):
            known.add(f.name.replace(".csv", ".txt"))

    try:
        issues = json.loads(out([
            "gh", "issue", "list", "-R", work_repo, "--state", "all",
            "--limit", "1000", "--json", "title",
        ]) or "[]")
        known.update(i["title"] + ".txt" for i in issues)
    except subprocess.CalledProcessError:
        print(f"!! 无法读取工作仓库 issue，将只按本仓库文件去重: {work_repo}")

    try:
        paths = out([
            "gh", "api", f"repos/{work_repo}/git/trees/{branch}?recursive=1",
            "--jq", ".tree[].path",
        ]).splitlines()
        known.update(filter(None, (flat_txt_from_work_path(p) for p in paths)))
        known.update(p[len("raw/"):] for p in paths
                     if p.startswith("raw/") and p.endswith(".txt"))
    except subprocess.CalledProcessError:
        print(f"!! 无法读取工作仓库文件树，将由 seed 脚本处理仓库存在性: {work_repo}")

    return known


def download_txts(files, repo, campus_dir):
    target = Path("todo/untranslated/txt")
    target.mkdir(parents=True, exist_ok=True)
    for name in files:
        url = f"https://raw.githubusercontent.com/{repo}/main/{campus_dir}/{name}"
        with urllib.request.urlopen(url) as resp:
            data = resp.read()
        (target / name).write_bytes(data)
        print(f"下载: {name}")


def ensure_pretranslation_repo():
    p = PRETRANS_DIR
    if not p.exists():
        run(["git", "clone", "--depth", "1", PRETRANS_REPO, str(p)])
    if not (p / "node_modules").exists():
        run([YARN, "--cwd", str(p), "install", "--frozen-lockfile"])
    patch_pretranslation_prompt()


def patch_pretranslation_prompt():
    p = PRETRANS_DIR / "src/prompts.ts"
    marker = "占位符：GAT_TAG_0、GAT_TAG_1 等必须原样保留"
    text = p.read_text(encoding="utf-8")
    if marker in text:
        return
    text = text.replace(
        "- 特殊符号：<br>代表换行，如果需要，应保留<br>。",
        "- 特殊符号：<br>代表换行，如果需要，应保留<br>。\n"
        "- HTML标签会被替换成 GAT_TAG_0、GAT_TAG_1 等占位符；这些占位符必须原样保留，数量、顺序都不能改变；只翻译占位符之间的可见日文文本。",
    )
    p.write_text(text, encoding="utf-8")


def ensure_pretranslation_env():
    p = PRETRANS_DIR / ".env"
    if p.exists() and "OPENAI_API_KEY" not in os.environ:
        return
    required = ["OPENAI_API_KEY", "OPENAI_BASE_URL", "MODEL"]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        raise SystemExit("缺少环境变量: " + ", ".join(missing))
    lines = [
        f"OPENAI_API_KEY={os.environ['OPENAI_API_KEY']}",
        f"OPENAI_BASE_URL={os.environ['OPENAI_BASE_URL']}",
        f"MODEL={os.environ['MODEL']}",
        f"LOG_LEVEL={os.environ.get('LOG_LEVEL', 'info')}",
        f"MAX_TOKENS={os.environ.get('MAX_TOKENS', '4096')}",
    ]
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")


def prepare_translate_input():
    src = Path("todo/untranslated/csv_dict")
    dst = PRETRANS_DIR / "tmp/untranslated"
    clear_dir(dst)
    clear_dir(PRETRANS_DIR / "tmp/translated")
    mask_csv_tags(src)
    for f in src.glob("*.csv"):
        shutil.copy2(f, dst / f.name)


def mask_csv_tags(folder):
    for path in Path(folder).glob("*.csv"):
        with path.open(encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            fieldnames = reader.fieldnames
        for row in rows:
            row["text"] = mask_tags(row.get("text", ""))
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)


def mask_tags(text):
    i = 0
    def repl(_):
        nonlocal i
        token = f"GAT_TAG_{i}"
        i += 1
        return token
    return TAG_RE.sub(repl, text or "")


def restore_csvs():
    src = PRETRANS_DIR / "tmp/translated"
    out_dir = Path("todo/translated/csv")
    csv_data = ROOT / "csv_data"
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_data.mkdir(exist_ok=True)
    stories = set()

    for translated in sorted(src.glob("*.csv")):
        orig_path = Path("todo/untranslated/csv_orig") / translated.name
        if not orig_path.exists():
            print(f"!! 缺原始 CSV，跳过: {translated.name}")
            continue

        with orig_path.open(encoding="utf-8", newline="") as f:
            orig_rows = list(csv.DictReader(f))
        with translated.open(encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            rows = list(reader)

        translator = None
        if len(rows) > len(orig_rows) and rows[-1].get("id") == "译者":
            translator = rows.pop()
        if len(rows) != len(orig_rows):
            print(f"!! 行数不一致，跳过: {translated.name}")
            continue

        for orig, row in zip(orig_rows, rows):
            if orig.get("id") == row.get("id"):
                row["text"] = orig.get("text", "")
                row["trans"] = unmask_tags(orig.get("text", ""), row.get("trans", ""))
        errors = validate_rows_html_tags(translated.name, rows)
        if errors:
            for e in errors[:10]:
                print("!!", e)
            raise SystemExit(f"{translated.name} HTML标签不一致，停止推送工作台")
        if translator:
            rows.append(translator)

        for dest in [out_dir / translated.name, csv_data / translated.name]:
            with dest.open("w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
        stories.add(translated.stem.rpartition("_")[0] or translated.stem)
        print(f"入 csv_data: {translated.name}")

    return sorted(stories)


def tag_signature(text):
    return TAG_RE.findall(text or "")


def unmask_tags(source_text, translated_text):
    out = translated_text or ""
    for i, tag in enumerate(tag_signature(source_text)):
        out = out.replace(f"GAT_TAG_{i}", tag)
    return out


def validate_rows_html_tags(filename, rows):
    errors = []
    for idx, row in enumerate(rows, start=2):
        row_id = row.get("id", "")
        if row_id in ("info", "译者"):
            continue
        trans = row.get("trans", "")
        if not trans:
            continue
        src_tags = tag_signature(row.get("text", ""))
        trans_tags = tag_signature(trans)
        if src_tags != trans_tags:
            errors.append(
                f"{filename}:{idx} 标签不一致 src={src_tags} trans={trans_tags}"
            )
    return errors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--campus-repo", default=CAMPUS_REPO)
    ap.add_argument("--campus-dir", default=CAMPUS_DIR)
    ap.add_argument("--work-repo", default=WORK_REPO)
    ap.add_argument("--work-branch", default="main")
    ap.add_argument("--prefix", default="adv_")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    remote = campus_file_list(args.campus_repo, args.campus_dir)
    known = known_files(args.work_repo, args.work_branch)
    new = sorted(f for f in remote if f.startswith(args.prefix) and f not in known)
    if args.limit:
        new = new[:args.limit]

    print(f"campus 共 {len(remote)} 个 txt，已知 {len(known)}，新增 {len(new)}")
    for name in new:
        print(" ", name)
    if args.dry_run or not new:
        return

    with tempfile.TemporaryDirectory(prefix="gat-campus-") as tmp:
        old_cwd = Path.cwd()
        os.chdir(tmp)
        try:
            for p in [
                "todo/untranslated/txt",
                "todo/untranslated/csv_orig",
                "todo/untranslated/csv_dict",
                "todo/translated/csv",
            ]:
                clear_dir(p)

            download_txts(new, args.campus_repo, args.campus_dir)
            preprocessor.preprocess_txt_files(preserve_html=True)
            ensure_pretranslation_repo()
            ensure_pretranslation_env()
            prepare_translate_input()
            run([YARN, "--cwd", str(PRETRANS_DIR), "translate:folder"])

            stories = restore_csvs()
            if not stories:
                raise SystemExit("没有生成可播种的 CSV")
            run([
                sys.executable, str(ROOT / "tools/seed_work_repo.py"),
                "--repo", args.work_repo,
                "--stories", *stories,
                "--push", "--issues",
                "--raw-dir", str(Path.cwd() / "todo/untranslated/txt"),
            ], cwd=str(ROOT))
        finally:
            os.chdir(old_cwd)


if __name__ == "__main__":
    main()
