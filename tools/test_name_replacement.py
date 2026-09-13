"""TXT 人名回归：短名不能破坏长名，本地两种合并模式都必须生效。"""
import contextlib
import csv
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gakumas_auto_translate.modules.merger import (
    process_bilingual,
    process_chinese_only,
    replace_txt_names,
)


NAME_DICT = {"ことね": "琴音", "ことねの脳内イメージ": "琴音的脑补"}


class NameReplacementTests(unittest.TestCase):
    def test_complete_values_and_single_pass(self):
        raw = (
            "name=ことね\r\n"
            "[message text=<em>ことね</em> name=ことねの脳内イメージ]\n"
            "[message text=x name= ことね speaker=x]\n"
            "[message text=x name=ことね？ rename=ことね]\n"
            "[message text=x name={user}]\n"
            "[message text=x name=？？？]\n"
            "[message text=x name=A.+]\n"
            "[message text=x name=琴音]"
        )
        expected = (
            "name=琴音\r\n"
            "[message text=<em>ことね</em> name=琴音的脑补]\n"
            "[message text=x name= 琴音 speaker=x]\n"
            "[message text=x name=ことね？ rename=ことね]\n"
            "[message text=x name={user}]\n"
            "[message text=x name=？？？]\n"
            "[message text=x name=$1\\名字]\n"
            "[message text=x name=另一名字]"
        )
        # 替换结果恰好也是字典键时，不得在同一次处理中再次翻译。
        dictionary = {**NAME_DICT, "琴音": "另一名字", "A.+": "$1\\名字"}
        self.assertEqual(replace_txt_names(raw, dictionary), expected)
        self.assertEqual(replace_txt_names(raw, {}), raw)

    def test_both_merge_modes(self):
        rows = [
            {"id": "0000000000000", "name": "ことね", "text": "長い長い台詞", "trans": "较长台词"},
            {"id": "0000000000000", "name": "ことねの脳内イメージ", "text": "短い", "trans": "短句"},
        ]
        raw = (
            "[message text=長い長い台詞 name=ことね]\n"
            "[message text=短い name=ことねの脳内イメージ]\n"
            "[message text=短い name=ことねの脳内イメージ]\n"
            "[message text=別の台詞 name=ことね？]"
        )
        for process in (process_chinese_only, process_bilingual):
            with self.subTest(mode=process.__name__), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                csv_dir = root / "todo" / "translated" / "csv"
                txt_dir = root / "todo" / "untranslated" / "txt"
                csv_dir.mkdir(parents=True)
                txt_dir.mkdir(parents=True)
                with (csv_dir / "sample.csv").open("w", encoding="utf-8", newline="") as stream:
                    writer = csv.DictWriter(stream, fieldnames=["id", "name", "text", "trans"])
                    writer.writeheader()
                    writer.writerows(rows)
                (txt_dir / "sample.txt").write_text(raw, encoding="utf-8")
                (root / "name_dictionary.json").write_text(json.dumps(NAME_DICT), encoding="utf-8")
                with contextlib.chdir(root), contextlib.redirect_stdout(io.StringIO()):
                    process()
                result = (root / "todo" / "translated" / "txt" / "sample.txt").read_text(encoding="utf-8")
                self.assertIn("name=琴音]", result)
                self.assertEqual(result.count("name=琴音的脑补]"), 2)
                self.assertIn("name=ことね？]", result)
                self.assertNotIn("琴音の脳内", result)
                self.assertIn("较长台词", result)
                self.assertIn("短句", result)
                self.assertFalse((root / "error_report.csv").exists())


if __name__ == "__main__":
    unittest.main()
