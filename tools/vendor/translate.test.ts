/**
 * 按行号归位的自检。跑法（从 GakumasPreTranslation 目录）：
 *   cp ../tools/vendor/translate.test.ts src/ && npx ts-node src/translate.test.ts
 *
 * 这段逻辑值得有测试：按输出位置归位时，模型少写一行同时多写一行，总数正好
 * 对上，整篇译文错位一格却不报错——静默的错译比崩溃危险得多。
 */
import assert from "assert";
import { DialogueListDeser as D } from "./translate";

function texts(m: Map<number, { name: string; text: string }>, n: number) {
  const out: (string | null)[] = [];
  for (let i = 0; i < n; i++) out.push(m.get(i)?.text ?? null);
  return out;
}

// 正常情况
assert.deepStrictEqual(
  texts(D.deserialize("0|燕|甲\n1|星南|乙\n2|燕|丙", 3), 3),
  ["甲", "乙", "丙"],
);

// 乱序：模型顺序不该影响归位
assert.deepStrictEqual(
  texts(D.deserialize("2|燕|丙\n0|燕|甲\n1|星南|乙", 3), 3),
  ["甲", "乙", "丙"],
);

// 核心场景：漏掉 1，同时多输出一行无关内容。
// 按位置归位时总数=3 会"通过"，且丙被装到 1 上；按行号归位则精确报出缺 1。
assert.deepStrictEqual(
  texts(D.deserialize("0|燕|甲\n2|燕|丙\n（以上为翻译）", 3), 3),
  ["甲", null, "丙"],
);

// 前言、空行、REF 回显都不该占位（REF 行首段不是数字）
assert.deepStrictEqual(
  texts(D.deserialize("以下是翻译：\n\nREF|0|燕|原|译\n0|燕|甲\n1|星南|乙", 2), 2),
  ["甲", "乙"],
);

// 译文里含 | 时拼回去，而不是整行丢弃
assert.strictEqual(D.deserialize("0|燕|甲|乙", 1).get(0)!.text, "甲|乙");

// 同一行号出现两次取后者（模型先回显输入再给译文）
assert.strictEqual(D.deserialize("0|燕|原文\n0|燕|译文", 1).get(0)!.text, "译文");

// 越界行号丢弃，不能污染别的行
assert.strictEqual(D.deserialize("5|燕|越界\n0|燕|甲", 1).size, 1);

// <br> 还原成 CSV 里的 \n 字面量
assert.strictEqual(D.deserialize("0|燕|上<br>下", 1).get(0)!.text, "上\\n下");

// serialize / deserialize 往返一致
const rows = [
  { name: "燕", text: "甲\\n乙" },
  { name: "{user}", text: "丙" },
];
const back = D.deserialize(D.serialize(rows), rows.length);
assert.deepStrictEqual(rows.map((r) => r.text), texts(back, rows.length));

console.log("OK: 按行号归位——乱序/缺行/回显/含|/越界 全部正确处理");
