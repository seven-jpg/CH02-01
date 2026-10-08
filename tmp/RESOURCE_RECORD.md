# C 模块检索资源记录（真实下载并校验）

> 记录日期：2026-10-07
> 本文件记录 **实际下载到本机** 的 M3 检索资源，含不可变 revision、字节数与 SHA256 校验结果。
> 所有哈希均为本机实测，可与官方 HF API 的 LFS oid 逐一对照。
> 建议后续移到 `experiments/m3/` 或作为 run_meta 的证据附件；本文件不构成任何实验结果。

---

## 1. 下载环境（关键：必须用 TLS 正常的解释器）

| 项 | 值 |
| --- | --- |
| 解释器 | `D:\CH02-01\.venv-hf\Scripts\python.exe` |
| Python | 3.13.5（由 anaconda base 创建，`--system-site-packages`） |
| OpenSSL | 3.0.16（**必须**） |
| huggingface_hub | 1.26.1（纯 Python，从 pytorch 环境复制，绕开损坏的 pip） |
| 镜像 | `HF_ENDPOINT=https://hf-mirror.com` |

**必要的环境变量：**

```powershell
$env:HF_ENDPOINT               = "https://hf-mirror.com"
$env:HF_HOME                   = "D:\CH02-01\search_indices\hf_home"
$env:HF_HUB_CACHE              = "D:\CH02-01\search_indices\hf_home\hub"
$env:HF_HUB_DISABLE_XET        = "1"     # 本机无 cp313 的 hf_xet，强制走普通 HTTP LFS
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"
```

> ⚠️ **不要用 `C:\Users\34353\anaconda3\envs\pytorch\python.exe` 下载**：
> 该环境的 OpenSSL 3.5.7 已损坏，所有 TLS 握手报
> `SSLError [ASN1: NOT_ENOUGH_DATA]`。疑似 conda 事务中断残留
> （`Library\bin\libcrypto-3-x64.dll.c~.conda_trash`），libssl/libcrypto 版本不匹配。
> 待修，但不影响本次下载。

---

## 2. Web 检索索引

| 项 | 值 |
| --- | --- |
| HF id | `crag-mm-2025/web-search-index-public-test` |
| repo_type | `dataset` |
| **immutable revision** | **`bd32162ffb21626994ad86ab147793561ba8fad2`** |
| 本机快照路径 | `D:\CH02-01\search_indices\hf_home\hub\datasets--crag-mm-2025--web-search-index-public-test\snapshots\bd32162ffb21626994ad86ab147793561ba8fad2` |
| 总字节 | **17,628,302,096 B**（16.42 GiB / 17.63 GB 十进制）|
| 实测下载耗时 | 约 32 分钟，均速 **9.11 MiB/s** |
| 缓存复验 | `snapshot_download` 重跑 **1.60s** 秒回，不重新下载 ✓ |

### 文件清单与 SHA256 校验（全部匹配官方 LFS oid）

| 文件 | 字节 | 本机 SHA256 | 官方 LFS oid | 结果 |
| --- | --- | --- | --- | --- |
| `chroma.sqlite3` | 10,205,868,032 | `652e9b2dd75396f70dbb3546de6311ec0d14120220f22eb532e0252ec957e271` | 同左 | ✅ |
| `6fb7c70d-…/data_level0.bin` | 7,119,961,992 | `313bad84421f6c31e77de2e78bc8307f8c52f784e97ff8cfcb8f1ee78ab9c4a9` | 同左 | ✅ |
| `6fb7c70d-…/index_metadata.pickle` | 281,435,648 | `6b5aceb410a1f8e6c765997f247e44a157b4f0f1c671f6a964039459de5d7457` | 同左 | ✅ |
| `6fb7c70d-…/link_lists.bin` | 14,310,524 | `2c5ee2e272f4d68d72b75345242fb2643950ae3b5026dd39175db0dab1e54a20` | 同左 | ✅ |
| `6fb7c70d-…/length.bin` | 6,723,288 | `e61abae2e88df845e7218493b30ee7860220647429d13e1c8a497ed7c701cfad` | 同左 | ✅ |
| `6fb7c70d-…/header.bin` | 100 | `96f8518fbb816409f1e23a417a737254b16b265af942a4487cf155e7ed90f3c9` | 同左 | ✅ |
| `.gitattributes` | 2,512 | `b8523095639887939b69fc0e9fcca4564fed2e8c283633c76f385c65e14459c7` | （非 LFS，无 oid） | n/a |

完整校验输出：`D:\CH02-01\search_indices\_sha256_index.txt`

> **Windows 说明**：本机不支持符号链接，HF 缓存处于 "degraded mode"（真实文件直接放在
> `snapshots/<sha>/` 而非 `blobs/` + 链接）。功能等价，Chroma 可正常打开该目录。

---

## 3. BGE 查询编码器

| 项 | 值 |
| --- | --- |
| HF id | `BAAI/bge-large-en-v1.5` |
| **immutable revision** | **`d4aa6901d3a41ba39fb536a557fa166f842b0e09`** |
| 本机快照路径 | `D:\CH02-01\search_indices\hf_home\hub\models--BAAI--bge-large-en-v1.5\snapshots\d4aa6901d3a41ba39fb536a557fa166f842b0e09` |
| 总大小 | 1.25 GiB |
| 实测耗时 | 145.3s，均速 **8.81 MiB/s** |

只取了 sentence-transformers 需要的 10 个文件（**刻意排除** `pytorch_model.bin` 与
`onnx/model.onnx`，各约 1.34 GB，省掉约 2.7 GB 冗余权重）：

| 文件 | 字节 | SHA256 |
| --- | --- | --- |
| `model.safetensors` | 1,340,616,616 | `45e1954914e29bd74080e6c1510165274ff5279421c89f76c418878732f64ae7` ✅ 匹配官方 LFS oid |
| `tokenizer.json` | 711,396 | — |
| `vocab.txt` | 231,508 | — |
| `config.json` | 779 | — |
| `tokenizer_config.json` | 366 | — |
| `modules.json` | 349 | — |
| `1_Pooling/config.json` | 191 | — |
| `special_tokens_map.json` | 125 | — |
| `config_sentence_transformers.json` | 124 | — |
| `sentence_bert_config.json` | 52 | — |

---

## 4. 官方检索包（已取源码用于核实语义）

`cragmm-search-pipeline==0.5.1` 的 wheel（19,922 B）已用 curl 取下并解包到
`D:\CH02-01\tmp\_pkg\extracted\`，直接读源码，**未安装**。

wheel SHA256（PyPI 元数据）：`00d4ab506d6e56982ec4c1bdb0bef4838870cd09a0f633796484254dcd977628`

---

## 5. 官方检索语义（读 0.5.1 源码核实，写适配层必须对齐）

来源：`cragmm_search/search.py`、`web_search_mock_api/api/web_search.py`、`api/web_index.py`、`utils.py`

**索引加载**（`index_web_data`）：
```python
dataset_local_path = snapshot_download(repo_id=hf_path, repo_type="dataset", revision=revision)
client = chromadb.PersistentClient(path=dataset_local_path)
collection = client.get_collection(name="web_search_embeddings")
collection.modify(metadata={"hnsw:num_threads": os.cpu_count()})
```
- 集合名固定为 **`web_search_embeddings`**
- 索引**原地**被 Chroma 打开 → 该目录必须有写权限（`modify` 会写元数据）

**特征抽取**（`extract_features`）：
- tokenizer：`padding=True, truncation=True, **max_length=512**`
- **mean pooling**（按 attention_mask 加权）
- **L2 归一化**（`features / features.norm(dim=-1, keepdim=True)`）
- ⚠️ **不加** BGE 官方推荐的 query 指令前缀（"Represent this sentence for searching…"），
  直接用原 query。适配层必须与此一致，否则语义漂移。

**检索与打分**（`web_search`）：
- 再次 L2 归一化 query
- `collection.query(query_embeddings=…, n_results=top_n)`
- **`score = 1.0 - distance`**
- 按 `doc_id.split("_chunk")[0]` **按页面去重**，再按 score 降序取 `top_n`
- ⚠️ 因为**先去重后截断**，去重后条数**可能少于 top_n** —— 这是官方行为，不是 bug

**命中字段**（`postprocess`，非 private 路径）：
```python
{"index": ind, "score": score, "page_name": …, "page_snippet": …, "page_url": …}
```
映射到 m3.v1 的 hits：`doc_id=index`、`text=page_snippet`、`title=page_name`、`url=page_url`

**`score_kind` 注意事项**：
`score = 1 - distance` 是**距离派生量**，不是纯相似度。
本机**尚未确认**该 collection 的 Chroma 距离空间（l2 / cosine / ip），
需在真正打开索引后读取 collection 配置再决定 `score_kind` 写
`distance` 还是 `similarity`。**在确认前不得写成 `similarity`。**

**内存注意**（对应任务书第 3 条）：
`CragMockWeb.__init__` 里这一行会把**全量 metadata 灌进 Python dict**：
```python
self.index_to_metadata = dict(zip(vector_db.get()['ids'], vector_db.get(include=["metadatas"])['metadatas']))
```
叠加 `chroma.sqlite3` 9.5 GiB + `data_level0.bin` 6.6 GiB，
16 GB RAM 能否承受**仍未证明**，必须实测峰值内存/换页。

---

## 6. 实测验证结果（索引已真正打开并查询成功）

环境：`C:\Users\34353\anaconda3\envs\pytorch\python.exe`，`chromadb 1.5.9`，`cragmm-search-pipeline 0.5.1`，
GPU = RTX 4050 Laptop（6141 MiB）。

### 6.1 集合实况

| 项 | 值 |
| --- | --- |
| 集合名 | `web_search_embeddings` |
| **条目数** | **1,681,350** |
| **距离空间** | **`hnsw:space = "cosine"`** |
| HNSW 配置 | `ef_construction=100, ef_search=100, max_neighbors=16` |

> ✅ **`score_kind` 可以写 `similarity`**：空间是 cosine，Chroma 的 `distance = 1 - cos_sim`，
> 官方 `score = 1 - distance` 即余弦相似度。之前的保留意见可以解除。

### 6.2 实测耗时与内存

| 阶段 | 耗时 | 内存 |
| --- | --- | --- |
| 打开集合 | 4.9–5.2 s | 打开后 working set 仅 **101 MB** |
| BGE 加载（→CUDA） | 9.3–10.6 s | — |
| 编码 1 条 query | 0.73–0.99 s | — |
| 查询 top-5 | 101–105 ms | — |
| **整进程峰值内存** | — | **7,584 MB** |

**关键结论**：Chroma **不会**把整个索引读进内存（打开后仅 101 MB），
峰值 7.6 GB 主要来自 BGE fp32 加载 + CUDA context。**16 GB 机器可以跑**。

### 6.3 ⚠️ 官方 `CragMockWeb` 的额外内存开销（未实测，已估算）

官方 `CragMockWeb.__init__` 会把**全量 metadata 灌进 Python dict**。
本机抽样 5,000 条实测：

| 指标 | 值 |
| --- | --- |
| 单条 metadata（JSON） | 1,692 bytes |
| 全量 JSON 估算（下限） | **2.65 GiB** |
| 全量 Python dict 估算（含对象开销，粗估） | **约 6.6 GiB** |

> ⚠️ **建议不要照抄官方那一行**。用 `collection.query()` 返回的 `metadatas`
> 按命中取字段即可（探针脚本就是这样，全程只占 101 MB）。
> 若必须复刻官方行为，6.6 GiB 叠加在 7.6 GB 峰值之上，16 GB 机器会非常紧张。

### 6.4 ⚠️ Chroma 打开索引会改写 `chroma.sqlite3`

实测对照（打开一次之后）：

| 文件 | HF 缓存（原始） | 工作副本（被打开过） |
| --- | --- | --- |
| `chroma.sqlite3` | `652e9b2d…957e271` | `dfacb8e9…5b4ad64`（**已改写**） |
| `data_level0.bin` | `313bad84…ab9c4a9` | 同左（未改动） |

所以**必须先复制再打开**，否则校验过的缓存哈希会失效。
工作副本：`D:\CH02-01\search_indices\index_working`

---

## 7. 当前状态与后续

| 项 | 状态 |
| --- | --- |
| 资源落盘 + 版本固定 + SHA256 校验 | ✅ 完成 |
| **真实索引可查** | ✅ **已验证**（168 万条，真实 query 命中合理，见 §6） |
| pytorch 环境 HTTPS | ✅ 已修（OpenSSL 3.0.16） |
| `chromadb` / `cragmm-search-pipeline` | ✅ 已装入 pytorch 环境（未升级 protobuf/pydantic/urllib3） |
| `src/retrieval/text_retrieval.py`、`scripts/retrieve.py` | ✅ **已实现**（见 §8） |
| `requirements-retrieval.txt`、`experiments/m3/retrieval.json` | ✅ 已交付 |
| 真实 20 题 smoke | ⬜ 仍等 B 交付 `questions.jsonl` |
| dev 调参与 A 冻结 | ⬜ 待 dev 数据 |
| 正式 eval 分批证据 | ⬜ 待冻结 |
| 换页 / 长时间稳定性 | ⬜ 未测（单次进程最长 3 题） |

> **资源 + 环境 + 可行性 + 代码**四块就绪；**正式 smoke/dev/eval 证据仍未产出**，
> 不得据此报告检索实验结果。

---

## 8. C 模块实现与自测结果

### 8.1 交付物

| 文件 | 作用 |
| --- | --- |
| `src/retrieval/text_retrieval.py` | 仅 Web+BGE 的适配层；不加载 CLIP，不碰图像 |
| `scripts/retrieve.py` | CLI：哈希核对、状态行、逐题落盘、断点续跑、分批、run_meta |
| `requirements-retrieval.txt` | 实测通过的依赖版本（含刻意锁定项） |
| `experiments/m3/retrieval.json` | 冻结候选配置（`top_k=5`，其余为 dev 待调） |

### 8.2 自测结果（dev 小样本，3 题，**非正式证据**）

| 检查 | 结果 |
| --- | --- |
| `--help` | 0.20s，**未加载** torch/chromadb/transformers ✓ |
| 真实检索 | 3/3 `ok`，退出码 0 ✓ |
| A 的验收器（全量 scope） | `valid: true`，0 errors，`checked_scope_only` ✓ |
| A 的验收器（`--batch-ids`） | `valid: true`，exit 0 ✓ |
| 断点续跑 | 复用 3 条、run_id 不变、不重跑 ✓ |
| 配置变更后续跑 | 旧文件另存 `.superseded-<时间戳>`，新 run 用新哈希 ✓ |
| 越界批次 / 配置缺失 | 退出码 1 + 明确报错 ✓ |
| `--require-provenance` | **正确拒绝** dev 包（`synthetic_provenance`）✓ |
| 配置哈希本机中立 | 换 `--index-path`、换 `index_cache_dir`，哈希恒为 `47d54550…` ✓ |

### 8.3 实测性能

| 指标 | 值 |
| --- | --- |
| 进程冷启动（HNSW 载入 + CUDA 预热） | **约 14–25 s，已单独记录，不计入逐题耗时** |
| 逐题检索（稳定态） | 均值 **26.6 ms**，最大 32.8 ms |
| 整进程峰值内存 | 8,774 MB（`top_k=5`，CUDA） |
| 机器可用内存 | 仅 0.46 GB（当时有训练任务在跑） |

> 冷启动 25 s 是**运维要点**：应尽量一个进程跑完整批，而不是每题起一个进程。

### 8.4 实现中确定下来的语义

- `score_kind = "similarity"`：集合 `hnsw:space=cosine`，故 `1 - distance` 就是余弦相似度。
  程序会**在加载时校验**空间，与 `hnsw_space_expected` 不符则拒绝继续。
- **先按 `_chunk` 页面去重、再截断**（官方行为）→ hits 条数可能少于 `top_k`（实测 top_k=5 时出现 3 条）。
- `text` 取 `page_snippet`，为空时回退 `page_name`（协议允许取"标题/片段内容"）；两者皆空则丢弃该命中，不伪造。

### 8.5 评审问题修复记录

评审指出的 4 个问题经逐条核实**全部成立**，已修复并逐项实测：

| # | 问题 | 原缺陷 | 修复 | 验证结果 |
| --- | --- | --- | --- | --- |
| 1 | 没检查问题文件的数据版本哈希 | `load_questions()` 完全忽略 questions 行的 `dataset_manifest_sha256`，拿错数据包也照跑 | 逐行比对 manifest 原始字节哈希；并拒绝不属于本数据包的 ID | 伪造错误哈希 → 退出码 1、**不产生输出文件** ✓ |
| 2 | 索引或模型初始化失败时留下空文件 | 在加载检索器**之前**就写了输出，`load()` 抛错后留下无状态行的空文件、且无 run_meta | 阶段化：结构性核对阶段不写文件；初始化失败为**每个**未完成 ID 写 `error` 行并照常产出 run_meta | 指向空索引目录 → 退出码 2、3 条 error 行、run_meta 存在；验收器 `valid=true exit_code=2 technical_failures_remaining` ✓ |
| 3 | 独立批次生成不同运行编号 | `run_id` 含 `utc_stamp()`，各批次 run_id 不同，合并后被判 `mixed_run` | `run_id` 改为由 (subset, 配置哈希, manifest 哈希)**确定性派生**，不含时间戳 | 两个批次 run_id 均为 `retrieval-smoke-47d54550ef62-9770b9a7`；合并后 `valid=true` 且**无 `mixed_run`** ✓ |
| 4 | 缓存缺少完整校验 | `peek_resume()` 只看状态是否 ok/empty，被截断或手改成 `ok` 的记录会被当成成功结果复用 | 新增 `row_is_sound()`：字段集合完全相等、状态与 hits 严格一致、rank 从 1 连续、text 非空、`score_kind` 合法、score 为数字或 null、query 哈希与版本字段齐备 | 把一条 `ok` 行的 hits 改为空 → 检出 1 行不合法、另存 `.superseded-*`、从头重跑 ✓ |

修复后 `scripts/retrieve.py` 的 SHA256 由 `4e64bf8b…` 变为
**`2b72ceb1ffecb20f8dd3e8e3849dd805de89e861ae566a9294e9518f56b90b8e`**。

> ⚠️ 推送注意：`requirements-retrieval.txt` 被 `.gitignore` 的 `*.txt` 挡住，
> 必须 `git add -f`，否则本次必交文件不会进仓库。

### 附：可直接复用的探针脚本

`tmp\probe_index.py` —— 打开工作副本索引 + BGE 编码 + 真实 query，
输出集合元信息、命中、耗时与峰值内存。运行方式：

```powershell
$env:HF_ENDPOINT="https://hf-mirror.com"
$env:HF_HOME="D:\CH02-01\search_indices\hf_home"
$env:HF_HUB_DISABLE_XET="1"
& "C:\Users\34353\anaconda3\envs\pytorch\python.exe" -u tmp\probe_index.py --top-k 5
```
