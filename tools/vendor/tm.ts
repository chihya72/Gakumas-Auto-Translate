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
  sourceFile?: string;
  translator?: string;
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
 * 剧情策略。角色卡与术语表对所有类型一律加载，不受此处控制。
 * - group-merge  同组段落在管线侧合并成一次请求，引擎内不再注入 REF
 * - sequential   顺序翻译，同组已译段落按原顺序全量注入
 * - summary      只注入滚动摘要；不再搭上一话全文
 * - none         不注入任何剧情上下文
 */
export type ContextMode = "group-merge" | "sequential" | "summary" | "none";
export type PrefillMode = "exact-row" | "none";

export interface StoryPolicy {
  context: ContextMode;
  prefill: PrefillMode;
}

const DEFAULT_STORY_POLICY: StoryPolicy = { context: "none", prefill: "none" };

/**
 * 与 gakumas-viewer 工作台一致的显式策略表。未列出的类型一律不注入剧情
 * 上下文，也不做精确复用；精确复用绝不是所有类型共享的通用机制。
 */
export const STORY_POLICIES: Record<string, StoryPolicy> = {
  cidol: { context: "group-merge", prefill: "none" },
  csprt: { context: "group-merge", prefill: "none" },
  event: { context: "sequential", prefill: "none" },
  dear: { context: "summary", prefill: "none" },
  pstory: { context: "none", prefill: "exact-row" },
  pevent: { context: "none", prefill: "exact-row" },
};

export function storyPolicy(type: string): StoryPolicy {
  return STORY_POLICIES[type] || DEFAULT_STORY_POLICY;
}

// ---------- 角色卡 / 术语表 / 滚动摘要 ----------
// 这三块对所有剧情类型一律加载，不受 STORY_POLICIES 控制。

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
  checkpoints?: DearSummaryCheckpoint[];
}

export interface DearSummaryCheckpoint {
  from_episode: number;
  through_episode: number;
  input_hash: string;
  /** 到这一块为止的【累积】摘要快照，不是这几话的摘要 */
  summary: string;
  /** 只讲 from_episode~through_episode 这几话的剧情；串起来就是一条完整剧情线 */
  segment?: string;
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
function mappingParts(value: string): Array<{ jp: string; text: string }> {
  return value.split("；").map((text) => ({
    jp: text.split("→")[0].trim(),
    text: text.trim(),
  })).filter((part) => part.jp && part.text);
}

export function characterMappings(name: string): Record<string, string> {
  const card = (characterCards as Record<string, CharacterCard>)[name];
  if (!card) return {};
  const mappings: Record<string, string> = {};
  for (const value of [card.first_person, ...Object.values(card.address || {})]) {
    if (!value) continue;
    for (const part of mappingParts(value)) {
      const arrow = part.text.indexOf("→");
      if (arrow >= 0) mappings[part.jp] = part.text.slice(arrow + 1).trim();
    }
  }
  return mappings;
}

export function characterCardBlock(
  names: Set<string>,
  higherPriorityKeys: Set<string> = new Set(),
): string {
  const cards = characterCards as Record<string, CharacterCard>;
  const blocks: string[] = [];
  for (const name of Object.keys(cards)) {
    if (!isDataKey(name) || !names.has(name)) continue;
    const card = cards[name];
    const lines: string[] = [];
    if (card.first_person) {
      const kept = mappingParts(card.first_person)
        .filter((part) => !higherPriorityKeys.has(part.jp))
        .map((part) => part.text);
      if (kept.length > 0) lines.push(`- 自称：${kept.join("；")}`);
    }
    if (card.politeness) lines.push(`- 敬语：${card.politeness}`);
    for (const rule of card.speech || []) lines.push(`- 语气：${rule}`);
    for (const [other, form] of Object.entries(card.address || {})) {
      const kept = mappingParts(form)
        .filter((part) => !higherPriorityKeys.has(part.jp))
        .map((part) => part.text);
      if (kept.length > 0) lines.push(`- 称呼 ${other}：${kept.join("；")}`);
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
export function activeGlossary(
  texts: string[],
  extra?: Record<string, string>,
): Record<string, string> {
  const global = glossary as Record<string, string>;
  const merged: Record<string, string> = {};
  for (const [jp, zh] of Object.entries(extra || {})) merged[jp] = zh;
  for (const [jp, zh] of Object.entries(global)) {
    if (isDataKey(jp)) merged[jp] = zh; // 全局表覆盖临时表
  }
  const joined = texts.join("\n");
  return Object.fromEntries(Object.entries(merged).filter(([jp]) => joined.includes(jp)));
}

export function glossaryBlock(
  texts: string[],
  extra?: Record<string, string>,
): string {
  const hits = Object.entries(activeGlossary(texts, extra));
  if (hits.length === 0) return "";
  const lines = hits.map(([jp, zh]) => `TERM|${jp}|${zh}`).join("\n");
  return `术语表（硬约束，出现即必须使用）\n\n${lines}`;
}

/** dear 滚动摘要：几百 token 顶掉几千行 REF，且模型真的读得进去 */
export function activeDearFixed(
  storyKey: string,
  higherPriorityTerms: Set<string> = new Set(),
): Record<string, string> {
  const info = classifyStory(storyKey);
  if (info.type !== "dear" || !info.character) return {};
  const entry = loadDearSummaries()[info.character];
  if (
    !entry ||
    !entry.summary ||
    (info.episode >= 0 && entry.through_episode !== info.episode - 1)
  ) return {};
  return Object.fromEntries(Object.entries(entry.fixed || {}).filter(([jp]) => {
    if (!higherPriorityTerms.has(jp)) return true;
    log.warn(`dear 固定译法 ${jp} 与术语表冲突，按优先级采用术语表`);
    return false;
  }));
}

export function summaryBlock(
  storyKey: string,
  higherPriorityTerms: Set<string> = new Set(),
  resolvedFixed?: Record<string, string>,
): string {
  const info = classifyStory(storyKey);
  if (info.type !== "dear" || !info.character) return "";
  const entry = loadDearSummaries()[info.character];
  if (!entry || !entry.summary) return "";
  if (info.episode >= 0 && entry.through_episode !== info.episode - 1) {
    log.warn(
      `dear 摘要覆盖到第 ${entry.through_episode} 话，但当前是第 ${info.episode} 话——拒绝注入非连续摘要`,
    );
    return "";
  }
  const parts = [`剧情摘要（本角色此前进展）\n\n${entry.summary}`];
  // 累积摘要被反复重写，早期细节必然被压掉；分段剧情线把每几话的
  // 原始梗概原样留下来，两者互补。旧检查点没有 segment，自然就不注入。
  const timeline = (entry.checkpoints || [])
    .filter((checkpoint) => checkpoint.segment)
    .map((checkpoint) => {
      const span = checkpoint.from_episode === checkpoint.through_episode
        ? `第 ${checkpoint.from_episode} 话`
        : `第 ${checkpoint.from_episode}~${checkpoint.through_episode} 话`;
      return `【${span}】${checkpoint.segment}`;
    });
  if (timeline.length > 0) {
    parts.push(
      "分段剧情线（按话数顺序，供理解前情，不是翻译对象）\n" +
        timeline.join("\n"),
    );
  }
  const fixed = Object.entries(resolvedFixed || activeDearFixed(storyKey, higherPriorityTerms));
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

export function isMachineTranslator(tag: string): boolean {
  return Boolean(tag && AI_TRANSLATOR_RE.test(tag));
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

export type TranslationRowKind = "message" | "choice" | "narration" | "title";

export interface ExactRow {
  id?: string;
  name?: string;
  text: string;
}

/** 行类型是精确复用键的一部分；空说话人的普通行按旁白处理。 */
export function translationRowKind(row: ExactRow): TranslationRowKind {
  if (row.id === "select") return "choice";
  if (row.name === "__title__") return "title";
  if (row.name === "__narration__" || !row.name) return "narration";
  return "message";
}

/**
 * 完整整行签名。这里故意不 trim、不折叠空白、不做子串匹配：标点、换行和
 * 占位符都是原文的一部分，任一差异都必须交回模型判断。
 */
export function exactRowKey(type: string, row: ExactRow): string {
  return JSON.stringify([type, translationRowKind(row), row.name || "", row.text]);
}

/** 精确复用也必须服从比它更高的全局禁令、术语表和占位符完整性。 */
export function exactReuseAllowed(
  source: string,
  translated: string,
  terms: Record<string, string>,
): boolean {
  if (!translated || translated.includes("酱") || translated.includes("呐")) return false;
  if (/(^|[。！？!?…\n])\s*嘛(?=$|[，,。！？!?…\s])/.test(translated)) return false;
  for (const [jp, zh] of Object.entries(terms)) {
    if (source.includes(jp) && !translated.includes(zh)) return false;
  }
  const placeholders = (value: string) => value.match(/GAT_TAG_\d+/g) || [];
  const sourceTags = placeholders(source);
  const translatedTags = placeholders(translated);
  return sourceTags.length === translatedTags.length &&
    sourceTags.every((tag, index) => tag === translatedTags[index]);
}

/**
 * 翻译记忆：从 csv_data（历史翻译 CSV）加载 原文→译文 索引，
 * 按规范分类（story-index.json）分组，供翻译时生成前文参考。
 */
export class TranslationMemory {
  /** 同一严格整行签名可能有多个译法；按人工 > 机翻分层，同层歧义不命中。 */
  private exact = new Map<string, Map<string, TMEntry>>();
  private stories = new Map<string, TMEntry[]>();
  private chars = new Map<string, TMEntry[]>();
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
      const machine = isMachineTranslator(translator);
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
          sourceFile: file,
          translator,
        };
        if ((human || machine) && storyPolicy(info.type).prefill === "exact-row") {
          const key = exactRowKey(info.type, row);
          let candidates = this.exact.get(key);
          if (!candidates) {
            candidates = new Map<string, TMEntry>();
            this.exact.set(key, candidates);
          }
          const existing = candidates.get(entry.trans);
          // 同一译文本身不构成冲突；若人工与机翻相同，保留人工来源供优先级判断。
          if (!existing || (!existing.human && entry.human)) candidates.set(entry.trans, entry);
        }
        pushEntry(this.stories, info.group, entry);
        if (entry.name) pushEntry(this.chars, entry.name, entry);
        this.total++;
      }
    }
    log.info(`TM loaded: ${this.total} pairs from ${files.length} files`);
  }

  lookupExact(storyKey: string, row: ExactRow): TMEntry | undefined {
    const info = classifyStory(storyKey);
    if (storyPolicy(info.type).prefill !== "exact-row") return undefined;
    const key = exactRowKey(info.type, row);
    const candidates = this.exact.get(key);
    if (!candidates) return undefined;
    const all = Array.from(candidates.values());
    const human = all.filter((entry) => entry.human);
    const preferred = human.length > 0 ? human : all;
    // 人工优先；没有人工时才使用机翻。同一优先级有多个译法时安全地不复用，
    // 避免在没有人工确认的情况下把任一候选静默扩散。
    if (preferred.length !== 1) {
      log.warn(`精确复用存在多个同级译法，跳过：${info.type} / ${row.name || "（空说话人）"} / ${row.text}`);
      return undefined;
    }
    return preferred[0];
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
    // 本轮机翻只供后续分批/分段作上下文，绝不进入精确复用索引。
    this.total++;
    pushEntry(this.stories, full.story, full);
    if (full.name) pushEntry(this.chars, full.name, full);
  }

  /** 参考策略入口 */
  examples(storyKey: string, max = maxRefLines()): TMEntry[] {
    const info = classifyStory(storyKey);
    switch (storyPolicy(info.type).context) {
      case "sequential":
        // event 五段之间靠这个衔接，截断会让后段看不全前段——不设上限
        return this.sequentialExamples(info, Number.MAX_SAFE_INTEGER);
      default:
        // summary（dear）靠滚动摘要承载历史，不再重复注入上一话全文；
        // group-merge / none 本来就不注入 REF。
        return [];
    }
  }

  /** 生成注入提示词的参考块；REF| 前缀使其即使被模型回显也不会被解析成译文 */
  referenceBlock(storyKey: string): string {
    const info = classifyStory(storyKey);
    if (storyPolicy(info.type).context !== "sequential") return "";
    const ex = this.examples(storyKey);
    if (ex.length === 0) return "";
    const header =
      "以下是同一剧情此前段落的翻译，按剧情顺序排列，请保持剧情衔接、人名和术语的一致。";
    const lines = ex.map((e, i) => `REF|${i}|${e.name}|${e.text}|${e.trans}`).join("\n");
    return `${header}\n这些行只是参考，不要翻译或输出它们。\n\n${lines}`;
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
