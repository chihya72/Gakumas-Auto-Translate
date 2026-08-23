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
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gakumas_auto_translate.modules import preprocessor
from gakumas_auto_translate.modules.utils import merge_groups, split_merged
from gakumas_auto_translate.modules.vendor_sync import sync_vendor_files

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
# 校验不过的文件最多重翻几轮
RETRY_ROUNDS = 3
# 网络瞬时故障的重试次数与首次退避秒数
NET_RETRIES = 3
NET_BACKOFF = 5


def run(cmd, **kw):
    print("  $", " ".join(map(str, cmd)))
    return subprocess.run(cmd, check=True, text=True, encoding="utf-8", **kw)


def retry(action, what):
    """瞬时故障（连接重置、限流、服务端 5xx）重试，最后一次仍失败才抛。

    不加重试的后果已经吃过一次：一次 TCP reset 就能把整轮搞挂。
    只包只读请求（下载、gh api 查询），写操作不重试以免重复产生副作用。
    """
    delay = NET_BACKOFF
    for attempt in range(1, NET_RETRIES + 1):
        try:
            return action()
        except (OSError, subprocess.CalledProcessError) as error:
            if attempt == NET_RETRIES:
                raise
            print(f"!! {what} 失败（第 {attempt}/{NET_RETRIES} 次）: {error}；{delay}s 后重试")
            time.sleep(delay)
            delay *= 2


def out(cmd):
    return retry(lambda: run(cmd, capture_output=True), " ".join(map(str, cmd[:3]))).stdout


def configured_max_tokens():
    """取值而已。校验由引擎的 validateMaxTokens 做——它就在 HTTP 请求前一行，
    是离付费最近的位置，而且阈值只需要存一份。"""
    return os.environ.get("MAX_TOKENS", "").strip() or str(DEFAULT_MAX_TOKENS)


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

        def fetch():
            with urllib.request.urlopen(url) as resp:
                return resp.read()

        data = retry(fetch, f"下载 {name}")
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
    sync_vendor_files(ROOT, PRETRANS_DIR)
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
    max_tokens = configured_max_tokens()
    print(f"写入引擎配置: MAX_TOKENS={max_tokens}")
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


def group_members(name, manifest):
    """返回该文件所属合并组的全部分段；不属于任何组则只有它自己。

    同组是一次请求翻出来的，只补其中一段会错位，所以重翻必须整组重翻。
    """
    for parts in (manifest or {}).values():
        names = [part for part, _ in parts]
        if name in names:
            return names
    return [name]


def restore_csvs(manifest=None, done=None):
    """还原原文与标签、写出合格的 CSV，返回 {文件名: 失败原因}。

    单个文件不合格不再中断整批——那会把同批已经付过钱的几十个文件
    一起丢掉。调用方负责重试，重试不过再标记。
    """
    src = PRETRANS_DIR / "tmp/translated"
    out_dir = Path("todo/translated/csv")
    out_dir.mkdir(parents=True, exist_ok=True)
    done = done if done is not None else set()
    failures = {}

    # 合并翻译的先按行数拆回各段（就地拆在 src 里），之后逐段处理逻辑不变。
    # 拆完后合并文件会被第一段覆盖，所以已完成的组不能再拆一次。
    for name, layout in (manifest or {}).items():
        merged = src / name
        if merged.exists() and not any(part in done for part, _ in layout):
            split_merged(merged, layout, src)

    for translated in sorted(src.glob("*.csv")):
        if translated.name in done:
            continue
        orig_path = Path("todo/untranslated/csv_orig") / translated.name
        if not orig_path.exists():
            print(f"!! 缺原始 CSV，跳过: {translated.name}")
            failures[translated.name] = "缺少对应的原始 CSV"
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
            failures[translated.name] = (
                f"行数不一致（原文 {len(orig_rows)} 行，译文 {len(rows)} 行）"
            )
            continue

        for orig, row in zip(orig_rows, rows):
            if orig.get("id") == row.get("id"):
                row["text"] = orig.get("text", "")
                row["trans"] = unmask_tags(orig.get("text", ""), row.get("trans", ""))
        errors = validate_rows_html_tags(translated.name, rows)
        if errors:
            for e in errors[:10]:
                print("!!", e)
            failures[translated.name] = errors[0]
            continue
        if translator:
            rows.append(translator)

        # 只写临时目录交给 seed 推工作仓；csv_data 是实装译文目录，机翻不回写
        dest = out_dir / translated.name
        with dest.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        done.add(translated.name)
        print(f"待推送工作仓: {translated.name}")

    return failures


def requeue_failures(failures, manifest, done):
    """把失败文件（及其所在合并组）的输出删掉，下一轮就会重翻它们。

    翻译入口默认跳过已存在的输出，所以只需删掉要重翻的，合格的不会再花钱。
    """
    src = PRETRANS_DIR / "tmp/translated"
    out_dir = Path("todo/translated/csv")
    for name in list(failures):
        for member in group_members(name, manifest):
            (src / member).unlink(missing_ok=True)
            (out_dir / member).unlink(missing_ok=True)
            done.discard(member)


def mark_failed(repo, failures):
    """给反复失败的文件在工作仓开一个标记 issue，不传 CSV。

    既让人看得见，也让去重认得它（known_files 是认 issue 标题的），
    不会下一轮又把它当新文件重翻一次。
    """
    subprocess.run(["gh", "label", "create", "机翻异常", "-R", repo, "--force"],
                   capture_output=True)
    for name, reason in sorted(failures.items()):
        title = name[:-len(".csv")] if name.endswith(".csv") else name
        body = (
            f"机翻连续 {RETRY_ROUNDS} 轮未通过校验，未入库。\n\n"
            f"原因：{reason}\n\n需要人工处理。"
        )
        try:
            run(["gh", "issue", "create", "-R", repo, "--title", title,
                 "--body", body, "--label", "机翻异常"])
        except subprocess.CalledProcessError:
            print(f"!! 标记 issue 创建失败，下轮会重试该文件: {title}")


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
            # 机翻摘要只服务本轮内连续的新 Dear 话数。长期摘要必须由工作仓
            # translated/proofread 人工层重建，不能让机翻状态写回 canonical 文件。
            runtime_summary = Path(tmp) / "dear-summaries.runtime.json"
            canonical_summary = VENDOR_SRC / "dear-summaries.json"
            if canonical_summary.exists():
                shutil.copy2(canonical_summary, runtime_summary)
            else:
                runtime_summary.write_text("{}\n", encoding="utf-8")
            max_tokens = configured_max_tokens()
            translate_env = {
                **os.environ,
                # 翻译记忆只读 csv_data（人工实装译文），机翻不回写，不自我污染
                "TM_DIR": str(ROOT / "csv_data"),
                "DEAR_SUMMARY_FILE": str(runtime_summary),
                "DEAR_SUMMARY_WRITE": "1",
                # 合并后的同组 CSV 必须放得进一次请求，否则又被切开等于白合并
                "MAX_LINES_PER_REQUEST": os.environ.get("MAX_LINES_PER_REQUEST", "250"),
                "MAX_TOKENS": max_tokens,
            }
            translation_error = None
            done, failures = set(), {}
            for attempt in range(1, RETRY_ROUNDS + 1):
                if attempt > 1:
                    print(f"第 {attempt} 轮：重翻 {len(failures)} 个未通过校验的文件")
                try:
                    run([YARN, "--cwd", str(PRETRANS_DIR), "translate:folder"],
                        env=translate_env)
                except subprocess.CalledProcessError as exc:
                    # fail-fast 会留下此前已经完整写出的 CSV。先把这些成果播种，
                    # 再让本轮失败；否则人工恢复时还会为已成功文件重复付费。
                    translation_error = exc
                    print("!! 翻译引擎已停止；正在保存失败前已完成的译文")

                failures = restore_csvs(manifest, done)
                # 引擎本身挂了（余额/认证/参数），重试只会再挂一次，不必烧钱
                if not failures or translation_error or attempt == RETRY_ROUNDS:
                    break
                requeue_failures(failures, manifest, done)

            stories = sorted({
                path.stem.rpartition("_")[0] or path.stem
                for path in Path("todo/translated/csv").glob("*.csv")
            })
            if stories:
                run([
                    sys.executable, str(ROOT / "tools/seed_work_repo.py"),
                    "--repo", args.work_repo,
                    "--stories", *stories,
                    "--csv-src", str(Path.cwd() / "todo/translated/csv"),
                    "--push", "--issues",
                    "--raw-dir", str(Path.cwd() / "todo/untranslated/txt"),
                ], cwd=str(ROOT))
            if failures:
                print(f"!! {len(failures)} 个文件重翻 {RETRY_ROUNDS} 轮仍未通过校验，标记待人工处理")
                mark_failed(args.work_repo, failures)
            if translation_error:
                raise SystemExit(
                    f"翻译中途失败；已先保存 {len(stories)} 个完成剧情组，"
                    "剩余文件需人工恢复后再翻"
                ) from translation_error
            if failures:
                raise SystemExit(f"{len(failures)} 个文件未入库，已在工作仓标记")
            if not stories:
                raise SystemExit("没有生成可播种的 CSV")
        finally:
            os.chdir(old_cwd)


if __name__ == "__main__":
    main()
