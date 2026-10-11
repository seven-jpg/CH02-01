# M3 参数决定与最终评测交接

2026-10-11，A 根据 D/E 已完成的同一 dev50 比较，确定 B1 使用 `top_k=1`，不加 `fetch_k`、重排或实时网页抓取。检索、生成和评分配置已在运行 eval 检索前固定；组长电脑完成 smoke20 和 eval200 的真实检索，220 条均成功并通过严格验收。D 接着生成 eval 的 B0/B1，E 再评分；目前还没有 eval 的回答质量成绩。

## 参数为什么选 1

三组使用相同 50 个问题、生成模型、提示、证据预算和 4096 裁判配置，均完整生成、完整评分，无最终技术失败。

| top_k | 答对 C | 答错 W | 拒答 M | 正确率 | 错误率 | Truthfulness |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| **1** | **10** | **17** | 23 | **20%** | **34%** | **−0.14** |
| 3 | 11 | 20 | 19 | 22% | 40% | −0.18 |
| 5 | 9 | 24 | 17 | 18% | 48% | −0.30 |

本次工程选择优先比较 `Truthfulness=(C−W)/N_scored`，并列时选错误率低者，再选较小 k。该规则在本次决定时公开，没有事先预注册。k3 比 k1 多答对 1 题、也多答错 3 题；k5 答对更少、答错更多，因此选 k1。若只追求正确率，k3 是本次样本中的第一；课程报告应同时展示正确率、错误率和 Truthfulness，不能把它们混为一个指标。50 题只能支持本次开发集选择，不能证明全局最优或统计显著。

B0 在 dev 上为 C=0、W=1、M=49，Truthfulness=−0.02，但几乎完全拒答。保留它作为控制组，不能用 B0 代替课程要求的纯文本 RAG。R001 的机器 CORRECT 与 AI 复核 WRONG 有分歧，原成绩不改；即使人工最终改判 WRONG，k1 的 Truthfulness 为 −0.18，与 k3 并列，仍按较低错误率选 k1。独立人工复核目前为 0 条。

逐题成绩与旧失败记录见 [E 完成结果](evaluation_paid_4096_v1/complete_v1/README.md)，独立验收见 [参数审计](retrieval_review/parameter_selection_review.json)。dev k5 必须用 `results/m3/dev/e_paid_4096_complete_v1/b1/scores_b1.jsonl`，旧 `e_paid_4096_v1/b1` 是部分结果。

## 固定配置与 C 的交付

| 阶段 | 最终配置 | 固定内容 |
| --- | --- | --- |
| C 检索 | `experiments/m3/retrieval_selected.json` | top_k=1，官方 Web 文本索引，固定 BGE；原始 query，无图片或参考答案 |
| D 生成 | `experiments/m3/generation.json` | NVIDIA `meta/llama-3.2-11b-vision-instruct`，纯文本调用，temperature=0，top_p=1，max_tokens=100，seed=42，证据预算1500（原字符估算方法） |
| E 评分 | `experiments/m3/evaluation_4096.json` | AutoDL `DeepSeek-V4.1-Flash`，temperature=0，max_tokens=4096，官方 tokenizer 截前75 tokens，SDK及应用自动重试0 |

[操作参数冻结记录](../../experiments/m3/parameter_freeze.json) 保存精确配置哈希、manifest 哈希和冻结时间。`experiments/m3/retrieval.json` 及旧 k5 结果保留，不能覆盖。整个项目的最终验收跟踪仍在 [freeze_record.json](../../experiments/m3/freeze_record.json)，操作参数固定不等于 M3 所有工作完成。

| C 新结果 | 成功数 | 首次运行墙钟时间 | 严格验收 |
| --- | ---: | ---: | --- |
| `results/m3/selected_k1_run1/smoke/` | 20/20 | 50.711秒 | `acceptance_retrieval.json`，通过 |
| `results/m3/selected_k1_run1/eval/` | 200/200 | 27.548秒 | `acceptance_retrieval.json`，通过 |

每个目录交付 `evidence.jsonl`、`run_meta_retrieval.json`、`acceptance_retrieval.json`。实际使用组长 RTX 4060 Laptop 8GB、16GB RAM，CUDA 检索，eval 进程峰值内存约8794MB。预热和索引初始化单独记录，不能用检索耗时声称完整系统满足比赛10秒限制。这些是检索成功率，尚不是回答正确率。D/E 拉取这些小文件即可，不需要下载检索索引，也无需为了此次评测租 GPU 服务器。

## D 现在做什么

拉取本次提交，在项目根目录使用原生成环境和本机凭证，保留原配置。dev 已完成，不重跑；k1 的 dev50 已验证完整生成评分链，新的 smoke20 只需查看输入验收，无需额外重复调用20题。

```powershell
git pull --ff-only
# 在已安装 requirements-generation.txt 的环境执行
$Out = 'results/m3/selected_k1_run1/eval'
python scripts/generate.py --questions data/processed/m3/eval/questions.jsonl --manifest data/processed/m3/manifest.json --baseline B0 --config experiments/m3/generation.json --output "$Out/predictions_b0.jsonl" --requests-output "$Out/requests_b0.jsonl" --run-meta-output "$Out/run_meta_b0.json" --run-id eval-k1-run1-b0
if ($LASTEXITCODE -ne 0) { throw 'B0 generation failed; retain records and inspect errors.' }
python scripts/generate.py --questions data/processed/m3/eval/questions.jsonl --manifest data/processed/m3/manifest.json --baseline B1 --evidence "$Out/evidence.jsonl" --config experiments/m3/generation.json --output "$Out/predictions_b1.jsonl" --requests-output "$Out/requests_b1.jsonl" --run-meta-output "$Out/run_meta_b1.json" --run-id eval-k1-run1-b1
if ($LASTEXITCODE -ne 0) { throw 'B1 generation failed; retain records and inspect errors.' }
```

D 交付两份各200条的 predictions、requests 和 generation run_meta，即以上6个新增文件，再提交 Git。保持原问题不改写 this，不加图片、caption、OCR、full_query、历史或参考答案。正常 `I don't know` 是成功生成；API故障不能伪装成拒答。失败需保留、说明和恢复；用完全相同的命令可恢复成功行，失败行会重新尝试，不换模型/提示/参数，不用 `--no-resume` 覆盖旧产物。B0/B1可在不覆盖各自输出的前提下分别运行，但要遵守原账号限流和预算。

A 已离线构造并核验这两组共400条请求，B1仅使用每题对应的1条证据，最多约643个估计tokens，未超过原1500预算。离线预检没有生成回答；CLI退出2是因为全部标为 `dry_run_no_api_call`，独立输入审计通过。预检产物保存在本机ignored目录，不混入正式结果。

API的身份、限额和费用由调用者沿用已有账号；本次 A 的参数选择和本机检索新增 API 调用为0。不要把密钥或本机 `.env` 提交 Git。

## E 接到 D 后做什么

先拉取 D 的6个文件。沿用已完成 dev 的 E 环境与本机 `.env`，保持 `JUDGE_PROVIDER=autodl`、`JUDGE_MODEL=DeepSeek-V4.1-Flash`、同一 base URL 和已核验 tokenizer。第三方裁判与官方 GPT-4o 不同，报告不能声称排行榜同口径。代码已通过47项E测试，A的完整192项测试也通过，无需为复现已有dev成绩重新付费。

先离线预检两组（不会调用API），两组共用新日志，预检目录与正式目录分开：

```powershell
# 在已安装 requirements-evaluation.txt 的环境执行
$Out = 'results/m3/selected_k1_run1/eval'
foreach ($B in @('b0', 'b1')) {
  $EvalArgs = @('--questions', 'data/processed/m3/eval/questions.jsonl', '--answers', 'data/processed/m3/eval/answers.jsonl', '--metadata', 'data/processed/m3/eval/metadata.jsonl', '--manifest', 'data/processed/m3/manifest.json', '--predictions', "$Out/predictions_$B.jsonl", '--generation-run-meta', "$Out/run_meta_$B.json", '--config', 'experiments/m3/evaluation_4096.json', '--cache', "$Out/evaluation/judge_journal.jsonl")
  python scripts/evaluate.py @EvalArgs --output-dir "$Out/precheck/$B" --run-id "eval-k1-run1-precheck-$B" --dry-run
  if ($LASTEXITCODE -ne 0) { throw "E precheck failed: $B" }
}
```

确认 `precheck.json` 的 `N_fixed=200`、生成覆盖率和待请求数，核对账号剩余预算后执行正式评分。拒答/精确匹配可由规则判断，其余才调用裁判；下面200是每组请求上限，并不表示一定消耗200次。第一次正式运行不要加 `--resume`：

```powershell
foreach ($B in @('b0', 'b1')) {
  $EvalArgs = @('--questions', 'data/processed/m3/eval/questions.jsonl', '--answers', 'data/processed/m3/eval/answers.jsonl', '--metadata', 'data/processed/m3/eval/metadata.jsonl', '--manifest', 'data/processed/m3/manifest.json', '--predictions', "$Out/predictions_$B.jsonl", '--generation-run-meta', "$Out/run_meta_$B.json", '--config', 'experiments/m3/evaluation_4096.json', '--cache', "$Out/evaluation/judge_journal.jsonl")
  python scripts/evaluate.py @EvalArgs --output-dir "$Out/evaluation/$B" --run-id "eval-k1-run1-$B" --allow-paid-api --max-api-requests 200
  if ($LASTEXITCODE -ne 0) { throw "E scoring stopped: $B; preserve the failure and inspect before resuming." }
}
```

若付费运行中断，保留请求日志、原失败和所有已评分行。先审查原因；同一身份恢复才加 `--resume`，具体失败输入按已有恢复流程处理，不能切换到另一个裁判/预算后混合成绩。

E 交付每组 `scores_b0/b1.jsonl`、`summary.csv`、`run_meta_eval_b0/b1.json`、预检/来源/请求日志及费用用量审计。再从同一完整200题逐题重算 B0/B1 和成对差异，报告 N_fixed、N_generated、N_scored、覆盖率、正确/错误/拒答率、Truthfulness及技术失败。不能平均批次百分比。现有 `review_evaluation.py compare` 的组名映射针对 smoke/dev；新增 eval 比较时需扩展映射并验收，或使用 A 的通用 `check_artifacts.py --compare-predictions --compare-scores`，不能套用旧 dev 的样本数。

## A 的最终验收与报告

D/E分别完成后交Git；A用固定manifest核对完整200个ID、输入输出哈希、同一配置和真实请求，把成对评分并入中期报告。可用以下通用验收（本机路径不同时将映射右侧设为自己的项目根目录）：

如果 D/E 的元数据保存了其他电脑的绝对项目路径，按元数据中的项目根再追加 `--path-map OLD=本机项目根`。每个不同来源根各加一条映射；不要改写原元数据、哈希或成绩来绕过检查。

```powershell
$Out = 'results/m3/selected_k1_run1/eval'
python scripts/check_artifacts.py --manifest data/processed/m3/manifest.json --questions data/processed/m3/eval/questions.jsonl --answers data/processed/m3/eval/answers.jsonl --metadata data/processed/m3/eval/metadata.jsonl --evidence "$Out/evidence.jsonl" --predictions "$Out/predictions_b1.jsonl" --requests "$Out/requests_b1.jsonl" --scores "$Out/evaluation/b1/scores_b1.jsonl" --compare-predictions "$Out/predictions_b0.jsonl" --compare-requests "$Out/requests_b0.jsonl" --compare-scores "$Out/evaluation/b0/scores_b0.jsonl" --config retrieval=experiments/m3/retrieval_selected.json --config generation=experiments/m3/generation.json --config evaluation=experiments/m3/evaluation_4096.json --run-meta "retrieval=$Out/run_meta_retrieval.json" --run-meta "generation=$Out/run_meta_b1.json" --run-meta "generation=$Out/run_meta_b0.json" --run-meta "evaluation=$Out/evaluation/b1/run_meta_eval_b1.json" --run-meta "evaluation=$Out/evaluation/b0/run_meta_eval_b0.json" --path-map "D:\jqxxxxq\CH02-01=$((Get-Location).Path)" --require-provenance --group-metadata data/processed/m3/smoke/metadata.jsonl --group-metadata data/processed/m3/dev/metadata.jsonl --group-questions data/processed/m3/smoke/questions.jsonl --group-questions data/processed/m3/dev/questions.jsonl --report "$Out/acceptance_complete.json"
if ($LASTEXITCODE -ne 0) { throw 'Final acceptance failed; inspect the retained report.' }
```

运行期间不要改变 eval 问题、k、提示、证据预算或裁判来选最好看的结果。把已发现的30条复核材料分给团队做独立人工检查，保留机器成绩和人工意见各自版本。报告应解释：纯文本检索在视觉指代问题上容易检索错对象，B1带来部分正确回答也增加错误，M4通过多模态对照检验图像的作用。源代码上游版本、API模型不可变版本与人工裁判校准仍按冻结跟踪记录如实说明。

Git属性保留评分与新检索产物的原字节，避免跨电脑换行导致哈希不一致；旧校准的两份 `summary.csv` 也恢复为原元数据所记录的CRLF字节，CSV数值和旧成绩不变。官方评价源码使用仓库已有LF版本，与E固定源码哈希一致，不改评价逻辑。

## 发群里的交接消息

> A已经根据同一dev50的D/E实测结果把top_k定为1，优先比较Truthfulness，同时报告正确率和错误率。k1=10对17错23拒答，k3=11对20错19拒答，k5=9对24错17拒答。本机k1 smoke20+eval200检索已完成并验收通过，证据在results/m3/selected_k1_run1/。D拉取后按本文命令用原generation.json跑eval200的B0、B1，交predictions+requests+run_meta共6个文件；E收到后用evaluation_4096.json先dry-run再正式评分，交逐题分数、汇总和请求审计。我最后验收并整合报告。dev不用重跑，不加fetch_k，不用eval反过来调参。
