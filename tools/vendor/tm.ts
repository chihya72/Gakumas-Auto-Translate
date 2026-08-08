import Papa from "papaparse";
import fs from "fs-extra";
import path from "path";
import log from "loglevel";
import storyIndex from "./story-index.json";
import characterCards from "./character-cards.json";
import glossary from "./glossary.json";

export interface TMEntry {
  text: string;
  trans: string;
  name: string;
  story: string; // 规范分组 key，如 cidol-amao-3-017 / pstory/001/amao / csprt-1-0000
  human: boolean;
  type: string; // 规范目录名：cidol | csprt | pstory | pevent | dear | event | live | ...
  character: string; // 角色码（amao/atbm/...），无则 ""
  episode: number; // 好感度（dear）/cidol 话数，非此类 -1
  card: string; // pstory: "001"；csprt: "1-0005"；pevent: "001-activity"；其余 ""
  batch: string; // csprt 批次（"1"/"2"/...），其余 ""
}

export interface StoryInfo {
  type: string;
  group: string;
  character: string;
  episode: number;
  card: string;
  batch: string;
}

/**
 * 剧情上下文策略。角色卡与术语表对所有类型一律加载，不受此处控制。
 * - group-merge  同组段落在管线侧合并成一次请求，引擎内不再注入 REF
 * - sequential   顺序翻译，同组已译段落按原顺序全量注入
 * - summary      滚动摘要 + 上一话全文
 * - exact-human  精确匹配套用，且只复用人工译文
 * - none         不注入任何剧情上下文
 */
export type RefMode =
  | "group-merge"
  | "sequential"
  | "summary"
  | "exact-human"
  | "none";

/** 与 gakumas-viewer 工作台一致的类型 → 策略映射（未列出的类型一律 none） */
export const STORY_MODES: Record<string, RefMode> = {
  cidol: "group-merge", // P卡剧情：同一批 01~03 合并成一次请求
  csprt: "group-merge", // S卡剧情：同一批 01~03 合并成一次请求
  event: "sequential", // 活动剧情：五段顺序翻译，前文按原顺序注入
  dear: "summary", // 好感度剧情：滚动摘要 + 上一话全文
  pstory: "exact-human", // 培养故事：同样文本直接套用，仅限人工译文
  pevent: "none", // 培养事件：直接翻译，不必参考
};

// ---------- 角色卡 / 术语表 / 滚动摘要 ----------
// 这三块对所有剧情类型一律加载，不受 STORY_MODES 控制。

interface CharacterCard {
  zh?: string;
  first_person?: string;
  politeness?: string;
  speech?: string[];
  address?: Record<string, string>;
}

export interface DearSummary {
  through_episode?: number;
  summary?: string;
  fixed?: Record<string, string>;
}

/**
 * dear 摘要是**可写**状态，必须落回本仓库的 tools/vendor/dear-summaries.json，
 * 落在 CI 的临时 clone 里翻完就丢了。所以不用编译期 import，改成运行时按
 * DEAR_SUMMARY_FILE 指定的路径读写。未设置 = 不启用摘要（本地跑不受影响）。
 */
function summaryFile(): string | undefined {
  return process.env.DEAR_SUMMARY_FILE || undefined;
}

export function loadDearSummaries(): Record<string, DearSummary> {
  const file = summaryFile();
  if (!file || !fs.existsSync(file)) return {};
  try {
    return JSON.parse(fs.readFileSync(file, "utf-8"));
  } catch (e) {
    log.warn(`dear 摘要读取失败，本轮不注入摘要: ${e.message}`);
    return {};
  }
}

export function saveDearSummary(character: string, entry: DearSummary): void {
  const file = summaryFile();
  if (!file) return;
  const all = loadDearSummaries();
  all[character] = entry;
  fs.writeFileSync(file, JSON.stringify(all, null, 2) + "\n", "utf-8");
  log.info(`已更新 dear 摘要: ${character} -> 第 ${entry.through_episode} 话`);
}

/** 数据文件里以 _ 开头的键是说明性注释，不参与注入 */
function isDataKey(key: string): boolean {
  return !key.startsWith("_");
}

/**
 * 角色卡：只注入本次请求实际出场的角色，且按固定顺序（出场量降序，即
 * 文件内声明顺序）排列——同组文件角色集合相同时前缀一致，还能吃到前缀缓存。
 */
export function characterCardBlock(names: Set<string>): string {
  const cards = characterCards as Record<string, CharacterCard>;
  const blocks: string[] = [];
  for (const name of Object.keys(cards)) {
    if (!isDataKey(name) || !names.has(name)) continue;
    const card = cards[name];
    const lines: string[] = [];
    if (card.first_person) lines.push(`- 自称：${card.first_person}`);
    if (card.politeness) lines.push(`- 敬语：${card.politeness}`);
    for (const rule of card.speech || []) lines.push(`- 语气：${rule}`);
    for (const [other, form] of Object.entries(card.address || {})) {
      lines.push(`- 称呼 ${other}：${form}`);
    }
    if (lines.length === 0) continue;
    const title = card.zh && card.zh !== name ? `${name} / ${card.zh}` : name;
    blocks.push(`【${title}】\n${lines.join("\n")}`);
  }
  if (blocks.length === 0) return "";
  return `角色卡（硬约束，必须遵守）\n\n${blocks.join("\n\n")}`;
}

/**
 * 术语表：只注入原文中实际出现的词条。全局表可能几百条，全塞是浪费。
 * extra 是 event 的本活动临时表；冲突时全局表优先。
 */
export function glossaryBlock(
  texts: string[],
  extra?: Record<string, string>,
): string {
  const global = glossary as Record<string, string>;
  const merged: Record<string, string> = {};
  for (const [jp, zh] of Object.entries(extra || {})) merged[jp] = zh;
  for (const [jp, zh] of Object.entries(global)) {
    if (isDataKey(jp)) merged[jp] = zh; // 全局表覆盖临时表
  }
  const joined = texts.join("\n");
  const hits = Object.entries(merged).filter(([jp]) => joined.includes(jp));
  if (hits.length === 0) return "";
  const lines = hits.map(([jp, zh]) => `TERM|${jp}|${zh}`).join("\n");
  return `术语表（硬约束，出现即必须使用）\n\n${lines}`;
}

/** dear 滚动摘要：几百 token 顶掉几千行 REF，且模型真的读得进去 */
export function summaryBlock(storyKey: string): string {
  const info = classifyStory(storyKey);
  if (info.type !== "dear" || !info.character) return "";
  const entry = loadDearSummaries()[info.character];
  if (!entry || !entry.summary) return "";
  if (info.episode >= 0 && entry.through_episode !== info.episode - 1) {
    log.warn(
      `dear 摘要覆盖到第 ${entry.through_episode} 话，但当前是第 ${info.episode} 话——摘要可能过期`,
    );
  }
  const parts = [`剧情摘要（本角色此前进展）\n\n${entry.summary}`];
  const fixed = Object.entries(entry.fixed || {});
  if (fixed.length > 0) {
    parts.push(
      "已固定的称呼（硬约束，优先级高于角色卡）\n" +
        fixed.map(([k, v]) => `- ${k}：${v}`).join("\n"),
    );
  }
  return parts.join("\n\n");
}

const AI_TRANSLATOR_RE =
  /(gpt|deepseek|claude|gemini|glm|qwen|kimi|minimax|grok|o1|o3|llama|mistral|sakura|ernie|hunyuan)/i;

export function isHumanTranslator(tag: string): boolean {
  if (!tag) return false;
  return !AI_TRANSLATOR_RE.test(tag);
}

/** 从规范索引条目转成 StoryInfo */
function fromIndex(hit: {
  c: string;
  g: string;
  ch?: string;
  ep?: number;
  card?: string;
  batch?: string;
}): StoryInfo {
  return {
    type: hit.c,
    group: hit.g,
    character: hit.ch || "",
    episode: hit.ep ?? -1,
    card: hit.card || "",
    batch: hit.batch || "",
  };
}

/**
 * 解析规范路径段（data/adv 下的相对路径或分组 key）。
 * 类型 = 规范目录名（cidol/csprt/pstory/pevent/dear/event/live/unit/...）。
 */
export function classifyCanonical(seg: string[]): StoryInfo {
  const first = seg[0] || "";
  let m: RegExpMatchArray | null;

  m = first.match(/^cidol-([a-z0-9]+)-(\d+)-(\d+)$/i);
  if (m) {
    return {
      type: "cidol",
      group: first,
      character: m[1],
      episode: parseInt(m[3], 10),
      card: m[3],
      batch: "",
    };
  }

  m = first.match(/^csprt-(\d+)-(\d+)$/i);
  if (m) {
    return {
      type: "csprt",
      group: first,
      character: "",
      episode: -1,
      card: `${m[1]}-${m[2]}`,
      batch: m[1],
    };
  }

  if (first === "pstory" && seg.length >= 3) {
    return {
      type: "pstory",
      group: seg.slice(0, 3).join("/"),
      character: seg[2],
      episode: -1,
      card: seg[1],
      batch: "",
    };
  }

  if (first === "pevent" && seg.length >= 4) {
    return {
      type: "pevent",
      group: seg.slice(0, 4).join("/"),
      character: seg[2],
      episode: -1,
      card: `${seg[1]}-${seg[3]}`,
      batch: "",
    };
  }

  if (first === "dear" && seg.length >= 3) {
    const fileBase = seg[2].replace(/\.(csv|txt)$/i, "");
    const ep = parseInt(fileBase.match(/^(\d+)/)?.[1] || "-1", 10);
    return {
      type: "dear",
      group: `dear/${seg[1]}/${String(ep).padStart(3, "0")}`,
      character: seg[1],
      episode: ep,
      card: String(ep),
      batch: "",
    };
  }

  if (first === "live" && seg.length >= 3) {
    return {
      type: "live",
      group: seg.slice(0, 3).join("/"),
      character: seg[1],
      episode: -1,
      card: "",
      batch: "",
    };
  }

  if (first === "event" && seg.length >= 2) {
    return {
      type: "event",
      group: seg.slice(0, 2).join("/"),
      character: "",
      episode: -1,
      card: "",
      batch: "",
    };
  }

  if (first === "gasha" && seg.length >= 2) {
    return {
      type: "gasha",
      group: seg.slice(0, 2).join("/"),
      character: "",
      episode: -1,
      card: "",
      batch: "",
    };
  }

  if (first === "unit" && seg.length >= 2) {
    return {
      type: "unit",
      group: seg.slice(0, 2).join("/"),
      character: "",
      episode: -1,
      card: "",
      batch: "",
    };
  }

  if (first === "pgrowth" && seg.length >= 3) {
    return {
      type: "pgrowth",
      group: seg.slice(0, 3).join("/"),
      character: seg[2],
      episode: -1,
      card: seg[1],
      batch: "",
    };
  }

  if (first === "presult" && seg.length >= 2) {
    return {
      type: "presult",
      group: seg.slice(0, 2).join("/"),
      character: "",
      episode: -1,
      card: "",
      batch: "",
    };
  }

  const group = seg.length >= 2 ? seg.slice(0, 2).join("/") : first;
  return { type: first, group, character: "", episode: -1, card: "", batch: "" };
}

/** 扁平文件名解析（旧逻辑，仅作为索引未覆盖时的兜底）。 */
export function parseStory(name: string): StoryInfo {
  const base = name.replace(/\.(csv|txt)$/i, "");
  let m: RegExpMatchArray | null;

  m = base.match(/^adv_cidol-([a-z0-9]+)-(\d+)-(\d+)(?:[-_]\d+)?$/i);
  if (m) {
    return {
      type: "cidol",
      group: `cidol-${m[1]}-${m[2]}-${m[3]}`,
      character: m[1],
      episode: parseInt(m[3], 10),
      card: m[3],
      batch: "",
    };
  }

  m = base.match(/^adv_csprt-(\d+)-(\d+)(?:[-_]\d+)?$/i);
  if (m) {
    return {
      type: "csprt",
      group: `csprt-${m[1]}-${m[2]}`,
      character: "",
      episode: -1,
      card: `${m[1]}-${m[2]}`,
      batch: m[1],
    };
  }

  m = base.match(/^adv_pstory_(\d+)_([a-z0-9]+)_(.+)$/i);
  if (m) {
    return {
      type: "pstory",
      group: `pstory/${m[1]}/${m[2]}`,
      character: m[2],
      episode: -1,
      card: m[1],
      batch: "",
    };
  }

  m = base.match(/^adv_pevent_(\d+)_([a-z0-9]+)_(.+)$/i);
  if (m) {
    const restSeg = m[3].split("_");
    const eventName = restSeg.slice(0, -1).join("_") || restSeg[0];
    return {
      type: "pevent",
      group: `pevent/${m[1]}/${m[2]}/${eventName}`,
      character: m[2],
      episode: -1,
      card: `${m[1]}-${eventName}`,
      batch: "",
    };
  }

  m = base.match(/^adv_dear_([a-z0-9]+)_(\d+)(?:-\d+)?$/i);
  if (m) {
    return {
      type: "dear",
      group: `dear/${m[1]}/${m[2]}`,
      character: m[1],
      episode: parseInt(m[2], 10),
      card: m[2],
      batch: "",
    };
  }

  return { type: "other", group: base, character: "", episode: -1, card: "", batch: "" };
}

/**
 * 统一分类入口：优先查规范索引（story-index.json），
 * 其次按规范路径解析，最后退到扁平名正则。
 */
export function classifyStory(name: string): StoryInfo {
  const base = name.replace(/\.(csv|txt)$/i, "");
  const hit = (storyIndex as Record<string, any>)[base];
  if (hit) return fromIndex(hit);
  if (base.includes("/")) return classifyCanonical(base.split("/"));
  const flat = parseStory(base);
  if (flat.type !== "other") return flat;
  return classifyCanonical(base.split("/"));
}

export function storyKeyFromName(name: string): string {
  return classifyStory(name).group;
}

function pushEntry(map: Map<string, TMEntry[]>, key: string, entry: TMEntry) {
  let arr = map.get(key);
  if (!arr) {
    arr = [];
    map.set(key, arr);
  }
  arr.push(entry);
}

function maxRefLines(): number {
  const v = parseInt(process.env.TM_MAX_REF || "40", 10);
  return Number.isFinite(v) && v > 0 ? v : 40;
}

/**
 * 翻译记忆：从 csv_data（历史翻译 CSV）加载 原文→译文 索引，
 * 按规范分类（story-index.json）分组，供翻译时生成前文参考。
 */
export class TranslationMemory {
  private exact = new Map<string, TMEntry>();
  private stories = new Map<string, TMEntry[]>();
  private chars = new Map<string, TMEntry[]>();
  private byChar = new Map<string, TMEntry[]>();
  private loaded = false;
  private total = 0;

  get isLoaded(): boolean {
    return this.loaded;
  }

  get size(): number {
    return this.total;
  }

  loadDir(dir: string | undefined): void {
    if (this.loaded) return;
    this.loaded = true;
    if (!dir || !fs.existsSync(dir)) {
      log.warn(`Translation memory dir not found: ${dir || "(unset)"}, context lookup disabled`);
      return;
    }
    const files = fs
      .readdirSync(dir)
      .filter((f) => f.endsWith(".csv"))
      .sort();
    for (const file of files) {
      const filePath = path.join(dir, file);
      let parsed: any[];
      try {
        parsed = Papa.parse(fs.readFileSync(filePath, "utf-8"), {
          header: true,
        }).data as any[];
      } catch (e) {
        log.warn(`TM: skip unreadable ${file}: ${e.message}`);
        continue;
      }
      const info = classifyStory(file);
      let translator = "";
      for (const row of parsed) {
        if (row && row.id === "译者") {
          translator = row.name || "";
          break;
        }
      }
      const human = isHumanTranslator(translator);
      for (const row of parsed) {
        if (!row || !row.text || !row.trans) continue;
        const entry: TMEntry = {
          text: row.text,
          trans: row.trans,
          name: row.name || "",
          story: info.group,
          human,
          type: info.type,
          character: info.character,
          episode: info.episode,
          card: info.card,
          batch: info.batch,
        };
        const prev = this.exact.get(entry.text);
        const score = entry.human ? 2 : 1;
        if (!prev || score >= (prev.human ? 2 : 1)) {
          this.exact.set(entry.text, entry);
        }
        pushEntry(this.stories, info.group, entry);
        if (entry.name) pushEntry(this.chars, entry.name, entry);
        if (info.character) pushEntry(this.byChar, info.character, entry);
        this.total++;
      }
    }
    log.info(`TM loaded: ${this.total} pairs from ${files.length} files`);
  }

  lookup(text: string): TMEntry | undefined {
    return this.exact.get(text);
  }

  add(entry: { text: string; trans: string; name: string; story: string }): void {
    const info = classifyStory(entry.story);
    const full: TMEntry = {
      text: entry.text,
      trans: entry.trans,
      name: entry.name || "",
      story: info.group,
      human: false,
      type: info.type,
      character: info.character,
      episode: info.episode,
      card: info.card,
      batch: info.batch,
    };
    const prev = this.exact.get(full.text);
    if (!prev) {
      this.exact.set(full.text, full);
      this.total++;
    }
    pushEntry(this.stories, full.story, full);
    if (full.name) pushEntry(this.chars, full.name, full);
    if (full.character) pushEntry(this.byChar, full.character, full);
  }

  /** 参考策略入口 */
  examples(storyKey: string, max = maxRefLines()): TMEntry[] {
    const info = classifyStory(storyKey);
    switch (STORY_MODES[info.type] || "none") {
      case "sequential":
        // event 五段之间靠这个衔接，截断会让后段看不全前段——不设上限
        return this.sequentialExamples(info, Number.MAX_SAFE_INTEGER);
      case "summary":
        return this.previousEpisode(info, max);
      default:
        return []; // group-merge / exact-human / none：不注入 REF
    }
  }

  /** 生成注入提示词的参考块；REF| 前缀使其即使被模型回显也不会被解析成译文 */
  referenceBlock(storyKey: string): string {
    const info = classifyStory(storyKey);
    const mode = STORY_MODES[info.type] || "none";
    if (mode !== "sequential" && mode !== "summary") return "";
    const ex = this.examples(storyKey);
    if (ex.length === 0) return "";
    const header =
      mode === "sequential"
        ? "以下是同一剧情此前段落的翻译，按剧情顺序排列，请保持剧情衔接、人名和术语的一致。"
        : "以下是该角色上一话好感度剧情的全文，请保持人设、称呼和关系进展的连贯一致。";
    const lines = ex.map((e, i) => `REF|${i}|${e.name}|${e.text}|${e.trans}`).join("\n");
    return `${header}\n这些行只是参考，不要翻译或输出它们。\n\n${lines}`;
  }

  /** summary（dear）：只取上一话全文，按原顺序。更早的历史由滚动摘要承载。 */
  private previousEpisode(info: StoryInfo, max: number): TMEntry[] {
    if (info.type !== "dear" || info.episode < 0) return [];
    const previous = (this.byChar.get(info.character) || []).filter(
      (e) => e.type === "dear" && e.episode >= 0 && e.episode < info.episode,
    );
    if (previous.length === 0) return [];
    const lastEp = Math.max(...previous.map((e) => e.episode));
    const seen = new Set<string>();
    const out: TMEntry[] = [];
    this.pick(previous.filter((e) => e.episode === lastEp), out, seen, max);
    return out;
  }

  private pick(
    entries: TMEntry[],
    out: TMEntry[],
    seen: Set<string>,
    cap: number,
  ) {
    for (const e of entries) {
      if (out.length >= cap) return;
      const key = `${e.text}\u0001${e.trans}`;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push(e);
    }
  }

  /**
   * sequential（event）：同一剧情组已翻译的段落，按原文件顺序全量注入。
   * 不排序——按文本长度排序会把"一段有前后关系的对话"打散成词汇表，剧情线索就没了。
   * 不跨组兜底——不同活动/不同卡是不同故事，塞进来对剧情连贯是负作用；
   * 跨组需要的一致性由角色卡和术语表负责。
   */
  private sequentialExamples(info: StoryInfo, max: number): TMEntry[] {
    const seen = new Set<string>();
    const out: TMEntry[] = [];
    this.pick(this.stories.get(info.group) || [], out, seen, max);
    return out;
  }

}

let shared: TranslationMemory | null = null;

export function getSharedTM(): TranslationMemory {
  if (!shared) shared = new TranslationMemory();
  return shared;
}
