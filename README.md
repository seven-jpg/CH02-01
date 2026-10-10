# CH02-01：Meta CRAG-MM 多模态 RAG 课程项目

本项目以 KDD Cup 2025 Meta CRAG-MM 的公开数据、检索工具和评价代码为实验平台。当前目标是完成课程 M2 数据分析和 M3 纯文本单轮 RAG 基线，M4 再研究多模态、多轮上下文和图像扰动。

截至2026-10-10，B 已提交 M2 EDA、固定 manifest 和 smoke20/dev50/eval200 数据；C 已完成 dev50 上 top_k=1/3/5 的真实检索；D 已提交生成入口、smoke/dev 的 B0/B1 回答及 dev 的 k=1/3 B1 回答。三组 dev 检索与生成的严格验收通过，E 的正式评分入口和逐题结果尚未找到，完整实验仍未冻结。验收通过不代表答案正确。

当前固定基线仍为 `top_k=5`，不添加 `fetch_k`，尚未证明参数最优。最新结果检查见 [C/D 交付审查](docs/M3/retrieval_review/cd_generation_review.json)；组长电脑已准备官方 Web 索引/BGE，并在 RTX 4060 Laptop / 16 GB RAM 上完成真实 smoke20 和严格验收，见 [本地检索说明](docs/M3/local_retrieval_setup.md) 与 [本机验证记录](docs/M3/retrieval_review/local_environment_verification.json)。

## 研究问题与阶段范围

- **RQ1**：图像加文本检索相对纯文本检索，对答案准确性的影响。
- **RQ2**：全历史、摘要和滑动窗口对多轮回答的影响。
- **RQ3**：模糊、遮挡和低光照对多模态系统鲁棒性的影响。

M2 分析 Single-turn/Multi-turn。M3 仅用 Single-turn，B1 是“原始问题→官方 Web 文本检索→生成→答案”，B0 是建议增加的无检索对照。两组不输入图片、图片 URL、OCR、caption、视觉实体、历史、图像生成的 full_query 或参考答案。M3 初步对照不能直接回答完整 RQ1–RQ3。

## 当前代码和来源

| 路径 | 当前用途 |
| --- | --- |
| `scripts/check_artifacts.py` | A：产物验收 CLI |
| `src/contracts/m3.py` | A：JSON/schema、编号、哈希、状态的公共校验 |
| `requirements-integration.txt` | A：轻依赖，不部署模型或索引 |
| `requirements-integration.lock.txt` | 本机 Python3.12.9 实际验证的依赖版本 |
| `docs/M2_M3_execution/` | 五人任务、AI提示词、m3.v1协议、schema和预算方案 |
| `experiments/m3/freeze_record.json` | 待确认项，当前 `is_frozen=false` |
| `docs/M2/`、`docs/M3/` | 数据、报告和复现模板 |
| `external/CRAG-MM/` | 导入的官方参考代码，不是本组实验成果 |

本地根仓库初始化提交为 `78acf3abbb656e989b8732f62d0dce50104ca6f3`，提交信息为 `chore: initialize CH02-01 project`。`external/CRAG-MM` 没有独立 Git checkout；这个 SHA **不是已核实的上游官方版本**。导入来源的上游 commit 仍待核实，在冻结记录中补证据。

正式字段以 [统一接口](docs/M2_M3_execution/01统一接口与验收.txt) 和 [JSON schema](docs/M2_M3_execution/接口字段.schema.json) 为准。验收代码能检查结构、配对、哈希和状态；证据真实性、完整输入无泄漏及裁判可靠性还需要实际来源、requests、配置和人工核查。

## A 的 Windows 环境

只做 A 的轻量验收时，在仓库根目录的 PowerShell 中运行。推荐 Python3.11 独立环境；先用 `py -0p` 确认本机已有该版本。该验收步骤不需要 API 密钥、检索索引、CLIP/BGE 或生成模型权重。组长代跑 C 的检索使用另外的 `.venv-retrieval`，按上方本地检索说明操作。

```powershell
py -0p
py -3.11 -m venv .venv-integration
.\.venv-integration\Scripts\python.exe -m pip install -r requirements-integration.txt
.\.venv-integration\Scripts\python.exe scripts/check_artifacts.py --help
.\.venv-integration\Scripts\python.exe -m unittest discover -s tests -v
```

本机实际验证使用 Windows/Python3.12.9；推荐环境为3.11，但尚未在3.11实测。需要复用本机验证依赖时安装 `requirements-integration.lock.txt`。

可以立即运行合成开发包检查，验证入口能工作；它不会调用API，也不代表真实smoke通过：

```powershell
.\.venv-integration\Scripts\python.exe scripts/check_artifacts.py `
  --manifest fixtures/synthetic/integration/manifest.json `
  --questions fixtures/synthetic/integration/questions.jsonl `
  --answers fixtures/synthetic/integration/answers.jsonl `
  --metadata fixtures/synthetic/integration/metadata.jsonl `
  --evidence fixtures/synthetic/integration/evidence.jsonl `
  --predictions fixtures/synthetic/integration/predictions_b0.jsonl `
  --compare-predictions fixtures/synthetic/integration/predictions_b1.jsonl `
  --scores fixtures/synthetic/integration/scores_b0.jsonl `
  --compare-scores fixtures/synthetic/integration/scores_b1.jsonl `
  --report results/development/check_fixture.json
```

本机没有3.11时，先安装或使用已验证兼容的 Python，不把版本缺失误判为项目代码失败。直接调用虚拟环境的 Python 不要求改变 PowerShell 执行策略。

B 已提供真实 smoke 包，下面命令可执行数据包检查：

```powershell
.\.venv-integration\Scripts\python.exe scripts/check_artifacts.py `
  --manifest data/processed/m3/manifest.json `
  --questions data/processed/m3/smoke/questions.jsonl `
  --answers data/processed/m3/smoke/answers.jsonl `
  --metadata data/processed/m3/smoke/metadata.jsonl `
  --report results/m3/smoke/check_data.json
```

收到阶段产物后追加 `--evidence`、`--predictions`、`--scores`。`--subset` 可显式指定，也可推断。逐批使用 `--batch-ids`，完整集合验收不传它。questions/answers/metadata 可以是完整 subset，脚本先按批次筛选；阶段产物须完整覆盖本批编号。批次通过后还要检查合并后的 full subset。

进阶核查选项：

- `--requests`、`--compare-requests`：实际模型消息及证据使用记录。
- `--compare-predictions`、`--compare-scores`：配对基线工件。
- `--config STAGE=PATH`、`--run-meta STAGE=PATH`：可重复，STAGE 为 retrieval/generation/evaluation。
- `--group-metadata PATH`、`--group-questions PATH`：可重复，用于跨集合分组检查。
- `--require-provenance`：严格要求请求、配置和运行元数据可追溯。
- `--report PATH`：保存机器可读报告；详细用法以 `--help` 为准。

退出0表示所提供工件结构合规，仍须查看报告中的未检查项；退出1表示接口/编号/哈希/状态不一致；退出2表示结构通过但有技术失败。缺少真实 requests 时不能凭退出0宣称输入完全无泄漏。技术失败记录仍可供 E 独立评分入口读取并标为 unscored，不能因非零退出就删除失败题。

## 五台独立电脑的交接

使用同一小型代码仓库，各自在自己的电脑运行负责模块，通过 Git 与现有文件渠道交换产物，无共享电脑或端口服务要求。

| 人员 | 所需环境和职责 | 交接 |
| --- | --- | --- |
| A | Python/Git/轻量验收依赖，维护接口、冻结、检查与材料 | 接收四人产物；各人交自己的方法与结果，A负责合并 |
| B | 数据、表格、图片和绘图库，分批读图做 EDA | questions给A/C/D/E；answers给A/E；metadata给A/E；先交20条真实smoke |
| C | 官方检索包、索引和编码模型，在自己电脑真实搜索 | evidence及来源/版本/资源测量给D/A/E |
| D | 统一提供商的API客户端，B0/B1生成及demo | B0只等B；B1再等C。预测、实际messages、调用记录给E/A |
| E | 轻量评分代码、官方tokenizer、裁判客户端 | 接B的问题/答案/metadata和D的预测，交评分、汇总与复核给A |

B 下载 Single/Multi **QA数据**；C 在 M3 只准备 Web索引/BGE，做仅文本的适配层。完整统一管线还会初始化视觉部分，不能直接当轻量入口；本机 16GB RAM 已通过完整 Web 索引 smoke20 查询，但冷加载较慢且内存余量较小，M4 再测图像资源。E 不初始化搜索、不下载索引。各人提供自己的实际依赖版本，不要求五台装完整 vLLM；A 代跑 C 时复用同一配置与独立批次产物。

## 统一运行入口

以下为统一入口约定；C 的 retrieve 与 D 的 generate 已实现并提交真实结果，E 的 evaluate 仍为待实现入口：

```text
python preprocessing/prepare_data.py --config experiments/m3/data.json --output-dir data/processed/m3
python preprocessing/eda.py --config experiments/m3/data.json --output-dir results/eda
python scripts/retrieve.py --questions QUESTIONS --manifest MANIFEST --config experiments/m3/retrieval.json --output EVIDENCE
python scripts/generate.py --questions QUESTIONS --manifest MANIFEST --baseline B0 --config experiments/m3/generation.json --output PREDICTIONS
python scripts/generate.py --questions QUESTIONS --manifest MANIFEST --baseline B1 --evidence EVIDENCE --config experiments/m3/generation.json --output PREDICTIONS
python scripts/evaluate.py --questions QUESTIONS --answers ANSWERS --metadata METADATA --manifest MANIFEST --predictions PREDICTIONS --config experiments/m3/evaluation.json --output-dir OUTPUT
```

C/D 已实现入口的 `--help` 不需密钥、不下载模型或索引。C/D 支持同一批次规则，E 也应遵循该约定；批次沿用同一 manifest、阶段配置和对应 run ID，最后按去重逐题记录重算，不能平均批次百分比。完整 B1 运行说明见 [D 生成说明](docs/M3/generation_run.md)。

## 数据、配置与结果

```text
data/processed/m3/manifest.json
data/processed/m3/<smoke|dev|eval>/{questions,answers,metadata}.jsonl
results/m3/<subset>/evidence.jsonl
results/m3/<subset>/predictions_b0.jsonl、predictions_b1.jsonl
results/m3/<subset>/scores_b0.jsonl、scores_b1.jsonl、summary.csv
results/m3/<subset>/run_meta_*.json、requests_b0.jsonl、requests_b1.jsonl
results/eda/                         EDA图表、范围与失败记录
fixtures/synthetic/                 开发样例，不混入正式数据/结果
```

目标20/50/200、seed42是方案建议。B按session、可识别共享图像和重复问题分组，A确认实际数量与编号。尽早确定三个集合完整ID清单并写manifest，先交smoke，后续dev/eval沿用同一manifest。manifest原字节SHA256写入所有逐题行；变更时发布一致新包并重新验收，不能只改旧结果哈希。

D 已提交使用 NVIDIA `meta/llama-3.2-11b-vision-instruct` 的真实生成结果和请求记录，B0/B1 使用相同模型与公共参数，仅发送文本。当前审查核实了请求和文件哈希，未独立验证提供商账号及课程在线推理许可。E 的裁判、官方 tokenizer 和正式评分仍待提交，详见 [冻结记录](experiments/m3/freeze_record.json)。

使用相应提供商时，变量名为 `NVIDIA_API_KEY` 或 `CLOUDFLARE_ACCOUNT_ID` / `CLOUDFLARE_API_TOKEN`；E可能还需tokenizer访问凭证。A检查不读取这些变量。实际调用者在本机配置，密钥不写JSON、Git、日志或报告。

当前仓库已跟踪 manifest、处理后的问题/答案/metadata 及审查过的检索结果。`.gitignore` 忽略 `search_indices/`、`checkpoints/`、虚拟环境及密钥文件；大型索引和模型不进 Git。传输和提交后仍须核对数据包版本与原始字节哈希。

C 的 empty是成功搜索零证据，error是技术故障。D B1在empty时可正常回答，error/missing默认blocked；API故障/空响应不能变拒答。usage始终对象，未返回用量时两个token值为null。

E先按官方tokenizer截75 tokens，保存实际评分文本。生成error/blocked为unscored，裁判失败为error，均不算WRONG或MISSING。结果报告N_fixed、N_generated、N_scored和覆盖率；准确率C/N_scored、幻觉率W/N_scored、拒答率M/N_scored、Truthfulness=(C-W)/N_scored，分母0时比例null。替代裁判与汇总规则差异明确说明，不能直接声称排行榜同口径。未补齐集合时公开缺失ID，共同评分子集比较只作为补充。

文档模板：

- [M2 数据与EDA说明](docs/M2/data_eda_template.md)
- [M3 中期报告](docs/M3/midterm_report_template.md)
- [M3 复现记录](docs/M3/reproduction_record_template.md)

官方来源：[CRAG-MM](https://github.com/facebookresearch/CRAG-MM)、[Single-turn QA](https://huggingface.co/datasets/crag-mm-2025/crag-mm-single-turn-public)、[Multi-turn QA](https://huggingface.co/datasets/crag-mm-2025/crag-mm-multi-turn-public)。实际版本以运行记录为准。
