# C（官方 Web 文本检索与证据）— 准备清单与实施分解

> 本文件是**准备与规划**，不是实现。所有数字均为 2026-10-07 在本机/官方 HF API 实测。
> 放在 tmp/ 仅为草稿，不进入正式结果，不作为任何 run 的输入。

## 0. 一句话任务

在**自己这一台电脑**上准备**唯一一份** M3 检索资源（官方 Web 索引 + BGE 编码器），
用**纯原始 query**（不含图片/OCR/caption/full_query/历史/参考答案）检索，
按 `m3.v1` 每题输出 `evidence.jsonl`（`ok/empty/error` + `hits`），并交出资源与耗时记录。

C 只做检索；不部署 Llama-3.2-11B-Vision；D/E 不需要复制你的索引。

---

## 1. 已核实的资源坐标（可直接写进配置与 freeze_record）

| 项 | 值 |
| --- | --- |
| 索引 HF id | `crag-mm-2025/web-search-index-public-test` |
| 索引 revision (immutable) | `bd32162ffb21626994ad86ab147793561ba8fad2` |
| 索引 tag | `main`（官方建议保持 main） |
| 索引 lastModified | 2025-06-02T08:14:37Z |
| **索引实际字节** | **17,628,300,096 B ≈ 17.63 GB(十进制) / 16.42 GiB** |
| 编码器 HF id | `BAAI/bge-large-en-v1.5` |
| 编码器 revision (immutable) | `d4aa6901d3a41ba39fb536a557fa166f842b0e09` |
| 编码器权重 | `model.safetensors` 1,340,616,616 B ≈ 1.34 GB |
| 官方检索包 | `cragmm-search-pipeline==0.5.1`（wheel sha256 `00d4ab50…977628`） |

索引构成（main revision）：

| 文件 | 字节 | 说明 |
| --- | --- | --- |
| `chroma.sqlite3` | 10,205,868,032 | Chroma 元数据/全文库，**单文件 9.5 GiB** |
| `<uuid>/data_level0.bin` | 7,119,961,992 | HNSW 向量层 |
| `<uuid>/index_metadata.pickle` | 281,435,648 | 268 MiB Python pickle（全量 metadata，见风险 R3） |
| `<uuid>/link_lists.bin` | 14,310,524 | HNSW 图 |
| `<uuid>/length.bin` | 6,723,288 | |
| `<uuid>/header.bin` | 100 | |

**注意**：BGE 仓库里 `model.safetensors` / `pytorch_model.bin` / `onnx/model.onnx`
各约 1.34 GB，**裸下载会是 4 GB+**。必须用 `allow_patterns` 只取一份格式
（safetensors + `config.json` + `tokenizer*` + `vocab.txt` + `modules.json` + `1_Pooling/` + `sentence_bert_config.json`）。
任务书说的 1.34 GB 成立，17.63 GB 也成立（是十进制字节，不是 GiB）。

---

## 2. 本机体检（实测，2026-10-07）

| 项 | 实测 | 与任务书对比 |
| --- | --- | --- |
| RAM | 15.78 GB 总 / **当前仅 4.82 GB 可用**（占用 69%） | 任务书「16GB 是否可用尚未证明」→ **仍是最大未知** |
| CPU | 24 逻辑核 | — |
| GPU | RTX 4050 Laptop，**6141 MiB 总 / 3438 MiB 空闲**，driver 577.00 | 任务书写「8GB」→ **实际只有 6GB**，需报 A |
| 磁盘 D: | 651.6 GB 总 / **419.9 GB 空闲** | 任务书建议空闲 60–80 GB → **满足** |
| 磁盘 C: | 300 GB 总 / 50.2 GB 空闲 | 索引不能放 C |
| Python | 3.11.13（`C:\Users\34353\anaconda3\envs\pytorch`） | 与「推荐 3.11」一致 |
| torch | 2.8.0+cu128，CUDA 12.8，`cuda.is_available()=True` | 可用 |
| transformers | **5.14.1** | 官方包只要求 `>=4.20.0`，但 5.x 有破坏性变更 → 见风险 R4 |
| 已装 | accelerate 1.13.0, bitsandbytes 0.49.2, huggingface_hub 1.26.1, numpy 2.4.5 | |
| **未装** | `cragmm-search-pipeline`, `chromadb`, `datasets`, `sentence-transformers` | 需装 |

仓库现状（C 相关文件**全部不存在**，均为待建）：

```
src/retrieval/            MISSING
scripts/retrieve.py       MISSING
requirements-retrieval.txt MISSING
experiments/m3/retrieval.json MISSING   (experiments/m3/ 只有 freeze_record.json)
data/processed/m3/        MISSING   ← B 尚未交付，正式题未到
results/m3/               MISSING
search_indices/           MISSING   ← 索引尚未下载
```

已存在、可直接复用：`src/contracts/m3.py`（`query_sha256` / `config_sha256` / `canonical_json` / `file_sha256`）。
C 应 **import 复用**，不要另写一套哈希逻辑。

---

## 3. 阻塞项（必须先解决，否则无法开工）

### B1. 本机 HTTPS 完全不通（最高优先级）

实测：

- `curl https://…` → `schannel: AcquireCredentialsHandle failed: SEC_E_NO_CREDENTIALS (0x8009030e)`
- Python `ssl` 对 **baidu / pypi / microsoft / hf-mirror 全部** → `SSLError [ASN1: NOT_ENOUGH_DATA]`
- `http://www.baidu.com` → **200**（HTTP 通，只有 TLS 不通）
- 非沙箱（full access）下同样失败 → **不是 DSH 沙箱限制，是本机环境问题**

叠加：`C:\Windows\System32\drivers\etc\hosts` 把 **`huggingface.co`、`github.com` 及全套 GitHub 域名指向 `127.0.0.1`**。

后果：**现在无法 `pip install`，也无法下载 17.63 GB 索引和 BGE 权重。**

建议（按顺序试）：

1. 起本机代理（D 盘已有 `Clash`、`迷雾通` 目录），设 `HTTPS_PROXY`/`HTTP_PROXY` 走 127.0.0.1 端口；
   代理远端解析 DNS，可**绕过 hosts 里 huggingface.co→127.0.0.1**。
2. 无需代理时的替代：设 `HF_ENDPOINT=https://hf-mirror.com` 并用 hf-mirror 下载索引与权重
   （本次索引元数据就是通过 hf-mirror 核实的）。
3. 无论走哪条路，**先修 TLS**，否则 pip 也装不了。

> 注：我（本会话）自己有独立网络出口，已用它核实了索引/编码器 revision 与大小；
> 但那不代表你的 shell 能下载。

### B2. 工作区既有子目录不可写

实测：`D:\CH02-01\` 根可写，但 `scripts/ src/ docs/ fixtures/ tests/ experiments/ tmp/` **全部拒绝写入**
（`Access to the path … is denied`）。

原因：根目录带 `Mandatory Label\Low Mandatory Level:(OI)(CI)(NW)`，
而**既有子目录没有完整性标签**，默认按 Medium 处理；沙箱进程运行在 **Low 完整性**，
受 No-Write-Up 策略限制，写 Medium 对象被拒。**新建目录会继承 Low 标签，所以可写**
（已实测：新建目录写入成功）。

后果：将来 Python 写 `results/m3/*.jsonl`、把索引下载到 `search_indices/` 都会失败。
`D:\CH02-01\tmp` 目前只能被编辑工具写入，不能被 pwsh/Python 写入。

建议（二选一，需你确认）：

- **A**（推荐）：给工作区补完整性标签，与 DSH 对根目录的做法一致
  `icacls "D:\CH02-01" /setintegritylevel (OI)(CI)Low /T /C`
  —— 只改完整性标签，不改权限、不改所有者、不动文件内容。
- **B**：把本会话切到「完全权限」(full access)。

> 遗留：我用编辑工具写了 `tmp\_probe_write_tool.txt` 做探测，因上述原因**删不掉**，
> 修好标签后请一并删除。

---

## 4. 需要准备什么（交付清单）

### 4.1 依赖与隔离环境

独立 venv（不要污染 pytorch 环境），放 D 盘：

```powershell
py -3.11 -m venv D:\CH02-01\.venv-retrieval
.\.venv-retrieval\Scripts\python.exe -m pip install -r requirements-retrieval.txt
```

`requirements-retrieval.txt` 必须记录**实际验证版本**（含官方包的传递依赖，A 会在验收时核对）：

```
cragmm-search-pipeline==0.5.1
torch==<实测>
transformers==<实测，注意 5.x 风险>
chromadb>=1.0.3,<2
chroma-hnswlib>=0.7.6
sentence-transformers==<实测>
huggingface-hub==<实测>
numpy==<实测>
lmdb>=1.6.2
```

### 4.2 资源落盘（全部放 D 盘，别用 C 盘）

```powershell
$env:HF_HOME = "D:\CH02-01\search_indices\hf_home"   # C 盘只剩 50 GB
```

- 索引：`revision=bd32162ffb21626994ad86ab147793561ba8fad2`，约 17.63 GB
- 编码器：`revision=d4aa6901d3a41ba39fb536a557fa166f842b0e09`，`allow_patterns` 只取 safetensors 一份

### 4.3 接口文件

- `experiments/m3/retrieval.json` —— 至少含 `top_k`(=5 起步)、`index_revision`、`encoder_revision`；
  **不能含密钥**；哈希用 `src/contracts/m3.py::config_sha256`。
- 逐行字段严格按 `接口字段.schema.json` 的 `evidence` / `hit` 定义（`additionalProperties:false`）。

### 4.4 输入数据（等 B）

- `data/processed/m3/manifest.json` + `smoke/questions.jsonl`（B 交，先 20 条）
- **C 不读 `answers.jsonl`**（协议明令）。run_meta 的 `input_files_sha256` 里出现 answers 哈希会被 A 判错。

### 4.5 交付物（每人一份，C 的）

1. `src/retrieval/text_retrieval.py`、`scripts/retrieve.py`
2. `requirements-retrieval.txt`、`experiments/m3/retrieval.json`
3. `results/m3/<subset>/evidence.jsonl`、`run_meta_retrieval.json`
4. 索引/编码器**实际 revision**、耗时/峰值内存记录、来源抽查、方法说明、已知限制

---

## 5. 具体要做什么（实现分解）

### 步骤 0：可行性（第 1 天，不等 B）

1. 解决 B1/B2 两个阻塞。
2. 装包、落盘索引与编码器，记 revision 与字节数。
3. **真实加载**索引 + BGE，用**普通文本**（可先用 3–5 条自造英文问句，仅用于可行性，不进正式结果）跑通搜索。
4. 记录：加载耗时、每题延迟、**峰值内存 / 换页**。
   - 若 16 GB 装不下，**明确报 A**（协议：不许用模拟搜索「完成」，也不许偷偷换小索引）。

### 步骤 1：适配层 `src/retrieval/text_retrieval.py`

核心难点（任务书第 1 条）：官方 `UnifiedSearchPipeline` **会初始化图像部分，传 `None` 跳不过去**。
必须写一个**只加载 Web + BGE** 的适配层，要点：

- 核实并记录：`cragmm-search-pipeline==0.5.1` 的实际可调用签名、索引配置、
  **编码/池化(pooling)/归一化(normalize)** 方式、**距离定义**。
- 距离→分数语义：若底层是 cosine distance，`score_kind` 必须写 `distance`；
  只有确实是相似度才写 `similarity`；不确定写 `unknown`。**不得把 distance 冒充 similarity。**
- 输出 `hits`：`rank / doc_id / url / title / text / score / score_kind`。
  - `doc_id` = 官方返回的 `index`（形如 `https://en.wikipedia.org/wiki/…_chunk_2`）
  - `url` 从 doc_id 拆出；`title` = `page_name`；`text` = `page_snippet`
  - **没有网页正文就保存片段并说明**，不许声称已取全文
- 低内存考虑（任务书第 3 条）：官方 `CragMockWeb` 会全量读 metadata 建 Python dict，
  且 `index_metadata.pickle` 本身 268 MiB。可评估「按命中再取 metadata」是否保持检索语义；
  但 **Chroma/HNSW 自身内存省不掉**。**只查 20 题不会缩小完整索引**——这个必须实测说清楚。

### 步骤 2：CLI `scripts/retrieve.py`

```
python scripts/retrieve.py --questions QUESTIONS --manifest MANIFEST \
  --config experiments/m3/retrieval.json --output EVIDENCE [--batch-ids BATCH.json]
```

必须做到：

- `--help` **不下载索引、不加载模型、不调 API**
- 读 questions + manifest，**核对 ID 与 hash**（manifest 原字节 SHA256、每题 `query_sha256`）
- 输入**只有原始 query**：不碰 `image_url`/`ocr`/`caption`/`full_query`/history/answers
- 逐题落盘；**有界重试**；**断点续跑**
- **每个预期 ID 都要有一行状态**，绝不静默删题
- 状态语义：`ok`=hits 非空；`empty`=检索成功但零命中（`error_code=null`）；`error`=技术故障（hits 空、`error_code` 非空）
- **缓存键必须含 query + 配置哈希 + 索引/编码器 revision**，不能只用 ID
- `--batch-ids` 时：预期 ID 集合 = 该数组；不改变 manifest 哈希；不跨 subset；批间不重复
- 退出码：结构/ID/哈希错 → 非零报错；遍历完但存在技术失败 → 写完整状态行后非零退出

### 步骤 3：配置与 freeze 记录

- `retrieval.json`：`top_k=5`、无重排、无实时抓取（**初始值，只在 dev 调**）
- 冻结后 eval 一次正式配置输出，批次沿用**同一 `run_id`**，合并去重后验收
- 若适配层改变了官方流程 → **写清差异**；有条件时用少量相同 query 对照官方文本结果；
  **不得宣称未经实测的等价性**

### 步骤 4：run_meta

按协议第十一节精确字段：`run_id/stage/subset/schema_version/code_commit/input_files_sha256/
output_files_sha256/config/config_sha256/started_at/finished_at/hardware/N_expected/N_success/
N_failed/retries/peak_memory_mb`（+ 分批时的 `batch_ids`）。

- 检索 `ok`/`empty` **都算成功**；`N_success + N_failed = N_expected`
- **input_files_sha256 不得包含 answers**
- 缓存复跑**不能当作原始检索耗时为零**

---

## 6. 风险清单（需向 A 报告）

| ID | 风险 | 说明 |
| --- | --- | --- |
| R1 | **本机 HTTPS 全断 + HF 被 hosts 屏蔽** | 见 B1。不解决则**完全无法下载**，C 的第一天目标直接落空 |
| R2 | **RAM 16 GB 可能不够** | Chroma 全量 + 9.5 GiB sqlite + 6.6 GiB HNSW；当前可用内存仅 4.82 GB。必须实测峰值内存/换页，失败就报 A |
| R3 | `index_metadata.pickle` 268 MiB + 官方 `CragMockWeb` 全量 dict | 低内存适配可能与官方流程产生语义差异，需说明 |
| R4 | **transformers 5.14.1** 与官方包（`>=4.20.0`）可能不兼容 | 建议独立 venv，实测能导入再记录；不要升级/降级全局环境 |
| R5 | GPU 实际 6 GB（非任务书的 8 GB） | 需报 A 修正设备记录；BGE-large 用 fp16 小批量在 6 GB 上应可行 |
| R6 | C 盘仅剩 50.2 GB | `HF_HOME` 必须指向 D 盘，否则空间不够 |
| R7 | 工作区子目录不可写 | 见 B2，会挡住所有产物落盘 |

---

## 7. 时间线（对齐 00 群消息）

| 天 | C 的动作 |
| --- | --- |
| D1 | 解阻塞 → 装包 → 落盘索引/BGE → 真实加载并测 20 题可行性 → **交 smoke 证据** |
| D2 | dev 上调 `top_k`/设备等参数 → 报 A 冻结 → 写 freeze 证据 |
| D3 | 逐批 eval 检索与导出（支持恢复），**优先给 D 第一批真实证据** |
| D4 | 按命令复跑一小批 → 交方法/结果/限制 + 案例说明 |

每日固定格式进度：
```
[角色] 已完成：……
真实验证：输入文件/题数/成功数/命令……
已交文件：……（写版本、哈希或 commit）
阻塞：……
下一批交付：……
```
