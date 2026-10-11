# E评价模块运行说明

结果解释和最终成绩路径见[评价与结果分析](../E_evaluation.md)。以下命令均从项目根目录执行。离线比较与日志审计不需要API密钥或分词器；新输入预检、75-token截断重算和付费评分需要固定来源的分词器。

## 环境与入口

已验证环境为Miniforge的`ch0201-e-score`，Python 3.11.17。其他成员可使用满足依赖的独立环境，无需沿用个人环境名称。

```powershell
conda activate ch0201-e-score
$env:PYTHONNOUSERSITE='1'
$env:PYTHONUTF8='1'
$env:PYTHONIOENCODING='utf-8'
python -m pip install -r requirements-evaluation.txt
```

`requirements-evaluation.txt`固定六项直接依赖；`requirements-evaluation.lock.txt`和`.lock.json`保存完整环境快照。评分入口为`scripts/evaluate.py`，比较与复核入口为`scripts/review_evaluation.py`，审计与合并入口为`scripts/evaluation_records.py`。本次配置为`experiments/m3/evaluation_4096.json`；`evaluation.json`为历史1024配置。

## 离线复现六组比较

以下命令只读取已有文件，输出目录应使用未用过的名称。

```powershell
python scripts/review_evaluation.py compare `
  --scores smoke_B0=results/m3/smoke/e_paid_4096_v1/b0/scores_b0.jsonl `
  --scores smoke_B1_k5=results/m3/smoke/e_paid_4096_v1/b1/scores_b1.jsonl `
  --scores dev_B0=results/m3/dev/e_paid_4096_v1/b0/scores_b0.jsonl `
  --scores dev_B1_k1=results/m3/dev_topk_sweep_run1/top_k_1/e_paid_4096_v1/b1/scores_b1.jsonl `
  --scores dev_B1_k3=results/m3/dev_topk_sweep_run1/top_k_3/e_paid_4096_v1/b1/scores_b1.jsonl `
  --scores dev_B1_k5=results/m3/dev/e_paid_4096_complete_v1/b1/scores_b1.jsonl `
  --output-dir results/m3/e_comparison_reproduction
```

输出`completed_summary.csv`和`completed_comparisons.json`，应与[最终汇总](complete_v1/README.md)一致。smoke比较共同20题，dev比较共同50题。成对比较中的`first_group`、`second_group`为组名，`first`、`second`为对应指标。

每套scores必须保留同目录的`run_meta_eval_b0.json`或`run_meta_eval_b1.json`及其中引用的输入输出文件。元数据中的相对路径以其所在目录解析；比较入口核验原始字节SHA256、五类当前输入的哈希覆盖、配置、运行身份、范围、成功/失败计数及确定性规则标签。缺少运行记录、文件改写或规则矛盾时退出非零，所有组别通过后才写比较结果。

比较不调用API、不加载tokenizer或凭证，不重新判断语义。运行记录提供的是保存时的校验依据；哈希一致本身不能代替独立语义复核。完整评分时的[复现脚本](complete_v1/reproduce.ps1)作为原始快照保留，当前操作以本说明为准。

## 请求日志审计与公共验收

```powershell
python scripts/evaluation_records.py audit --journal results/m3/e_judge_cache_4096_v1.jsonl --journal results/m3/e_judge_cache_4096_manual_retry_v1.jsonl --output results/m3/e_request_audit_reproduction.json
```

预期91次尝试、90份不同输入、90次成功、1次失败，`total_tokens=236135`。两份日志联合统计，保留原失败和手动重试。审计只根据日志核对调用，不据此认定授权状态，因此`authorization_verified`默认false。

以dev k5最终合并成绩为例：

```powershell
python scripts/check_artifacts.py --manifest data/processed/m3/manifest.json --questions data/processed/m3/dev/questions.jsonl --answers data/processed/m3/dev/answers.jsonl --metadata data/processed/m3/dev/metadata.jsonl --predictions results/m3/dev/predictions_b1.jsonl --requests results/m3/dev/requests_b1.jsonl --evidence results/m3/dev/evidence.jsonl --scores results/m3/dev/e_paid_4096_complete_v1/b1/scores_b1.jsonl --config evaluation=experiments/m3/evaluation_4096.json --run-meta evaluation=results/m3/dev/e_paid_4096_complete_v1/b1/run_meta_eval_b1.json
```

预期退出0、`valid=true`、`errors`为空。其他五组按主说明的路径替换subset、预测目录、baseline及scores/run_meta。公共验收不重新判断语义，其未核实范围见`unverified_checks`。240行分词器与已保存响应重算证据见[评分验证快照](complete_v1/verification.json)，最新比较校验见[比较验证记录](validation/comparison_v1.json)。

## 分词器与本地配置

默认文件位置为`.cache/tokenizers/llama-3.2-1b-instruct/tokenizer.json`。只需分词器文件，不需模型权重。交付包不包含缓存、真实`.env`或API凭证。

|项目|固定值|
|---|---|
|官方逻辑标识|`meta-llama/Llama-3.2-1B-Instruct`|
|官方版本|`9213176726f574b556790deb65791e0c5aa438b6`|
|公开副本仓库|`onnx-community/Llama-3.2-1B-Instruct-ONNX`|
|公开副本版本|`f91ba3ec08fde6b664d0b1a02cf4305b53a41141`|
|官方与副本Git blob ID|`5cc5f00a5b203e90a27a3bd60d1ec393b07971e8`|
|文件大小|9,085,657字节|
|SHA256|`79e3e522635f3171300913bb421464a87de6222182a0570b9b2ccba2a964b2b4`|

[固定版本下载链接](https://huggingface.co/onnx-community/Llama-3.2-1B-Instruct-ONNX/resolve/f91ba3ec08fde6b664d0b1a02cf4305b53a41141/tokenizer.json)。下载后核验大小与SHA256，来源记录见[分词器核验](review/tokenizer_provenance.json)。许可和使用政策的来源版本也记录在该文件中。缺文件、哈希不一致或加载失败时程序停止，不自动下载。

分词器使用`tokenizers.Tokenizer.from_file`，沿用官方`enable_truncation(max_length=75)`、`encode_batch`与`decode`的默认行为，包括默认特殊token；不套聊天模板或按字符截取。保留原始回答和实际评分文本。已用官方截断函数对240条真实预测及7个边界样例核验。

本地设置写入仓库根目录`.env`，进程环境优先：

```dotenv
JUDGE_PROVIDER=autodl
JUDGE_BASE_URL=https://www.autodl.art/api/v1
JUDGE_MODEL=DeepSeek-V4.1-Flash
JUDGE_API_KEY=
RESPONSE_TOKENIZER_PATH=.cache/tokenizers/llama-3.2-1b-instruct/tokenizer.json
RESPONSE_TOKENIZER_SHA256=79e3e522635f3171300913bb421464a87de6222182a0570b9b2ccba2a964b2b4
```

相对分词器路径以项目根目录解析。本地加载不需要`HF_TOKEN`。凭证不写入源码、日志、成绩或配置哈希；运行配置若与固定评价方法冲突，会在请求前停止。

## 新输入预检与后续评分

下面示例创建新预检目录，不产生正式成绩或API调用：

```powershell
python scripts/evaluate.py --manifest data/processed/m3/manifest.json --questions data/processed/m3/smoke/questions.jsonl --answers data/processed/m3/smoke/answers.jsonl --metadata data/processed/m3/smoke/metadata.jsonl --predictions results/m3/smoke/predictions_b1.jsonl --config experiments/m3/evaluation_4096.json --output-dir results/m3/smoke/e_new_precheck/b1 --run-id e-new-precheck-smoke-b1 --dry-run
```

输出目录与run_id应未使用。输出包括`prepared`、`pending_judge`、`deterministic`、`provenance`、`precheck`及`run_identity`，不输出正式scores。现有smoke B1预期20条，其中8条规则拒答、12条语义输入。

问题、参考、metadata和预测按`interaction_id`关联。D历史运行记录中的机器路径通过明确提供的本地文件名及原字节哈希解析，原记录保持不变。检查覆盖实际生成请求，包括E批次未选中的行；生成计数对应完整预测，E批次范围另记。

正式评分必须同时设置`--allow-paid-api`和正整数`--max-api-requests`。限额按单个运行计数，多批累计量通过联合日志审计核对。发送前持久化`started`；SDK和应用自动重试均为0，首次技术失败后停止后续新调用。失败或未完成请求不自动重发，手动重试须核对历史尝试并另作记录。

`--resume`要求输入、源码、配置、模式、run_id和缓存路径一致，并先核验已有最终产物。源码发生变化后需另建目录。缓存键覆盖manifest、ID、问题、参考、实际75-token文本及完整方法配置，可在相同输入的组间复用响应，但每组scores仍保留自身生成来源；1024与4096配置不共用缓存键。

退出0表示相应模式完成，退出1表示输入、配置或结构错误，正式遍历后仍存在技术失败时退出2。锁由操作系统释放，锁文件存在不代表进程仍运行。

## 测试与复核资料

运行测试前，将`E_TEST_WORKDIR`设置为允许保存测试过程材料的目录，再执行：

```powershell
python -X utf8 -m unittest discover -s tests -p test_evaluation.py -v
```

未设置该变量时部分测试会跳过，不能将跳过计为通过。47项E测试的API均为模拟，夹具标记为synthetic；真实六组的公共验收与240行响应重算单独记录。

抽样、隐藏组别的复核表、映射及AI意见收在`review/`，材料清单见[资料索引](README.md)。这些记录包含30条AI辅助复核，人工核查数为0。
