"""校验失败要跳过而不是中止整批，并且能被重翻一轮之后收回来。

以前一处标签对不上就 raise SystemExit，同批已经付过钱的几十个文件全丢。
这里盯住三件事：坏文件不拖累好文件、好文件不会被重复处理、
重翻同组时整组一起回炉（同组是一次请求翻出来的，只补一段会错位）。
"""
import csv
import importlib.util
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_spec = importlib.util.spec_from_file_location("acp", ROOT / "tools/auto_campus_pipeline.py")
acp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(acp)

FIELDS = ["id", "name", "text", "trans"]
RUBY = "<r\\=コンポーザー>作曲家</r>とのミーティング"


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


def orig_rows(name, text):
    return [{"id": "0", "name": "咲季", "text": text, "trans": ""},
            {"id": "info", "name": name.replace(".csv", ".txt"), "text": "", "trans": ""}]


def translated_rows(name, text, trans):
    """引擎的输出：text 是掩码后的，末尾多一行译者。"""
    return [
        {"id": "0", "name": "咲季", "text": acp.mask_tags(text), "trans": trans},
        {"id": "info", "name": name.replace(".csv", ".txt"), "text": "", "trans": ""},
        {"id": "译者", "name": "deepseek-v4-pro", "text": "", "trans": ""},
    ]


def good_trans(text):
    """模型正常输出：占位符原样带回。"""
    return "[译]" + acp.mask_tags(text)


def bad_trans(text):
    """模型漏抄一个占位符。"""
    return good_trans(text).replace("GAT_TAG_0", "", 1)


def setup(tmp, files):
    """files: {文件名: 译文}。原文一律含一对 ruby 标签。"""
    os.chdir(tmp)
    acp.PRETRANS_DIR = Path(tmp)
    for name, trans in files.items():
        write_csv(Path("todo/untranslated/csv_orig") / name, orig_rows(name, RUBY))
        write_csv(Path(tmp) / "tmp/translated" / name, translated_rows(name, RUBY, trans))


def main():
    old_cwd = Path.cwd()
    try:
        # --- 1. 一个坏文件不能拖累同批的好文件 ---
        with tempfile.TemporaryDirectory() as tmp:
            setup(tmp, {"a.csv": good_trans(RUBY),
                        "b.csv": bad_trans(RUBY),
                        "c.csv": good_trans(RUBY)})
            done = set()
            failures = acp.restore_csvs({}, done)
            assert set(failures) == {"b.csv"}, failures
            out = {p.name for p in Path("todo/translated/csv").glob("*.csv")}
            assert out == {"a.csv", "c.csv"}, out
            assert done == {"a.csv", "c.csv"}, done

            # --- 2. 重翻一轮：坏文件的输出被清掉，好文件不再重复处理 ---
            acp.requeue_failures(failures, {}, done)
            assert not (Path(tmp) / "tmp/translated/b.csv").exists()
            assert done == {"a.csv", "c.csv"}, done
            write_csv(Path(tmp) / "tmp/translated/b.csv",
                      translated_rows("b.csv", RUBY, good_trans(RUBY)))
            assert acp.restore_csvs({}, done) == {}
            out = {p.name for p in Path("todo/translated/csv").glob("*.csv")}
            assert out == {"a.csv", "b.csv", "c.csv"}, out
            os.chdir(old_cwd)   # Windows: cwd 在临时目录里就删不掉它

        # --- 3. 同组只坏一段，整组一起回炉 ---
        with tempfile.TemporaryDirectory() as tmp:
            parts = ["g_01.csv", "g_02.csv", "g_03.csv"]
            manifest = {"g_01.csv": [[p, 1] for p in parts]}
            setup(tmp, {p: (bad_trans(RUBY) if p == "g_02.csv" else good_trans(RUBY))
                        for p in parts})
            done = set()
            failures = acp.restore_csvs(manifest, done)
            assert set(failures) == {"g_02.csv"}, failures
            acp.requeue_failures(failures, manifest, done)
            left = {p.name for p in (Path(tmp) / "tmp/translated").glob("*.csv")}
            assert left == set(), f"整组都该回炉，剩下: {left}"
            assert done == set(), done
            assert not list(Path("todo/translated/csv").glob("*.csv"))
            os.chdir(old_cwd)

        # --- 4. 网络瞬时故障要重试，不能一次 TCP reset 就崩掉整轮 ---
        acp.NET_BACKOFF = 0          # 测试里不真等
        calls = []

        def flaky():
            calls.append(1)
            if len(calls) < 3:
                raise OSError(104, "Connection reset by peer")
            return "ok"

        assert acp.retry(flaky, "下载") == "ok"
        assert len(calls) == 3, calls

        # 一直失败要在用尽次数后抛出，不能无限重试、也不能吞掉
        dead = []

        def always_fails():
            dead.append(1)
            raise OSError(104, "Connection reset by peer")

        try:
            acp.retry(always_fails, "下载")
            raise AssertionError("重试用尽后必须抛出")
        except OSError:
            pass
        assert len(dead) == acp.NET_RETRIES, dead
    finally:
        os.chdir(old_cwd)
    print("OK: 坏文件跳过不中止、好文件不重复处理、同组整组回炉、瞬时故障会重试")


if __name__ == "__main__":
    main()
