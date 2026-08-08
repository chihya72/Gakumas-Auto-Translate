import log from "loglevel";
import axios from "axios";
import path from "path";
import { chinesePrompt } from "./prompts";
import {
  CsvTextInfo,
  CsvDataLine,
  toCsvText,
  jsonTextToCsvText,
  extractInfoFromCsvText,
} from "./csv";
import {
  TranslationMemory,
  getSharedTM,
  storyKeyFromName,
  classifyStory,
  STORY_MODES,
  characterCardBlock,
  glossaryBlock,
  summaryBlock,
  loadDearSummaries,
  saveDearSummary,
} from "./tm";

interface Dialogue {
  name: string;
  text: string;
}

export interface LLMConfig {
  apiKey: string;
  baseURL: string;
  model: string;
  max_tokens: number;
}

function splitCsvInfo(csvTextInfo: CsvTextInfo, batchNum: number) {
  const batchSize = Math.ceil(csvTextInfo.data.length / batchNum);
  const rtn: CsvTextInfo[] = [];
  for (let index = 0; index < batchNum; index++) {
    const startIndex = index * batchSize;
    const endIndex = (index + 1) * batchSize;
    rtn.push({
      data: csvTextInfo.data.slice(startIndex, Math.min(endIndex, csvTextInfo.data.length)),
      translator: csvTextInfo.translator,
      jsonUrl: csvTextInfo.jsonUrl,
    });
  }
  return rtn;
}

function mergeCsvInfo(csvTextInfos: CsvTextInfo[]) {
  const rtn: CsvTextInfo = {
    data: [],
    translator: csvTextInfos[0].translator,
    jsonUrl: csvTextInfos[0].jsonUrl,
  };
  for (let index = 0; index < csvTextInfos.length; index++) {
    const csvTextInfo = csvTextInfos[index];
    rtn.data.push(...csvTextInfo.data);
  }
  return rtn;
}

// ---------- 翻译记忆（TM）接入 ----------

function getTMDir(): string | undefined {
  const env = process.env.TM_DIR;
  if (env === "") return undefined;
  if (env) return path.resolve(env);
  // 默认相对 GakumasPreTranslation 的上级目录：仓库根/csv_data
  return path.resolve(process.cwd(), "../csv_data");
}

function getTM(): TranslationMemory | undefined {
  const tm = getSharedTM();
  if (!tm.isLoaded) {
    tm.loadDir(getTMDir());
  }
  return tm.size > 0 ? tm : undefined;
}

function prefillMode(): string {
  return (process.env.TM_PREFILL || "human").toLowerCase();
}

/**
 * 单次请求的行数上限。cidol/csprt 在管线侧把同组 01~03 合并成一个 CSV，
 * 这里必须放得下整组，否则又被切开就等于白合并。
 * 注意同步调高 MAX_TOKENS——250 行输出约需 10000+ token。
 */
function maxLinesPerRequest(): number {
  const v = parseInt(process.env.MAX_LINES_PER_REQUEST || "", 10);
  return Number.isFinite(v) && v > 0 ? v : 250;
}

// ---------- event 临时术语表 ----------

/**
 * 本活动临时术语表。活动剧情专有名词密集（活动名、场地、活动内设定），
 * 且在五段里反复出现——先花一次调用抽词，换五段的术语一致，划算。
 * 只在内存里活到本次运行结束，不落盘、不进版本控制。
 */
let extraGlossary: Record<string, string> | undefined;
const eventGlossaryCache = new Map<string, Record<string, string>>();

async function buildEventGlossary(
  group: string,
  texts: string[],
  config: LLMConfig,
): Promise<Record<string, string>> {
  const cached = eventGlossaryCache.get(group);
  if (cached) return cached;
  const prompt =
    "以下是一个偶像游戏活动剧情的全部日文台词。请找出其中的专有名词" +
    "（活动名、场地名、活动内设定、限定称谓等），给出简体中文译法。\n" +
    "每行输出一条，格式 TERM|[日文]|[中文]。只输出这些行，不要任何说明文字。\n" +
    "普通词汇、人名、常见词不要输出。最多 30 条。\n\n" +
    texts.join("\n");
  const result: Record<string, string> = {};
  try {
    const raw = await chat(prompt, config);
    for (const line of raw.split("\n")) {
      const parts = line.split("|");
      if (parts.length === 3 && parts[0].trim() === "TERM") {
        const jp = parts[1].trim();
        const zh = parts[2].trim();
        if (jp && zh) result[jp] = zh;
      }
    }
    log.info(`event 抽词: ${group} 得到 ${Object.keys(result).length} 条`);
  } catch (e) {
    // 抽词失败不该拖垮翻译——退回只用全局术语表
    log.warn(`event 抽词失败，跳过临时术语表: ${e.message}`);
  }
  eventGlossaryCache.set(group, result);
  return result;
}

// ---------- dear 滚动摘要 ----------

/**
 * 翻完一话就更新该角色的摘要，供下一话使用。
 * 摘要只记对翻译有影响的东西——关系阶段、称呼变化、已建立的设定；
 * 写成剧情流水账就等于把 REF 的毛病用更贵的方式重犯一遍。
 */
async function updateDearSummary(
  info: { character: string; episode: number },
  data: CsvDataLine[],
  config: LLMConfig,
): Promise<void> {
  if (!process.env.DEAR_SUMMARY_FILE || !info.character || info.episode < 0) return;
  const prev = loadDearSummaries()[info.character];
  // 单话重跑不能把摘要打回更早的进度——那会静默丢掉中间几话的进展，
  // 而且下次翻新话时注入的是一份残缺摘要，不报错也查不出来。
  // 要整段重建就先清掉该角色条目，让链条从头长起来：重建必须是显式的。
  const prevEp = prev?.through_episode ?? -1;
  if (prevEp >= info.episode) {
    log.warn(
      `dear 摘要已覆盖到第 ${prevEp} 话，跳过第 ${info.episode} 话的回写。` +
        `如需重建请先清空 ${info.character} 的条目。`,
    );
    return;
  }
  const body = data
    .filter((r) => r.trans)
    .map((r) => `${r.name}|${r.text}|${r.trans}`)
    .join("\n");
  const prompt =
    "你在维护一份偶像游戏好感度剧情的翻译辅助摘要，供翻译下一话时参考。\n" +
    "只记录对翻译有影响的内容：与制作人的关系走到哪个阶段、称呼或自称的变化及其触发点、" +
    "已建立的重要设定。不要写剧情流水账，不要写人物性格评价。摘要控制在 400 字以内。\n\n" +
    "输出格式（只输出这些行，不要任何说明文字）：\n" +
    "SUMMARY|<更新后的摘要全文，单行，不要换行>\n" +
    "FIXED|<项目名>|<已固定的译法>   （可有多行，没有则不输出）\n\n" +
    (prev?.summary ? `此前的摘要（覆盖到第 ${prev.through_episode} 话）：\n${prev.summary}\n\n` : "") +
    `第 ${info.episode} 话的原文与译文（格式 说话人|原文|译文）：\n${body}`;
  try {
    const raw = await chat(prompt, config);
    let summary = "";
    const fixed: Record<string, string> = {};
    for (const line of raw.split("\n")) {
      const parts = line.split("|");
      if (parts[0].trim() === "SUMMARY" && parts.length >= 2) {
        summary = parts.slice(1).join("|").trim();
      } else if (parts[0].trim() === "FIXED" && parts.length >= 3) {
        fixed[parts[1].trim()] = parts.slice(2).join("|").trim();
      }
    }
    if (!summary) {
      log.warn(`dear 摘要更新未返回 SUMMARY 行，保留旧摘要: ${info.character}`);
      return;
    }
    saveDearSummary(info.character, {
      through_episode: info.episode,
      summary,
      fixed: Object.keys(fixed).length ? fixed : prev?.fixed,
    });
  } catch (e) {
    // 摘要更新失败不该让整篇翻译白跑——译文已经拿到了
    log.warn(`dear 摘要更新失败，保留旧摘要: ${e.message}`);
  }
}

// ---------- 翻译 ----------

export async function translateCsvString(
  csvText: string,
  config: LLMConfig,
  maxBatchSize: number = maxLinesPerRequest(),
): Promise<string> {
  const csvTextInfo = extractInfoFromCsvText(csvText);
  const tm = getTM();

  const info = classifyStory(csvTextInfo.jsonUrl || "");
  extraGlossary =
    STORY_MODES[info.type] === "sequential"
      ? await buildEventGlossary(
          info.group,
          csvTextInfo.data.map((r) => r.text),
          config,
        )
      : undefined;
  const batchNum = Math.ceil(csvTextInfo.data.length / maxBatchSize);
  log.info(`Splitting csvTextInfo into ${batchNum} batches`);
  const csvTextInfos = splitCsvInfo(csvTextInfo, batchNum);
  if (tm) {
    log.info("TM enabled: 同一文件分批顺序翻译，前一批译文自动作为后一批前文");
    for (let i = 0; i < csvTextInfos.length; i++) {
      await translateCsvTextInfo(csvTextInfos[i], config, 2, tm, true);
    }
  } else {
    await Promise.all(csvTextInfos.map((info) => translateCsvTextInfo(info, config, 2)));
  }
  const merged = mergeCsvInfo(csvTextInfos);
  if (STORY_MODES[info.type] === "summary") {
    await updateDearSummary(info, merged.data, config);
  }
  return toCsvText(merged);
}

export async function translateJsonDataToCsvString(
  data: any[],
  jsonPath: string,
  config: LLMConfig,
): Promise<string> {
  return await translateCsvString(jsonTextToCsvText(data, jsonPath), config);
}

// will modify csvTextInfo
async function translateCsvTextInfo(
  csvTextInfo: CsvTextInfo,
  config: LLMConfig,
  leftRetry = 0,
  tm?: TranslationMemory,
  selfFeed = false,
) {
  const data = csvTextInfo.data;
  const pending: CsvDataLine[] = [];

  if (tm) {
    // 精确命中的行直接复用历史译文，其余交给 LLM。
    // 只复用人工译文：机翻一旦错译进了库，"复用"不会再经过模型，
    // 错误会被无差别复制到所有匹配文件上并永久固化。
    const reuseAll = prefillMode() === "all";
    for (const row of data) {
      const hit = tm.lookup(row.text);
      if (hit && (reuseAll || hit.human)) {
        row.trans = hit.trans;
      } else {
        pending.push(row);
      }
    }
  } else {
    pending.push(...data);
  }

  if (pending.length === 0) {
    csvTextInfo.translator = config.model;
    return;
  }

  const names = new Set<string>();
  for (const row of pending) if (row.name) names.add(row.name);
  const story = storyKeyFromName(csvTextInfo.jsonUrl || "");

  // 上下文块顺序与提示词里声明的一致：术语表 → 角色卡 → 剧情摘要 → 参考行
  const context = [
    glossaryBlock(pending.map((r) => r.text), extraGlossary),
    characterCardBlock(names),
    summaryBlock(story),
    tm ? tm.referenceBlock(story) : "",
  ].filter(Boolean);

  const userInput = DialogueListDeser.serialize(pending);
  const gptOutput = await chat(userInput, config, context);
  const translated = DialogueListDeser.deserialize(gptOutput, pending.length);

  const missing: number[] = [];
  for (let index = 0; index < pending.length; index++) {
    const dialogue = translated.get(index);
    if (dialogue) pending[index].trans = dialogue.text;
    else missing.push(index);
  }

  if (missing.length > 0) {
    const shown = missing.slice(0, 10).join(", ");
    log.error(
      `缺 ${missing.length}/${pending.length} 行译文，行号: ${shown}` +
        (missing.length > 10 ? " …" : ""),
    );
    if (leftRetry > 0) {
      log.info("Retrying...");
      return await translateCsvTextInfo(csvTextInfo, config, leftRetry - 1, tm, selfFeed);
    }
    throw new Error(`缺 ${missing.length} 行译文，重试已用尽`);
  }

  // 自我喂食：本批译文加入记忆，成为后续批次的前文
  if (tm && selfFeed) {
    for (const row of pending) {
      if (row.trans) {
        tm.add({
          text: row.text,
          trans: row.trans,
          name: row.name || "",
          story,
        });
      }
    }
  }

  csvTextInfo.translator = config.model;
}

export const DialogueListDeser = {
  serialize(dialogues: Dialogue[]): string {
    let rtn = "";
    for (let index = 0; index < dialogues.length; index++) {
      const dialogue = dialogues[index];
      rtn += `${index}|${dialogue.name}|${dialogue.text.replaceAll("\\n", "<br>")}\n`;
    }
    return rtn;
  },
  /**
   * 按【模型自己带回来的行号】归位，而不是按输出文本的第几行。
   *
   * 用位置归位时，模型少写一行就会让后面全部错位；如果它同时多写一行，
   * 总数正好对上，整篇错位还不报错——那是静默的错译。用行号归位后，
   * 第 47 行译文只会落到第 47 行原文上，模型的输出顺序不再有任何影响。
   *
   * 同一行号出现多次取最后一次：模型偶尔会先回显输入再给译文。
   */
  deserialize(gptOutput: string, expected: number): Map<number, Dialogue> {
    const rtn = new Map<number, Dialogue>();
    for (const line of gptOutput.split("\n")) {
      const parts = line.split("|");
      if (parts.length < 3) continue;
      const index = Number(parts[0].trim());
      if (!Number.isInteger(index) || index < 0 || index >= expected) continue;
      rtn.set(index, {
        name: parts[1],
        // 译文里出现 | 时会被切成 4 段以上，拼回去而不是整行丢弃
        text: parts.slice(2).join("|").replaceAll("<br>", "\\n"),
      });
    }
    return rtn;
  },
};

export async function chat(
  userInput: string,
  { apiKey, baseURL, model, max_tokens }: LLMConfig,
  context: string[] = [],
) {
  try {
    const openai = axios.create({
      baseURL,
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${apiKey}`,
      },
    });
    const messages: any[] = [{ role: "system", content: chinesePrompt }];
    for (const block of context) {
      messages.push({ role: "user", content: block });
    }
    messages.push({ role: "user", content: userInput });
    log.info(`Sending request to ${model} API, please wait...`);
    const response = await openai.post(
      "/v1/chat/completions",
      {
        model,
        messages,
        temperature: 0.7,
        max_tokens,
      },
      {
        timeout: 180000,
      },
    );

    const generatedText = response.data.choices[0].message.content;
    const tokenConsumed = response.data.usage.total_tokens;
    log.debug(`Generated Text: ${generatedText}`);
    log.debug(`Consumed token: ${tokenConsumed}`);
    return generatedText;
  } catch (error) {
    log.error(`Error: ${error.message}`);
    if (error.response && error.response.data && error.response.data.error) {
      log.error(`Error: ${error.response.data.error.message}`);
      throw new Error(error.response.data.error.message);
    }
    throw error;
  }
}
