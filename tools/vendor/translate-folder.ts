import fs from "fs-extra";
import { resolve, basename, join } from "path";
import log from "loglevel";
import {
  FatalTranslationError,
  LLMConfig,
  translateCsvString,
  translateJsonDataToCsvString,
} from "../src/translate";

// 连续这么多个文件失败就当全局故障（API 挂了、余额没了但没返回 4xx）停下来，
// 不然会把整批文件一个个试完、全标成「机翻异常」。
const MAX_CONSECUTIVE_FAILURES = 3;
import { getLLMConfig, setupLog, getRemoteEndpoint } from "../src/setup-env";
import { program } from "commander";
import axios from "axios";
import { walkSync } from "@nodelib/fs.walk";
import { extractInfoFromCsvText } from "../src/csv";

// 上游入口会吞掉单文件异常并继续翻译剩余文件。对余额、认证、输出预算等
// 全局故障，这会把一次错误放大成整批付费请求。本副本对 FatalTranslationError
// （4xx、配置错误）fail-fast；单文件错误（正文为空、解析不出行、缺行重试用尽）
// 只跳过这个文件——否则一个总让模型出错的文件永远排在队首，每轮都卡在它身上。
// 跳过的文件不产出，由管线按「没有输出」计入失败、重翻、标记。
async function translateFolder(
  config: LLMConfig,
  folder = "./tmp/untranslated",
  destFolder = "./tmp/translated",
  skipExisted = true,
  indexFile?: string,
) {
  const files = [];
  const entries = walkSync(folder);

  let indexFileContent: { [key: string]: string } = {};
  if (indexFile) {
    indexFileContent = fs.readJsonSync(indexFile);
    log.info("Found " + Object.keys(indexFileContent).length + " csv files in index file");
  }

  for (const entry of entries) {
    if (entry.name.endsWith(".csv")) files.push(entry);
  }
  // 补充篇 037-01 要排在主篇 037 之后（"-" 比 "." 小，直接比名字会反过来），
  // 否则补充篇先翻、把 dear 摘要链推到 37，主篇反而拿不到摘要。
  const sortKey = (name: string) => name.replace(/-(\d+)\.csv$/, ".csv-$1");
  files.sort((a, b) => sortKey(a.name).localeCompare(sortKey(b.name)));
  log.info("Found " + files.length + " csv files to translate");

  let consecutiveFailures = 0;
  for (const entry of files) {
    log.info("Translating " + entry.name);
    const filePath = entry.path;
    const csvString = await fs.promises.readFile(filePath, "utf-8");
    const csvInfo = extractInfoFromCsvText(csvString);

    if (indexFileContent[csvInfo.jsonUrl]) {
      log.debug(`Skipped ${csvInfo.jsonUrl} because of file already translated`);
      continue;
    }

    const destPath = resolve(destFolder, csvInfo.jsonUrl.replace(".txt", ".csv"));
    if (skipExisted && fs.existsSync(destPath)) {
      log.debug(`Skipped ${destPath} because of file existence`);
      continue;
    }

    try {
      const translatedCsvString = await translateCsvString(csvString, config);
      await fs.promises.writeFile(destPath, translatedCsvString, "utf-8");
      log.info(`Output to ${destPath}`);
      consecutiveFailures = 0;
    } catch (error) {
      if (error instanceof FatalTranslationError) {
        log.error(`failed to translate ${entry.path}; aborting remaining files`);
        throw error;
      }
      consecutiveFailures++;
      log.error(`failed to translate ${entry.path}; skipping this file: ${error.message}`);
      if (consecutiveFailures >= MAX_CONSECUTIVE_FAILURES) {
        log.error(`连续 ${consecutiveFailures} 个文件失败，疑似全局故障，停止本轮`);
        throw error;
      }
    }
  }
}

async function getJsonPathList(diffEndpoint: string) {
  const assetMapDiff = (await axios.get(diffEndpoint)).data;
  return Object.keys(assetMapDiff.added).filter((file) => file.startsWith("json/"));
}

async function translateRemoteDiff(
  config: LLMConfig,
  diffEndpoint: string,
  assetEndpoint: string,
  destFolder = "./tmp/translated",
  skipExisted = true,
) {
  const jsonPathList = await getJsonPathList(diffEndpoint);
  log.info("Found " + jsonPathList.length + " json files in latest diff to translate");

  for (const jsonPath of jsonPathList) {
    log.info("Translating " + jsonPath);
    const destPath = resolve(destFolder, basename(jsonPath).replaceAll(".json", ".csv"));
    if (skipExisted && fs.existsSync(destPath)) {
      log.debug(`Skipped ${destPath} because of file existence`);
      continue;
    }
    const jsonContent = (await axios.get(join(assetEndpoint, jsonPath))).data;
    const translatedCsvString = await translateJsonDataToCsvString(
      jsonContent,
      jsonPath.replace("json/", ""),
      config,
    );
    await fs.writeFile(destPath, translatedCsvString, "utf-8");
    log.info(`Output to ${destPath}`);
  }
}

async function main() {
  setupLog();
  program
    .requiredOption(
      "--type <translate-src-type>",
      "Type of the source file, can be folder, remote-diff",
      "folder",
    )
    .option(
      "--dir <dir>",
      "the source directory where the files are located, only activated when type is folder",
      "./tmp/untranslated",
    )
    .option(
      "--tag <tag>",
      "the version of the remote-diff, only activated when type is remote-diff",
      "-1",
    )
    .option("--overwrite", "whether to overwrite translation if a translated file already exists")
    .option("--indexfile <index-file>", "the index file used to ignore translated files", "./index.json")
    .option("--ignoreindex", "whether to ignore index files");
  await program.parseAsync(process.argv);
  const opts = program.opts();

  const config = getLLMConfig();
  if (opts.type === "folder") {
    log.info("Source File Directory:", opts.dir);
    log.info("overwrite files:", !!opts.overwrite);
    log.info("ignore index:", opts.ignoreindex);
    log.info("using index file:", opts.ignoreindex ? undefined : opts.indexfile);
    await translateFolder(
      config,
      opts.dir,
      opts.dest,
      !opts.overwrite,
      opts.ignoreindex ? undefined : opts.indexfile,
    );
  } else if (opts.type === "remote-diff") {
    const { diffEndpoint, assetEndpoint } = getRemoteEndpoint();
    log.info("Remote Diff Endpoint:", `${diffEndpoint}?latest=${opts.tag}`);
    log.info("overwrite files:", !!opts.overwrite);
    await translateRemoteDiff(
      config,
      `${diffEndpoint}?latest=${opts.tag}`,
      assetEndpoint,
      undefined,
      !opts.overwrite,
    );
  }
}

main()
  .then(() => process.exit(0))
  .catch((err) => {
    log.error(err);
    process.exit(1);
  });
