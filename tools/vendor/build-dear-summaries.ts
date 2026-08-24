/**
 * 从本仓 csv_data 与工作仓人工层重建 Dear 滚动摘要。
 *
 * 选源优先级：proofread_csv > translated_csv > csv_data > ai_csv（需 --include-ai）。
 * 同一话的 -01/-02 分段先按文件名合并；输入哈希变化时从最早受影响检查点重建。
 * 任何缺话、跳话、摘要回退或无 SUMMARY 输出都会失败关闭，绝不写入残链。
 *
 * 从 GakumasPreTranslation 目录在 PowerShell 运行：
 *   $env:TM_DIR = '..\csv_data'
 *   $env:WORK_REPO_DIR = '..\gakumas-translation-work'
 *   $env:DEAR_SUMMARY_FILE = '..\tools\vendor\dear-summaries.json'
 *   [string[]]$arguments = @('ts-node', 'src\build-dear-summaries.ts', '--chars=atbm,hski')
 *   & npx @arguments
 */
import { createHash } from "crypto";
import fs from "fs-extra";
import path from "path";
import log from "loglevel";
import Papa from "papaparse";
import { dearSummaryPrompt } from "./prompts";
import { chat } from "./translate";
import { getLLMConfig, setupLog } from "./setup-env";
import {
  DearSummary,
  DearSummaryCheckpoint,
  glossaryBlock,
  isHumanTranslator,
  loadDearSummaries,
  saveDearSummary,
} from "./tm";

const MAX_LINES_PER_CHUNK = 250;
const NAME_RE = /^adv_dear_([a-z0-9]+)_(\d+)(?:[-_]\d+)?$/i;

interface SelectedCsv {
  key: string;
  file: string;
  source: string;
  human: boolean;
  priority: number;
}
interface EpisodePart {
  key: string;
  source: string;
  human: boolean;
  lines: string[];
}

interface Episode {
  episode: number;
  human: boolean;
  parts: EpisodePart[];
  lines: string[];
}

interface EpisodeChunk {
  episodes: Episode[];
  from: number;
  through: number;
  inputHash: string;
}

function allCsvFiles(root: string): string[] {
  if (!root || !fs.existsSync(root)) return [];
  const out: string[] = [];
  const visit = (dir: string) => {
    for (const name of fs.readdirSync(dir).sort()) {
      const file = path.join(dir, name);
      const stat = fs.statSync(file);
      if (stat.isDirectory()) visit(file);
      else if (name.toLowerCase().endsWith(".csv")) out.push(file);
    }
  };
  visit(root);
  return out;
}

function canonicalKey(root: string, file: string, flat: boolean): string {
  if (flat) return path.basename(file, ".csv");
  return path
    .relative(root, file)
    .replace(/\.csv$/i, "")
    .split(path.sep)
    .join("_");
}

function csvIsComplete(file: string): boolean {
  const rows = Papa.parse(fs.readFileSync(file, "utf-8"), { header: true }).data as any[];
  const dialogue = rows.filter((row) => row && row.text);
  return dialogue.length > 0 && dialogue.every((row) => Boolean(row.trans));
}

function addLayer(
  selected: Map<string, SelectedCsv>,
  root: string,
  source: string,
  priority: number,
  human: boolean | undefined,
  flat: boolean,
): void {
  for (const file of allCsvFiles(root)) {
    const key = canonicalKey(root, file, flat);
    if (!NAME_RE.test(key)) continue;
    if (priority >= 30 && !csvIsComplete(file)) {
      log.warn(`跳过尚未完成的人工 Dear CSV: ${file}`);
      continue;
    }
    let isHuman = human;
    if (isHuman === undefined) {
      const rows = Papa.parse(fs.readFileSync(file, "utf-8"), { header: true }).data as any[];
      const translator = rows.find((row) => row && row.id === "译者")?.name || "";
      isHuman = isHumanTranslator(translator);
    }
    const prev = selected.get(key);
    if (!prev || priority > prev.priority) {
      selected.set(key, { key, file, source, human: Boolean(isHuman), priority });
    }
  }
}

function loadPart(item: SelectedCsv): EpisodePart | undefined {
  const rows = Papa.parse(fs.readFileSync(item.file, "utf-8"), { header: true }).data as any[];
  const lines = rows
    .filter((row) => row && row.text)
    .map((row) => `${row.name || ""}|${row.text}|${row.trans || ""}`);
  if (lines.length === 0) return undefined;
  return { key: item.key, source: item.source, human: item.human, lines };
}

export function loadEpisodes(
  localDir: string,
  workRepoDir: string | undefined,
  includeAi = false,
): Map<string, Episode[]> {
  const selected = new Map<string, SelectedCsv>();
  if (workRepoDir && includeAi) {
    addLayer(selected, path.join(workRepoDir, "ai_csv"), "ai_csv", 10, false, false);
  }
  addLayer(selected, localDir, "csv_data", 20, undefined, true);
  if (workRepoDir) {
    addLayer(selected, path.join(workRepoDir, "translated_csv"), "translated_csv", 30, true, false);
    addLayer(selected, path.join(workRepoDir, "proofread_csv"), "proofread_csv", 40, true, false);
  }

  const grouped = new Map<string, Map<number, EpisodePart[]>>();
  for (const item of Array.from(selected.values()).sort((a, b) => a.key.localeCompare(b.key))) {
    const match = NAME_RE.exec(item.key);
    if (!match) continue;
    const part = loadPart(item);
    if (!part) continue;
    const character = match[1];
    const episode = parseInt(match[2], 10);
    let byEpisode = grouped.get(character);
    if (!byEpisode) {
      byEpisode = new Map<number, EpisodePart[]>();
      grouped.set(character, byEpisode);
    }
    const parts = byEpisode.get(episode) || [];
    parts.push(part);
    byEpisode.set(episode, parts);
  }

  const result = new Map<string, Episode[]>();
  for (const [character, byEpisode] of Array.from(grouped.entries())) {
    const episodes = Array.from(byEpisode.entries())
      .sort(([a], [b]) => a - b)
      .map(([episode, parts]) => {
        parts.sort((a, b) => a.key.localeCompare(b.key));
        return {
          episode,
          human: parts.every((part) => part.human),
          parts,
          lines: parts.flatMap((part) => part.lines),
        };
      });
    validateContinuity(character, episodes);
    result.set(character, episodes);
  }
  return result;
}

function validateContinuity(character: string, episodes: Episode[]): void {
  if (episodes.length === 0) return;
  if (episodes[0].episode !== 0 && episodes[0].episode !== 1) {
    throw new Error(`${character}: Dear 输入从第 ${episodes[0].episode} 话开始，缺少链首`);
  }
  for (let i = 1; i < episodes.length; i++) {
    if (episodes[i].episode !== episodes[i - 1].episode + 1) {
      throw new Error(
        `${character}: Dear 输入不连续，第 ${episodes[i - 1].episode} 话后直接出现第 ${episodes[i].episode} 话`,
      );
    }
  }
}

function hashChunk(episodes: Episode[]): string {
  const stable = episodes.map((episode) => ({
    episode: episode.episode,
    parts: episode.parts.map((part) => ({
      key: part.key,
      source: part.source,
      human: part.human,
      lines: part.lines,
    })),
  }));
  return createHash("sha256").update(JSON.stringify(stable)).digest("hex");
}

/** 按行数切块，但一话及其所有分段永远不会被拆开。 */
function chunk(episodes: Episode[]): EpisodeChunk[] {
  const groups: Episode[][] = [];
  let current: Episode[] = [];
  let lines = 0;
  for (const episode of episodes) {
    if (current.length > 0 && lines + episode.lines.length > MAX_LINES_PER_CHUNK) {
      groups.push(current);
      current = [];
      lines = 0;
    }
    current.push(episode);
    lines += episode.lines.length;
  }
  if (current.length > 0) groups.push(current);
  return groups.map((group) => ({
    episodes: group,
    from: group[0].episode,
    through: group[group.length - 1].episode,
    inputHash: hashChunk(group),
  }));
}

function buildPrompt(prev: string, prevFixed: Record<string, string>, block: EpisodeChunk): string {
  const body = block.episodes
    .map((episode) => {
      const source = Array.from(new Set(episode.parts.map((part) => part.source))).join("+");
      return (
        `【第 ${episode.episode} 话；来源 ${source}${episode.human ? "" : "；含机翻，仅供参考"}】\n` +
        episode.lines.join("\n")
      );
    })
    .join("\n\n");
  const fixedText = Object.entries(prevFixed)
    .map(([jp, zh]) => `${jp}|${zh}`)
    .join("\n");
  return (
    "发生了什么（情节、关系变化）以日文原文为准。\n" +
    "但专有名词、人名、称呼、作品名一律沿用中文译文列里已有的译法——那是定稿，\n" +
    "摘要里不得出现日文写法（例：该写「启明星」而不是「一番星」）。\n" +
    "只有标注「含机翻，仅供参考」的话，其中文用词不可信；\n" +
    "这类话里的专有名词改用术语表，或其它话里已确立的译法。\n\n" +
    (prev ? `此前摘要：\n${prev}\n\n` : "") +
    (fixedText ? `此前已固定的称呼或自称（日文|中文）：\n${fixedText}\n\n` : "") +
    `请并入第 ${block.from}~${block.through} 话（说话人|原文|译文）：\n${body}`
  );
}

function parseReply(
  raw: string,
): { summary: string; segment: string; fixed: Record<string, string> } {
  let summary = "";
  let segment = "";
  const fixed: Record<string, string> = {};
  for (const line of raw.split("\n")) {
    const parts = line.split("|");
    if (parts[0].trim() === "SUMMARY" && parts.length >= 2) {
      summary = parts.slice(1).join("|").trim();
    } else if (parts[0].trim() === "SEGMENT" && parts.length >= 2) {
      segment = parts.slice(1).join("|").trim();
    } else if (parts[0].trim() === "FIXED" && parts.length >= 3) {
      const key = parts[1].trim();
      const value = parts.slice(2).join("|").trim();
      if (key && value) fixed[key] = value;
    }
  }
  return { summary, segment, fixed };
}

function checkpointMatches(checkpoint: DearSummaryCheckpoint, block: EpisodeChunk): boolean {
  return checkpoint.from_episode === block.from &&
    checkpoint.through_episode === block.through &&
    checkpoint.input_hash === block.inputHash;
}

function requestedCharacters(args: string[]): string[] {
  const inline = args.find((arg) => arg.startsWith("--chars="));
  const at = args.indexOf("--chars");
  const value = inline ? inline.slice(8) : at >= 0 ? args[at + 1] || "" : "";
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

async function rebuildCharacter(
  character: string,
  episodes: Episode[],
  existing: DearSummary | undefined,
  reset: boolean,
  allowRegression: boolean,
): Promise<void> {
  const blocks = chunk(episodes);
  const maxEpisode = episodes[episodes.length - 1].episode;
  const oldThrough = existing?.through_episode ?? -1;
  if (!allowRegression && oldThrough > maxEpisode) {
    throw new Error(
      `${character}: 输入最高第 ${maxEpisode} 话，低于现有摘要第 ${oldThrough} 话；拒绝摘要回退`,
    );
  }

  const oldCheckpoints = reset ? [] : existing?.checkpoints || [];
  let matched = 0;
  while (
    matched < blocks.length &&
    matched < oldCheckpoints.length &&
    checkpointMatches(oldCheckpoints[matched], blocks[matched])
  ) {
    matched++;
  }
  if (!reset && matched === blocks.length && matched === oldCheckpoints.length && oldThrough === maxEpisode) {
    log.info(`${character}: 输入哈希未变化，摘要已覆盖到第 ${maxEpisode} 话`);
    return;
  }

  const checkpoints = oldCheckpoints.slice(0, matched);
  const baseline = checkpoints[checkpoints.length - 1];
  let summary = baseline?.summary || "";
  let fixed: Record<string, string> = { ...(baseline?.fixed || {}) };
  log.info(
    `${character}: 从第 ${blocks[matched]?.from ?? maxEpisode} 话重建` +
      `（${matched}/${blocks.length} 个检查点可复用）`,
  );

  const config = getLLMConfig();
  for (let index = matched; index < blocks.length; index++) {
    const block = blocks[index];
    // 以前这里传的是 []，摘要任务根本没见过术语表，
    // 所以会把日文专有名词原样写进摘要，再注入翻译时
    // 就和术语表自相矛盾。
    const blockLines = block.episodes.flatMap((episode) => episode.lines);
    const reply = parseReply(
      await chat(
        buildPrompt(summary, fixed, block),
        config,
        [glossaryBlock(blockLines)].filter(Boolean),
        dearSummaryPrompt,
      ),
    );
    if (!reply.summary) {
      throw new Error(`${character} 第 ${block.from}~${block.through} 话未返回 SUMMARY`);
    }
    // SEGMENT 丢了不致命——摘要链才是主体，不值得为它作废一整轮重建。
    if (!reply.segment) {
      log.warn(`${character} 第 ${block.from}~${block.through} 话未返回 SEGMENT，剧情线缺这一段`);
    }
    summary = reply.summary;
    fixed = { ...fixed, ...reply.fixed };
    checkpoints.push({
      from_episode: block.from,
      through_episode: block.through,
      input_hash: block.inputHash,
      summary,
      segment: reply.segment || undefined,
      fixed: { ...fixed },
    });

    // 重建途中不得把磁盘上的成熟摘要暂时写回更早话；追平后才落检查点。
    if (block.through >= oldThrough || oldThrough < 0) {
      saveDearSummary(character, {
        through_episode: block.through,
        summary,
        fixed,
        checkpoints: checkpoints.map((checkpoint) => ({ ...checkpoint })),
      });
    }
    log.info(
      `  ${character} -> 第 ${block.through} 话（摘要 ${summary.length} 字，` +
        `分段 ${reply.segment.length} 字）`,
    );
  }
}

async function main(): Promise<void> {
  setupLog();
  const args = process.argv.slice(2);
  const only = requestedCharacters(args);
  const reset = args.includes("--reset");
  const includeAi = args.includes("--include-ai");
  const allowRegression = args.includes("--allow-regression");
  const localDir = path.resolve(process.env.TM_DIR || "../csv_data");
  const workRepoDir = process.env.WORK_REPO_DIR
    ? path.resolve(process.env.WORK_REPO_DIR)
    : undefined;
  const byChar = loadEpisodes(localDir, workRepoDir, includeAi);
  const all = loadDearSummaries();
  const characters = Array.from(byChar.keys())
    .filter((character) => only.length === 0 || only.includes(character))
    .sort();

  log.info(`共 ${characters.length} 个角色；人工层优先，${includeAi ? "允许" : "不允许"} ai_csv 兜底`);
  for (const character of characters) {
    await rebuildCharacter(character, byChar.get(character)!, all[character], reset, allowRegression);
  }
  log.info("Dear 摘要同步完成");
}

if (require.main === module) {
  main().catch((error) => {
    log.error(error);
    process.exit(1);
  });
}
