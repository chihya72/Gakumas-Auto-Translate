import fs from "fs-extra";
import { resolve, basename, join } from "path";
import log from "loglevel";
import { LLMConfig, translateCsvString, translateJsonDataToCsvString } from "../src/translate";
import { getLLMConfig, setupLog, getRemoteEndpoint } from "../src/setup-env";
import { program } from "commander";
import axios from "axios";
import { walkSync } from "@nodelib/fs.walk";
import { extractInfoFromCsvText } from "../src/csv";

// 上游入口会吞掉单文件异常并继续翻译剩余文件。对余额、认证、输出预算等
// 全局故障，这会把一次错误放大成整批付费请求。本副本保持兼容，但改为 fail-fast。
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
  files.sort((a, b) => a.name.localeCompare(b.name));
  log.info("Found " + files.length + " csv files to translate");

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
    } catch (error) {
      log.error(`failed to translate ${entry.path}; aborting remaining files`);
      throw error;
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
