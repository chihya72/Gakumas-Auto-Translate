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
from gakumas_auto_translate.modules.utils import merge_groups, split_merged

CAMPUS_REPO = "DreamGallery/Campus-adv-txts"
CAMPUS_DIR = "Resource"
PRETRANS_REPO = "https://github.com/imas-tools/GakumasPreTranslation.git"
WORK_REPO = "chihya72/gakumas-translation-work"
TAG_RE = re.compile(r"</?[A-Za-z][A-Za-z0-9_:-]*(?:\\=[^>]*)?>")
# 模型把注入的上下文块当成译文回显出来的特征；出现即判失败
ECHO_MARKERS = ("REF|", "TERM|", "角色卡", "剧情摘要", "术语表")
# 有台词的行特征；全无 = 空剧本（纯演出脚本），与本地菜单2的过滤同构，下载时直接跳过
TEXT_LINE_RE = re.compile(r"(?:message|narration|choice) text=|title title=")
ROOT = Path(__file__).resolve().parents[1]
VENDOR_SRC = ROOT / "tools/vendor"
PRETRANS_DIR = ROOT / "GakumasPreTranslation"
YARN = shutil.which("yarn.cmd") or shutil.which("yarn") or "yarn"
DEFAULT_MAX_TOKENS = 12288
DEEPSEEK_V4_PRO_MIN_MAX_TOKENS = 65536


def run(cmd, **kw):
    print("  $", " ".join(map(str, cmd)))
    return subprocess.run(cmd, check=True, text=True, encoding="utf-8", **kw)


def out(cmd):
    return run(cmd, capture_output=True).stdout


def required_max_tokens(model):
    """返回当前模型在本管线中的安全输出预算下限。"""
    if "deepseek-v4-pro" in (model or "").lower():
        return DEEPSEEK_V4_PRO_MIN_MAX_TOKENS
    return DEFAULT_MAX_TOKENS


def validated_max_tokens():
    """在任何付费请求前验证 MAX_TOKENS，避免旧 Secret 静默覆盖代码默认值。"""
    model = os.environ.get("MODEL", "")
    minimum = required_max_tokens(model)
    raw = os.environ.get("MAX_TOKENS", str(minimum)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise SystemExit(f"MAX_TOKENS 必须是正整数，当前值: {raw!r}") from exc
    if value < minimum:
        reason = (
            "DeepSeek V4 Pro thinking 的推理与最终译文共用输出预算"
            if minimum == DEEPSEEK_V4_PRO_MIN_MAX_TOKENS
            else "同组合并请求需要容纳完整译文"
        )
        raise SystemExit(
            f"MAX_TOKENS={value} 过小；{reason}，本管线要求至少 {minimum}。"
            "请修改 GitHub Actions Secret MAX_TOKENS 后手动重跑。"
        )
    return str(value)


def guard_repeated_scheduled_failure():
    """当前分支上次运行失败时暂停新的自动首跑，防止同一批剧情逐小时重复扣费。

    workflow_dispatch 和手动 Re-run（GITHUB_RUN_ATTEMPT > 1）都明确表示人工恢复，
    因而绕过此闸门；它们成功后也会成为当前分支最新完成的运行，解除暂停。
    """
    if os.environ.get("GITHUB_EVENT_NAME") != "schedule":
        return
    try:
        attempt = int(os.environ.get("GITHUB_RUN_ATTEMPT", "1"))
    except ValueError:
        attempt = 1
    if attempt > 1:
        return
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not repo:
        raise SystemExit("定时防重闸门缺少 GITHUB_REPOSITORY，已在付费请求前停止")
    branch = os.environ.get("GITHUB_REF_NAME", "master")
    endpoint = (
        f"repos/{repo}/actions/workflows/campus-to-work.yml/runs"
        f"?branch={branch}&status=completed&per_page=1"
    )
    payload = json.loads(out(["gh", "api", endpoint]))
    runs = payload.get("workflow_runs", [])
    if runs and runs[0].get("conclusion") == "failure":
        previous = runs[0]
        raise SystemExit(
            "当前分支上一次翻译运行失败，已阻止本轮再次调用模型，避免同一批剧情重复扣费。"
            f"上次运行: {previous.get('html_url', previous.get('id', 'unknown'))}。"
            "修好配置后请手动 Re-run failed jobs，或用 workflow_dispatch 运行。"
        )


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
    if not path.endswith(".csv"):
        return ""
    for prefix in ("ai_csv/", "data/"):
        if path.startswith(prefix):
            return "_".join(path[len(prefix):-len(".csv")].split("/")) + ".txt"
    return ""


def known_files(work_repo, branch):
    known = set()
    for folder in ["data", "csv_data"]:
        p = ROOT / folder
        if not p.exists():
            continue
        suffix = ".txt" if folder == "data" else ".csv"
        for f in p.glob(f"*{suffix}"):
            known.add(f.name.replace(".csv", ".txt"))

    # 工作仓不存在 = 还没播种过，known 保持只有本仓库文件；由 seed 负责建仓。
    # 但仓库存在时，下面两个查询失败必须致命——降级会让管线以为"什么都没翻过"，
    # 把 3000+ 剧本重翻一遍烧 API。
    try:
        out(["gh", "api", f"repos/{work_repo}", "--jq", ".name"])
    except subprocess.CalledProcessError:
        print(f"工作仓库尚不存在，跳过远端去重: {work_repo}")
        return known

    issues = json.loads(out([
        "gh", "issue", "list", "-R", work_repo, "--state", "all",
        "--limit", "1000", "--json", "title",
    ]) or "[]")
    known.update(i["title"] + ".txt" for i in issues)

    paths = out([
        "gh", "api", f"repos/{work_repo}/git/trees/{branch}?recursive=1",
        "--jq", ".tree[].path",
    ]).splitlines()
    known.update(filter(None, (flat_txt_from_work_path(p) for p in paths)))
    for raw_prefix in ("raw_txt/", "raw/"):
        known.update(p[len(raw_prefix):] for p in paths
                     if p.startswith(raw_prefix) and p.endswith(".txt"))

    return known


def download_txts(files, repo, campus_dir):
    """下载并过滤空剧本（无台词的纯演出脚本），与本地菜单2的空文件过滤同构。
    返回有台词的文件列表。空文件每轮会重新检查一遍（几KB开销，无状态残留）。"""
    target = Path("todo/untranslated/txt")
    target.mkdir(parents=True, exist_ok=True)
    kept = []
    for name in files:
        url = f"https://raw.githubusercontent.com/{repo}/main/{campus_dir}/{name}"
        with urllib.request.urlopen(url) as resp:
            data = resp.read()
        if not TEXT_LINE_RE.search(data.decode("utf-8", errors="replace")):
            print(f"跳过(无台词): {name}")
            continue
        (target / name).write_bytes(data)
        kept.append(name)
        print(f"下载: {name}")
    return kept


def ensure_pretranslation_repo():
    p = PRETRANS_DIR
    if not p.exists():
        run(["git", "clone", "--depth", "1", PRETRANS_REPO, str(p)])
    if not (p / "node_modules").exists():
        run([YARN, "--cwd", str(p), "install", "--frozen-lockfile"])
    overlay_vendor_files()


def overlay_vendor_files():
    """用本仓库 tools/vendor 下的翻译引擎文件覆盖 GakumasPreTranslation，
    使新克隆/CI 环境也具备翻译记忆（TM）能力。"""
    # dear-summaries.json 不覆盖：它是可写状态，由引擎按 DEAR_SUMMARY_FILE
    # 直接读写本仓库那一份，覆盖到临时 clone 里翻完就丢了
    for name in ("tm.ts", "translate.ts", "prompts.ts", "story-index.json",
                 "character-cards.json", "glossary.json"):
        src = VENDOR_SRC / name
        dst = PRETRANS_DIR / "src" / name
        if not src.exists():
            print(f"!! 缺少 vendor 文件: {src}")
            continue
        shutil.copy2(src, dst)
        print(f"已覆盖翻译引擎文件: {name}")
    # 上游脚本会 catch 单文件失败后继续翻剩余文件；配置错误时会把同一错误付费放大。
    # 覆盖为 fail-fast 版本，第一份失败即让整个进程非零退出。
    script_src = VENDOR_SRC / "translate-folder.ts"
    script_dst = PRETRANS_DIR / "scripts" / "translate.ts"
    if not script_src.exists():
        raise SystemExit(f"缺少 vendor 文件: {script_src}")
    shutil.copy2(script_src, script_dst)
    print("已覆盖翻译入口脚本: translate-folder.ts")


def ensure_pretranslation_env():
    p = PRETRANS_DIR / ".env"
    if p.exists() and "OPENAI_API_KEY" not in os.environ:
        return
    required = ["OPENAI_API_KEY", "OPENAI_BASE_URL", "MODEL"]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        raise SystemExit("缺少环境变量: " + ", ".join(missing))
    max_tokens = validated_max_tokens()
    print(f"翻译配置自检通过: MAX_TOKENS={max_tokens}")
    lines = [
        f"OPENAI_API_KEY={os.environ['OPENAI_API_KEY']}",
        f"OPENAI_BASE_URL={os.environ['OPENAI_BASE_URL']}",
        f"MODEL={os.environ['MODEL']}",
        f"LOG_LEVEL={os.environ.get('LOG_LEVEL', 'info')}",
        f"MAX_TOKENS={max_tokens}",
    ]
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")


def prepare_translate_input():
    src = Path("todo/untranslated/csv_dict")
    dst = PRETRANS_DIR / "tmp/untranslated"
    clear_dir(dst)
    clear_dir(PRETRANS_DIR / "tmp/translated")
    mask_csv_tags(src)
    return merge_groups(sorted(src.glob("*.csv")), dst)


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


def restore_csvs(manifest=None):
    src = PRETRANS_DIR / "tmp/translated"
    out_dir = Path("todo/translated/csv")
    out_dir.mkdir(parents=True, exist_ok=True)
    stories = set()

    # 合并翻译的先按行数拆回各段（就地拆在 src 里），之后逐段处理逻辑不变
    for name, layout in (manifest or {}).items():
        merged = src / name
        if merged.exists():
            split_merged(merged, layout, src)

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

        # 只写临时目录交给 seed 推工作仓；csv_data 是实装译文目录，机翻不回写
        dest = out_dir / translated.name
        with dest.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        stories.add(translated.stem.rpartition("_")[0] or translated.stem)
        print(f"待推送工作仓: {translated.name}")

    return sorted(stories)


def tag_signature(text):
    return TAG_RE.findall(text or "")


def unmask_tags(source_text, translated_text):
    out = translated_text or ""
    # 倒序替换：先换 GAT_TAG_10 再换 GAT_TAG_1，避免前缀误命中
    tags = tag_signature(source_text)
    for i in range(len(tags) - 1, -1, -1):
        out = out.replace(f"GAT_TAG_{i}", tags[i])
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
        echoed = next((m for m in ECHO_MARKERS if m in trans), None)
        if echoed:
            errors.append(f"{filename}:{idx} 回显了上下文块（含 {echoed!r}）: {trans[:60]}")
    return errors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--campus-repo", default=CAMPUS_REPO)
    ap.add_argument("--campus-dir", default=CAMPUS_DIR)
    ap.add_argument("--work-repo", default=WORK_REPO)
    ap.add_argument("--work-branch", default="main")
    ap.add_argument(
        "--prefix", default="adv_",
        help="逗号分隔的前缀白名单，命中任一即处理（如 adv_cidol,adv_csprt）")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    guard_repeated_scheduled_failure()

    remote = campus_file_list(args.campus_repo, args.campus_dir)
    known = known_files(args.work_repo, args.work_branch)
    prefixes = tuple(p.strip() for p in args.prefix.split(",") if p.strip())
    new = sorted(f for f in remote if f.startswith(prefixes) and f not in known)
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

            kept = download_txts(new, args.campus_repo, args.campus_dir)
            if not kept:
                print("新增全部为空剧本，无需机翻")
                return
            preprocessor.preprocess_txt_files(preserve_html=True)
            ensure_pretranslation_repo()
            ensure_pretranslation_env()
            manifest = prepare_translate_input()
            max_tokens = validated_max_tokens()
            translation_error = None
            try:
                run([YARN, "--cwd", str(PRETRANS_DIR), "translate:folder"], env={
                    **os.environ,
                    # 翻译记忆只读 csv_data（人工实装译文），机翻不回写，不自我污染
                    "TM_DIR": str(ROOT / "csv_data"),
                    "DEAR_SUMMARY_FILE": str(VENDOR_SRC / "dear-summaries.json"),
                    # 合并后的同组 CSV 必须放得进一次请求，否则又被切开等于白合并
                    "MAX_LINES_PER_REQUEST": os.environ.get("MAX_LINES_PER_REQUEST", "250"),
                    "MAX_TOKENS": max_tokens,
                })
            except subprocess.CalledProcessError as exc:
                # fail-fast 会留下此前已经完整写出的 CSV。先把这些成果播种，
                # 再让本轮失败；否则人工恢复时还会为已成功文件重复付费。
                translation_error = exc
                print("!! 翻译引擎已停止；正在保存失败前已完成的译文")

            stories = restore_csvs(manifest)
            if not stories:
                if translation_error:
                    raise SystemExit("翻译在首个文件失败，没有生成可播种的 CSV") from translation_error
                raise SystemExit("没有生成可播种的 CSV")
            run([
                sys.executable, str(ROOT / "tools/seed_work_repo.py"),
                "--repo", args.work_repo,
                "--stories", *stories,
                "--csv-src", str(Path.cwd() / "todo/translated/csv"),
                "--push", "--issues",
                "--raw-dir", str(Path.cwd() / "todo/untranslated/txt"),
            ], cwd=str(ROOT))
            if translation_error:
                raise SystemExit(
                    f"翻译中途失败；已先保存 {len(stories)} 个完成剧情组，"
                    "剩余文件需人工恢复后再翻"
                ) from translation_error
        finally:
            os.chdir(old_cwd)


if __name__ == "__main__":
    main()
