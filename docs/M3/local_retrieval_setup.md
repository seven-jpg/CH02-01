# 组长电脑的本地检索启动说明

当前状态：**本机已经可以运行真实文本检索**。官方 Web 索引和 BGE 的 17 个必要文件共约 18.97 GB，均已按固定版本的官方 LFS SHA256 / Git blob 校验。2026-10-10 在 RTX 4060 Laptop / 16 GB RAM 上离线运行 smoke20，20 题全部成功、零技术失败，严格接口与来源哈希验收通过。本机检索步骤无需租服务器。

Git 保存代码、配置、题目和已有结果，不包含约 **17.63 GB 官方 Web 索引**和 **1.34 GB BGE 权重**（十进制容量，另有少量配置/分词文件），也不包含虚拟环境。另一台电脑拉取 Git 后，仍需自行安装环境并准备相同版本资源。组长电脑使用 Python 3.12 的 `.venv-retrieval`，已安装 PyTorch 2.8.0+cu126 / CUDA 12.6，GPU 编码检查通过。

这里运行的是 B1 的**本地文本检索步骤**：BGE 编码问题，在官方 Web 索引取证据，不需要 Llama、生成 API 或裁判 API。完整 B1 回答仍由 D 的生成模块使用这些证据产生，E 负责评分。

## 固定资源与启动脚本

资源位置均相对项目根目录：

| 内容 | 本地位置 / 固定版本 |
| --- | --- |
| Python | `.venv-retrieval/Scripts/python.exe` |
| 可写 Chroma 工作库 | `search_indices/index_working/`，含 `chroma.sqlite3` 与 HNSW 段目录 |
| Web 索引 | `crag-mm-2025/web-search-index-public-test`，revision `bd32162ffb21626994ad86ab147793561ba8fad2` |
| BGE | `BAAI/bge-large-en-v1.5`，revision `d4aa6901d3a41ba39fb536a557fa166f842b0e09` |
| BGE 本地快照 | `search_indices/hf_home/hub/models--BAAI--bge-large-en-v1.5/snapshots/d4aa6901d3a41ba39fb536a557fa166f842b0e09/` |

`scripts/retrieve_local.ps1` 可从任意工作目录调用，不用激活虚拟环境。它将工作目录临时切到项目根，所以传给 CLI 的相对路径都相对项目根解释；参数原样传递，未提供 `--index-path` 时自动补上本机工作库。它临时设置 `HF_HOME`、`HF_HUB_CACHE`、`HF_HUB_OFFLINE=1` 、`TRANSFORMERS_OFFLINE=1` 和 `ANONYMIZED_TELEMETRY=False`，退出时恢复环境变量和原工作目录。缺少资源会报错，不联网补下载；`--help` 不检查大文件。

运行前只检查 Python、索引和模型必要文件，不打开 Chroma、不加载模型。文件存在检查不能替代下载时的 SHA256 核验或真实加载测试；首次打开 Chroma 可能修改可写工作库，资源下载核验记录应在首次打开之前保留。该包装只支持上表固定资源；准备/复制索引等安装动作使用原 CLI 或下载流程，不通过本包装执行。

固定基线继续使用原 `experiments/m3/retrieval.json`，**不要修改它的本机路径或其他字段**。原配置的 `index_cache_dir` 是 C 电脑路径，包装通过 `--index-path` 覆盖位置；该绝对缓存位置不参与公共配置哈希，基线仍为 `47d54550ef627166812458df23d43fbec926a4100ee3de1568b6129bf69e9e98`。不要增加 `--device cuda`：`device` 是实验参数，覆盖后会改变哈希；原 `auto` 会由实际环境选择设备并记录到 run_meta。`fetch_k` 尚未实现，不添加到配置。

## 运行真实 smoke20

在 PowerShell 中执行（按实际项目位置修改第一行，其他相对路径无需改）：

```powershell
$Repo = 'D:\jqxxxxq\CH02-01'
& "$Repo\scripts\retrieve_local.ps1" --help

& "$Repo\scripts\retrieve_local.ps1" `
  --questions data/processed/m3/smoke/questions.jsonl `
  --manifest data/processed/m3/manifest.json `
  --config experiments/m3/retrieval.json `
  --output results/m3/local_retrieval_smoke_run1/evidence.jsonl `
  --run-meta results/m3/local_retrieval_smoke_run1/run_meta_retrieval.json
$LASTEXITCODE
```

每次新的实测使用新的输出目录，例如 `local_retrieval_smoke_run2`，保留 C 已提交的 `results/m3/smoke/` 和 `results/m3/dev/`。同一批中断后可用完全相同命令续跑；不要用 `--no-resume` 删除已有产物，也不要把续跑耗时当首次冷启动耗时。原 CLI 退出码：`0` 全部 ok/empty，`1` 结构/配置错误，`2` 保留了技术失败；包装前置失败为 `1`。`0` 只表示检索遍历成功，不代表答案正确。

本机首轮记录：Python 3.12.9、PyTorch 2.8.0+cu126、Chroma 1.5.9、Transformers 5.14.1；实际设备为 CUDA，集合空间为 cosine。20 题全部返回非空证据，进程峰值内存约 7516 MB，运行墙钟时间 38.3 秒。预热探测报了一次 `RetrievalError`，后续 20 道真实题均成功且没有重试；首题 20.04 秒包含索引冷加载，不能把全体平均 1.034 秒当稳定态耗时，也不能用它宣称满足比赛每轮 10 秒限制。后 19 题耗时可从逐题文件单独统计。编码器单独预检的显存分配峰值约 1289 MiB，完整检索没有记录显存峰值，不能混用两者。

共享摘要见 [本机验证记录](retrieval_review/local_environment_verification.json)。完整本地产物为 `results/m3/local_retrieval_smoke_run1/{evidence.jsonl,run_meta_retrieval.json,acceptance.json}`；下载前后记录、首次 Chroma 打开前的哈希证明和依赖锁在 `search_indices/setup_records/`。这些本机大资源与运行目录由 Git 忽略，原始测量不覆盖 C 的记录。索引是可写工作副本，首次打开后可能迁移，后续不要把它与下载前的 SQLite 哈希不一致误判为下载损坏；若要恢复原始版本，使用新的下载目录。

## 在同一 dev50 上比较 k=1/3/5

C 已提交三组 dev50 的真实检索，D 已提交相应生成，当前不需要为了选 k 重跑相同检索；下一步等 E 对同一批回答评分。下面是需要独立复现时的命令。扫参脚本固定使用同一 manifest 和完整 dev50，单独生成三份配置；不改公共基线配置。它的原 CLI **没有 `--batch-ids`**，适合在一台有索引的电脑上顺序执行三个完整候选。

下列命令先准备配置和计划，尚不执行检索。因为扫参脚本使用当前 Python 启动子进程，必须使用 `.venv-retrieval`，不要用 `.venv-integration`：

```powershell
Push-Location $Repo
try {
  & "$Repo\.venv-retrieval\Scripts\python.exe" -X utf8 scripts/sweep_retrieval.py `
    --manifest data/processed/m3/manifest.json `
    --questions data/processed/m3/dev/questions.jsonl `
    --config experiments/m3/retrieval.json `
    --output-dir results/m3/local_dev_topk_sweep_run1 `
    --top-k 1 3 5 `
    --index-path "$Repo\search_indices\index_working"
} finally {
  Pop-Location
}
```

准备完成后，逐个调用包装，让各候选都使用本地缓存和离线模式；用同一套已经准备的候选配置，不手改哈希：

```powershell
foreach ($K in @(1, 3, 5)) {
  $Output = "results/m3/local_dev_topk_sweep_run1/top_k_$K"
  & "$Repo\scripts\retrieve_local.ps1" `
    --questions data/processed/m3/dev/questions.jsonl `
    --manifest data/processed/m3/manifest.json `
    --config "$Output/retrieval.json" `
    --output "$Output/evidence.jsonl" `
    --run-meta "$Output/run_meta_retrieval.json"
  if ($LASTEXITCODE -ne 0) { throw "top_k=$K failed: exit $LASTEXITCODE; inspect the retained records." }
}
```

这条路径直接调用原检索 CLI，扫参计划仍标记 prepare-only，不能拿它的计划文件声称已经执行成功；实际执行依据各候选 evidence/run_meta 和 A 的验收记录。D 对三组证据使用同款模型、提示、清理规则和证据 token 预算，E 用同一规则对相同 dev ID 做成对评分，A 才能依据回答质量选择 k。检索相似度和 hits 数量不能证明最优。若不做扫参，可以诚实固定 `top_k=5`；eval200 只用于最终测量，不用于选参数。

## A 与 C 分批跑时的交接

原 `scripts/retrieve.py` 已支持 `--batch-ids`：文件必须是 UTF-8、无 BOM 的非空唯一 ID 字符串数组，ID 全部来自该 subset 的原 manifest。已经生成 `experiments/m3/batches/dev_A.json`、`dev_C.json`（各 25 题），以及 `eval_A.json`、`eval_C.json`（各 100 题）；按 manifest 原顺序分前后两半，互不重叠且完整覆盖，原 manifest 不变。文件哈希与分批规则在同目录 `plan.json`，不得用参考答案决定批次。

两台电脑仍传完整的同一个 questions 文件与原 manifest，并使用**完全相同的候选配置**。每个 k 都复用相同批次 ID。A 的一个批次示例：

```powershell
& "$Repo\scripts\retrieve_local.ps1" `
  --questions data/processed/m3/dev/questions.jsonl `
  --manifest data/processed/m3/manifest.json `
  --config results/m3/local_dev_topk_sweep_run1/top_k_3/retrieval.json `
  --batch-ids experiments/m3/batches/dev_A.json `
  --output results/m3/local_dev_batches_run1/top_k_3/A/evidence.jsonl `
  --run-meta results/m3/local_dev_batches_run1/top_k_3/A/run_meta_retrieval.json
```

C 对应使用 `dev_C.json` 和独立 `C/` 输出目录。原 CLI 按同一 subset/config/manifest 派生相同 run_id，批次和本机索引位置不改变它。交付时每人交 evidence、run_meta 和批次 ID 文件；A 分批验收后按 `interaction_id` 合并，检查重复、缺失、配置/manifest/hash/run_id 一致，并保留两台机器各自原 run_meta。分批记录不能冒充单机全量测量；D/E 也按同一批次 ID 联调，最终评价从完整去重逐题记录重新计算。
