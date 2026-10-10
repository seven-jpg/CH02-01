# C 参数确认与接手说明（2026-10-10）

当前 M3 采用已经实际跑通的 `top_k=5`、无重排、无实时网页抓取。`fetch_k` 没有实现，不添加到配置。这个选择是固定基线，**没有证明 top_k=5 的回答质量最优**。完整实验尚未冻结，生成与评价仍需要 D/E 的真实结果。

本次只检查仓库已有结果并准备代码；组长电脑没有官方 Web 索引和 BGE 模型，没有重新检索、调用生成/裁判 API、购买资源或下载大模型。

## 已完成的检查

来源是 C 提交到 main 的 `7b79e64050420026d2d2feed8fe34ff37b709a39`。保留原始问题、manifest、配置、证据、run_meta 的字节与历史运行编号，不改写 C 的 `89e809d:dirty` 运行提交声明。其实际源码哈希记录用于追踪原始实现。

dev50 全部检索成功，共 214 条 hits。每题命中数量为：

| 实际 hits | 题数 |
|---|---:|
| 1 | 1 |
| 2 | 2 |
| 3 | 5 |
| 4 | 16 |
| 5 | 26 |

当前实现查询 5 个原始 chunk，再按页面去重，因此 24 题不足 5 条是允许的。49 条 hits 的文本与标题相同，涉及 25 道题；3 道题有完全相同的标准化证据文本。分数全部是 similarity，但高分不能证明目标实体正确，也不能证明片段足以回答。

按 manifest 每隔 5 条，加最低 top1 分数样本，检查了 11 道题的前两条证据（22 条）。检查范围为原问题、缓存标题/URL、每条正文前 400 字符；未查看答案或图片、未访问实时网页。例如手机颜色题检到 Galaxy S23 资料，但原问题没有型号；创始人题的前两条文本都只有 `Company`，来自不同公司。详细观察和边界见 [source_content_review.json](retrieval_review/source_content_review.json)。这些是定性内容抽查，不能据此给出准确率、Recall@k 或认定图中的真实对象。

复现 dev 缓存诊断：

```powershell
python scripts/audit_retrieval.py --manifest data/processed/m3/manifest.json --questions data/processed/m3/dev/questions.jsonl --evidence results/m3/dev/evidence.jsonl --config experiments/m3/retrieval.json --output-dir docs/M3/retrieval_review
```

该入口只读问题、配置和缓存证据，不加载模型/索引或答案。既有输出不同会报错，使用新的输出目录保存另一次诊断。摘要在 [diagnostic.json](retrieval_review/diagnostic.json)，参数记录在 [retrieval_decision.json](../../experiments/m3/retrieval_decision.json)。

## 不同电脑怎样验收 C 的结果

C 的 run_meta 记录了他电脑的 `D:\CH02-01` 路径。使用显式路径映射找到组长电脑中的对应文件，仍逐个校验原始字节 SHA256；不编辑原记录、不重写哈希。以下命令从仓库根目录运行，PowerShell 会取当前绝对路径：

```powershell
$repoRoot = (Get-Location).Path
python scripts/check_artifacts.py --manifest data/processed/m3/manifest.json --questions data/processed/m3/dev/questions.jsonl --answers data/processed/m3/dev/answers.jsonl --metadata data/processed/m3/dev/metadata.jsonl --evidence results/m3/dev/evidence.jsonl --config retrieval=experiments/m3/retrieval.json --run-meta retrieval=results/m3/dev/run_meta_retrieval.json --path-map "D:\CH02-01=$repoRoot" --group-metadata data/processed/m3/smoke/metadata.jsonl --group-metadata data/processed/m3/eval/metadata.jsonl --group-questions data/processed/m3/smoke/questions.jsonl --group-questions data/processed/m3/eval/questions.jsonl --require-provenance --report docs/M3/retrieval_review/dev_acceptance.json
```

smoke 的对应命令将主要输入及 run_meta 路径的 `dev` 改为 `smoke`，其它集合的分组输入改为 `dev` 和 `eval`。结构验收不代表已经重新执行检索，来源真实性和答案评分还有各自的验证边界。

## 如果需要真正比较 top_k

先准备三个独立的 dev 运行计划，不需要安装检索依赖：

```powershell
python scripts/sweep_retrieval.py --manifest data/processed/m3/manifest.json --questions data/processed/m3/dev/questions.jsonl --config experiments/m3/retrieval.json --output-dir results/m3/dev_topk_sweep --top-k 1 3 5
```

这条命令只生成配置和命令，不产生真实检索结果、不决定最优参数。真实运行需要有固定版本官方 Web 索引的可写工作副本、固定版本 BGE 编码器、可用检索环境。在有资源的电脑上增加：

```powershell
python scripts/sweep_retrieval.py --manifest data/processed/m3/manifest.json --questions data/processed/m3/dev/questions.jsonl --config experiments/m3/retrieval.json --output-dir results/m3/dev_topk_sweep_run1 --top-k 1 3 5 --index-path "D:\CH02-01\search_indices\index_working" --run
```

`--index-path` 换成执行电脑的真实可写目录。不要将 Hugging Face 校验快照直接作为 Chroma 工作库。安装参考 `requirements-retrieval.txt` 是 C 原电脑的运行记录，不能视为组长环境已经验证；CUDA/Python 依赖需在独立环境中确认。`--help`、默认准备入口不加载重库、不下载资源。

每组保持相同 dev ID、模型、提示、温度、证据清理和 token 预算；只比较 top_k。D 根据每组 evidence 生成 B1 回答，E 用同一评价配置评分，比较准确率、错误/拒答比例、覆盖率与耗时，再由 A 记录选择。没有 D/E 结果，不能仅用相似度或非空 hits 数选“最佳”。

现有 top5 缓存取前 1/3/5 条，可以用于 D 的提示证据数量对比，总计分别使用 50/146/214 条 hits；必须标注为“固定 top5 检索结果下的证据数量消融”。这不等于重新执行 Chroma `n_results=1/3/5`，不能修改 C 的原配置哈希冒充新的检索结果。

## 接下来谁做什么

- **A（本次接手）**：确认固定基线 top_k=5，交付审查记录、兼容验收与实验准备代码；收齐 D/E 设置后记录完整实验冻结。
- **D**：立即使用仓库中 smoke/dev 的真实 evidence 联调；负责 HTML/重复文本清理、证据长度预算，保存 requests 和实际 evidence_used。不能把只有标题的片段当网页全文，也不能把 API 故障写成正常拒答。
- **E**：对 D 的真实回答评分并公开评分覆盖率；如需选择 k，提供相同 dev 样本上的成对比较。C 来源抽查和 E 的答案/裁判校准是两项工作。
- **有检索资源的执行者**：如需扫参，按准备的命令真实运行 dev；配置最终确认后再运行 eval200。组长还未复制资源，因此本次没有 eval200 新证据。

固定基线不做扫参时，确认最终配置后可直接使用原 CLI 跑 eval：

```powershell
python scripts/retrieve.py --questions data/processed/m3/eval/questions.jsonl --manifest data/processed/m3/manifest.json --config experiments/m3/retrieval.json --index-path "D:\CH02-01\search_indices\index_working" --output results/m3/eval/evidence.jsonl
```

eval 只测成绩，不依据 eval 表现再挑参数。配置改动必须新建独立结果目录并保留旧结果。现阶段无需为了“最优”阻塞 D/E 已有证据的联调。

可发群里的消息：

> C 的参数确认我接手了。M3 先采用已跑通的 top_k=5，不加 fetch_k，报告明确这是固定基线，尚未证明最优。D 可以立即用仓库现有 smoke20/dev50 evidence 联调，做好去重、限长和真实请求记录；E 接回答评分。我已准备 dev 上 1/3/5 的真实检索比较脚本，但我的电脑还没有索引，暂未执行扫参或 eval200。若需要比较，等有索引的电脑运行，再结合 D/E 的同口径 dev 分数选择；确认最终配置后跑 eval200。
