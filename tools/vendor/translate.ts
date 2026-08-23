import log from "loglevel";
import axios from "axios";
import path from "path";
import { chinesePrompt, dearSummaryPrompt, eventGlossaryPrompt } from "./prompts";
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
  storyPolicy,
  characterCardBlock,
  characterMappings,
  glossaryBlock,
  activeGlossary,
  activeDearFixed,
  exactReuseAllowed,
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

export class FatalTranslationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "FatalTranslationError";
    Object.setPrototypeOf(this, FatalTranslationError.prototype);
  }
}

export class FatalApiError extends FatalTranslationError {
  constructor(message: string) {
    super(message);
    this.name = "FatalApiError";
    Object.setPrototypeOf(this, FatalApiError.prototype);
  }
}

function isDeepSeekV4(model: string): boolean {
  return model.toLowerCase().includes("deepseek-v4");
}

export function validateMaxTokens(model: string, maxTokens: number): void {
  if (!Number.isInteger(maxTokens) || maxTokens <= 0) {
    throw new FatalTranslationError(`MAX_TOKENS 必须是正整数，当前值: ${maxTokens}`);
  }
  if (model.toLowerCase().includes("deepseek-v4-pro") && maxTokens < 65536) {
    throw new FatalTranslationError(
      `MAX_TOKENS=${maxTokens} 过小；DeepSeek V4 Pro thinking 的推理与最终译文` +
        "共用输出预算，本管线要求至少 65536。",
    );
  }
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
    const raw = await chat(prompt, config, [], eventGlossaryPrompt);
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
  if (
    !process.env.DEAR_SUMMARY_FILE ||
    process.env.DEAR_SUMMARY_WRITE !== "1" ||
    !info.character ||
    info.episode < 0
  ) return;
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
  const firstEpisode = info.episode === 0 || info.episode === 1;
  if ((prev && prevEp !== info.episode - 1) || (!prev && !firstEpisode)) {
    log.warn(
      `dear 摘要链不连续：现有覆盖到第 ${prevEp} 话，当前是第 ${info.episode} 话；` +
        "拒绝跳话更新，请用历史重建脚本补齐中间话。",
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
    (Object.keys(prev?.fixed || {}).length
      ? `此前已固定的称呼：\n${Object.entries(prev!.fixed!)
          .map(([jp, zh]) => `${jp}|${zh}`)
          .join("\n")}\n\n`
      : "") +
    `第 ${info.episode} 话的原文与译文（格式 说话人|原文|译文）：\n${body}`;
  try {
    const raw = await chat(prompt, config, [], dearSummaryPrompt);
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
      fixed: { ...(prev?.fixed || {}), ...fixed },
      checkpoints: prev?.checkpoints,
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
    storyPolicy(info.type).context === "sequential"
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
  if (storyPolicy(info.type).context === "summary") {
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
  const story = storyKeyFromName(csvTextInfo.jsonUrl || "");
  const exactTerms = activeGlossary(data.map((r) => r.text), extraGlossary);

  if (tm) {
    // 只有策略白名单内的 pstory/pevent 可以精确复用。命中键包含剧情类型、
    // 行类型、说话人和完整原文；人工优先于机翻，同级歧义由 TM 判为未命中。
    for (const row of data) {
      if (row.trans) continue;
      const hit = tm.lookupExact(story, row);
      const explicitConstraints = {
        ...characterMappings(row.name || ""),
        ...exactTerms,
      };
      if (hit && exactReuseAllowed(row.text, hit.trans, explicitConstraints)) {
        row.trans = hit.trans;
      } else {
        pending.push(row);
      }
    }
  } else {
    for (const row of data) {
      if (!row.trans) pending.push(row);
    }
  }

  if (pending.length === 0) {
    csvTextInfo.translator = config.model;
    return;
  }

  const names = new Set<string>();
  for (const row of pending) if (row.name) names.add(row.name);
  const terms = activeGlossary(pending.map((r) => r.text), extraGlossary);
  const termKeys = new Set(Object.keys(terms));
  const fixed = activeDearFixed(story, termKeys);
  const cardOverrides = new Set(Object.keys(terms).concat(Object.keys(fixed)));

  // 约束优先级：术语表 > Dear 动态固定称呼 > 角色卡 > REF。
  // summaryBlock 会先删除与术语表同键的低优先级 FIXED，避免把冲突交给模型猜。
  const reference = tm ? tm.referenceBlock(story) : "";
  const constraints = [
    glossaryBlock(pending.map((r) => r.text), extraGlossary),
    summaryBlock(story, termKeys, fixed),
    characterCardBlock(names, cardOverrides),
  ];
  // event 顺序翻译时，参考行是同组各段之间唯一「只在末尾追加」的块（第 3 段的
  // 参考行 = 第 2 段的 + 第 2 段本身）。放到最前面，后面几段的请求就共享一段
  // 很长的相同前缀，能吃到 API 的上下文缓存折扣。而术语表/角色卡是每段都
  // 不一样的（只注入本段命中的词与出场角色），放前面等于开头第一句就分叉。
  // 其余类型要么没有参考行，要么一个文件只发一次请求，顺序无所谓，保持原样。
  const referenceFirst =
    storyPolicy(classifyStory(story).type).context === "sequential";
  const context = (
    referenceFirst ? [reference, ...constraints] : [...constraints, reference]
  ).filter(Boolean);

  const userInput = DialogueListDeser.serialize(pending);
  const gptOutput = await chat(userInput, config, context);
  const translated = DialogueListDeser.deserialize(gptOutput, pending.length);

  // 一个有效行号都没有时，原样重试只会再次消耗同一份输入和思考 token。
  if (translated.size === 0) {
    throw new Error(
      `模型响应未包含任何有效译文行（0/${pending.length}），已停止原样重试以避免重复扣费`,
    );
  }

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
      if (tm && selfFeed) {
        // 部分成功的译文立刻作为同文件前文，补翻缺失行时也能看到已有上下文。
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
      log.info(`仅重试缺失的 ${missing.length} 行；已成功的 ${translated.size} 行不会重发`);
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
      const text = parts.slice(2).join("|").replaceAll("<br>", "\\n");
      if (!text.trim()) continue;
      rtn.set(index, {
        name: parts[1],
        // 译文里出现 | 时会被切成 4 段以上，拼回去而不是整行丢弃
        text,
      });
    }
    return rtn;
  },
};

export function buildChatMessages(
  userInput: string,
  context: string[] = [],
  systemPrompt: string = chinesePrompt,
): Array<{ role: string; content: string }> {
  const messages = [{ role: "system", content: systemPrompt }];
  for (const block of context) messages.push({ role: "user", content: block });
  messages.push({ role: "user", content: userInput });
  return messages;
}

export async function chat(
  userInput: string,
  { apiKey, baseURL, model, max_tokens }: LLMConfig,
  context: string[] = [],
  systemPrompt: string = chinesePrompt,
) {
  try {
    validateMaxTokens(model, max_tokens);
    const openai = axios.create({
      baseURL,
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${apiKey}`,
      },
    });
    const messages = buildChatMessages(userInput, context, systemPrompt);
    const deepSeekV4 = isDeepSeekV4(model);
    const requestBody: any = {
      model,
      messages,
      max_tokens,
    };
    if (deepSeekV4) {
      // DeepSeek OpenAI 兼容接口的显式 thinking 开关；high 是普通请求默认强度。
      requestBody.thinking = { type: "enabled" };
      requestBody.reasoning_effort = "high";
    } else {
      requestBody.temperature = 0.7;
    }
    const configuredTimeout = parseInt(process.env.API_TIMEOUT_MS || "", 10);
    const timeout =
      Number.isFinite(configuredTimeout) && configuredTimeout > 0 ? configuredTimeout : 600000;
    log.info(
      `Sending request to ${model} API ` +
        `(thinking=${deepSeekV4 ? "enabled/high" : "provider-default"}, ` +
        `max_tokens=${max_tokens}, timeout=${Math.round(timeout / 1000)}s), please wait...`,
    );
    const response = await openai.post(
      "/v1/chat/completions",
      requestBody,
      {
        timeout,
      },
    );

    const choice = response.data?.choices?.[0];
    if (!choice) {
      throw new Error("API 响应缺少 choices[0]");
    }
    const generatedText = choice.message.content || "";
    const reasoningText = choice.message.reasoning_content || "";
    const usage = response.data.usage || {};
    const reasoningTokens = usage.completion_tokens_details?.reasoning_tokens ?? "unknown";
    const finishReason = choice.finish_reason || "unknown";
    log.info(
      `API response: finish_reason=${finishReason}, ` +
        `content_chars=${generatedText.length}, reasoning_chars=${reasoningText.length}, ` +
        `prompt_tokens=${usage.prompt_tokens ?? "unknown"}, ` +
        `completion_tokens=${usage.completion_tokens ?? "unknown"}, ` +
        `reasoning_tokens=${reasoningTokens}, total_tokens=${usage.total_tokens ?? "unknown"}`,
    );
    if (!generatedText.trim()) {
      const suffix = finishReason === "length" ? "（输出预算已耗尽）" : "";
      throw new Error(`API 最终译文 content 为空，finish_reason=${finishReason}${suffix}`);
    }
    if (finishReason === "length") {
      log.warn(
        "API 输出被 max_tokens 截断；将保留已返回的有效行，并且只重试缺失行。若没有有效行则立即停止。",
      );
    }
    log.debug(`Generated Text: ${generatedText}`);
    return generatedText;
  } catch (error) {
    const status = error.response?.status;
    const apiMessage = error.response?.data?.error?.message;
    const message = apiMessage || error.message || String(error);
    log.error(`API error${status ? ` HTTP ${status}` : ""}: ${message}`);
    if (error instanceof FatalTranslationError) {
      throw error;
    }
    // 认证、余额、请求参数等 4xx 不会靠换下一个文件自行恢复，必须终止整轮。
    if (status >= 400 && status < 500 && ![408, 409, 425, 429].includes(status)) {
      throw new FatalApiError(`API HTTP ${status}: ${message}`);
    }
    throw new Error(status ? `API HTTP ${status}: ${message}` : message);
  }
}
