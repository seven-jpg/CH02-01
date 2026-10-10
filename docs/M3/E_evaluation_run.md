# E 评分程序运行与交接说明

日期：2026-10-11。适用范围：E 的评分模块与本机环境。全组无需采用 Miniforge，也无需安装检索索引、模型权重或 vLLM。

本次交付完成离线实现与验证，六套现有预测均已预检。真实裁判 API 请求为 **0**。人工核查为 **0/30**；AI 辅助建议不计人工核查。eval200 尚无预测，不能提供正式成绩。课程 M3 所需的初步准确率仍待真实语义评分与人工校准，不能把本次预检当作 M3 评价全部完成。

## 文件入口

|文件|作用|
|---|---|
|`src/evaluation/score.py`|官方拒答/精确匹配、75-token截断、裁判适配、持久化响应缓存、汇总与成对比较|
|`src/evaluation/inputs.py`|Schema、ID、哈希、数据来源和D请求记录校验|
|`scripts/evaluate.py`|组内约定评分CLI，支持批次、离线预检、付费保护与恢复|
|`scripts/review_evaluation.py`|六组预检、去重、盲审抽样、人工回填统计、完整结果比较|
|`experiments/m3/evaluation.json`|固定评价方法，含完整官方提示、源码SHA256与参数，无凭证|
|`requirements-evaluation.txt`|六个直接依赖的固定版本|
|`requirements-evaluation.lock.txt` / `.lock.json`|本次独立环境完整版本快照，无本机安装路径|
|`tests/test_evaluation.py`|28项评分边界与联调测试，API全部模拟|

当前有效交付汇总目录为 `docs/M3/evaluation_offline_v2/`。各组预检在原预测同目录下的 `e_offline_v2/b0` 或 `e_offline_v2/b1`。较早的 `results/m3/smoke/evaluation_offline_v1/b1/` 只保留第一次 smoke B1 预检快照，源码身份较旧，不用于本次交接或恢复。

## E 本人的环境

已在现有 Miniforge 中新建 `ch0201-e-score`，Python 3.11.17。保留 `ch0201-evaluation` 及其他环境；未操作系统 Python 3.13。

在仓库根目录使用以下命令；其他成员可用自己的独立 Python 3.11 环境执行同样的 Python 入口。

```powershell
$env:PYTHONNOUSERSITE = '1'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
conda run --no-capture-output -n ch0201-e-score python -m pip install -r requirements-evaluation.txt
conda run --no-capture-output -n ch0201-e-score python scripts/evaluate.py --help
```

上述变量仅设置当前终端，避免用户级包混入专用环境并保证中文输出。`--no-capture-output` 可避开 Conda 捕获非ASCII输出时的编码问题。代码本身不要求 Conda。

已有 `.env`、`.env.example`、`E_local_setup.md` 与分词器来源记录均保留原状。加载仓库根 `.env`，进程环境变量优先；不使用其他提供商的凭证。离线模式不要求 API 密钥。相关变量为 `JUDGE_PROVIDER`、`JUDGE_BASE_URL`、`JUDGE_MODEL`、`JUDGE_API_KEY`、`RESPONSE_TOKENIZER_PATH`、`RESPONSE_TOKENIZER_SHA256`。与固定方法冲突会在请求前停止。

分词器按 [E_local_setup.md](E_local_setup.md) 的固定版本取得，加载前校验 SHA256。默认本地位置为 `.cache/tokenizers/llama-3.2-1b-instruct/tokenizer.json`。Git 不包含此缓存。不存在或不匹配时停止，不下载新版本、不按字符替代。

## 已执行的离线预检

六组输入依次为 smoke B0/B1 k5、dev B0/B1 k1/k3/k5。所有输入先做UTF-8、JSON、Schema、唯一ID、subset、manifest原始字节SHA256、query SHA256检查，再核对D的实际请求与来源运行记录。批次输入先按同一清单筛选问题/答案/metadata，再检查本批覆盖。

```powershell
conda run --no-capture-output -n ch0201-e-score python scripts/review_evaluation.py prepare --output-dir docs/M3/evaluation_offline_v2 --run-prefix e_offline_v2 --resume
```

这是对已交付预检的只读核对与恢复，无裁判调用。第一次复现请使用新的 `--output-dir` 与新的 `--run-prefix`，去掉 `--resume`；不要覆盖当前记录。所有相对输入路径均相对仓库根解析，启动终端可以位于其他目录。

单组示例（用新的目录和运行编号）：

```powershell
conda run --no-capture-output -n ch0201-e-score python scripts/evaluate.py --questions data/processed/m3/smoke/questions.jsonl --answers data/processed/m3/smoke/answers.jsonl --metadata data/processed/m3/smoke/metadata.jsonl --manifest data/processed/m3/manifest.json --predictions results/m3/smoke/predictions_b1.jsonl --config experiments/m3/evaluation.json --output-dir results/m3/smoke/e_offline_reproduction/b1 --run-id e-offline-reproduction-smoke-b1 --dry-run
```

每组输出 `precheck.json`、`prepared.jsonl`、`deterministic.jsonl`、`pending_judge.jsonl`、`provenance.json`、`run_identity.json`。这些文件有明确的离线身份，**不输出正式 scores 或 summary**。准备数据保留原回答和评分文本，实际裁判 messages 仅含问题、参考、评分文本，不带基线、top-k或检索证据。

D 的旧运行记录存在原电脑的绝对路径。E 用明确提供的本地文件、相同文件名及原始字节SHA256解析来源；新 `provenance.json` 记录可迁移的项目相对路径，不复制原机器路径，不改写D记录。此检查证明文件一致性，不能替代远端服务真实性证明。

## 后续付费阶段的运行方式（本次未执行）

本说明不构成付费授权。需用户另行明确授权，先做 smoke 小批校准，并约定真实请求上限，再进行后续评分。

确认授权后，可基于上面的单组命令去掉 `--dry-run`，改用一个新的付费输出目录与运行编号，再增加：

```text
--allow-paid-api --max-api-requests 12 --cache results/m3/e_judge_cache_v1.jsonl
```

12是当前 smoke B1 的最大待调用量示例，不是已获授权。其他组必须根据当时的清单单独设置上限。六组共享同一个缓存时，当前240条回答理论上最多需要90份成功响应；14条重复输入可复用。没有实际响应缓存时，不能声称已节省费用。

裁判固定为 AutoDL `DeepSeek-V4.1-Flash`，Chat Completions，temperature=0、max_tokens=1024、timeout=120秒。模型是否可用、认证、余额、usage字段和真实语义质量均未远端验证。提示每份9026–9521字符，90份合计826405字符；这是字符数，不能代替DeepSeek计费tokens。价格和人民币费用保持未知。

付费保护与恢复：

- 默认禁止请求；启用付费开关还必须提供正整数上限。重试为0，SDK自动重试关闭。
- 每次发送前将 started 事件刷新到磁盘；每次尝试计入该运行的累计上限，恢复后不重置。
- 成功响应缓存需要相同manifest、ID、问题、参考、实际评分文本与方法配置。复用的是裁判响应，逐题成绩仍保存自己的生成运行来源。
- 返回空内容、截断、异常结构或矛盾结果均是技术失败，score/verdict为null。首次API或解析故障停止后续新请求，并为所有预期ID保留状态行。
- started未完成或已有failed的输入不自动重发。先人工核查服务端状态与可能计费，再决定新的显式重试方案。
- `--resume` 必须使用相同输入、源码、配置、模式、运行编号和缓存路径。已有最终文件先核验字节哈希；不能用恢复覆盖旧结果。需要修复失败题时另建运行，核对缓存中的历史尝试。
- 正式产物是 `scores_b0/b1.jsonl`、`summary.csv`、`run_meta_eval_b0/b1.json`、`official_check.json`，逐题进度与裁判原文/usage另存。进程锁防止同时写入同一输出/缓存；锁文件可保留，操作系统释放锁，无需删除。
- 退出0表示本次模式成功；退出1是输入/配置/结构错误；付费模式完成遍历但仍有技术失败时退出2。离线退出0只表示预检成功。

## 人工盲审和后续比较

只把 `human_blind_review.md` 与 `human_review.csv` 交给独立审阅者，先隐藏 `blind_mapping_private.jsonl`、`ai_review.md`、`ai_review_suggestions.jsonl` 和案例文件。CSV的人工标签、理由、审阅者需由真实人员填写。固定seed42按预测记录抽20条语义待判、10条拒答，再打乱；30条对应28个不同问题，不是简单随机抽样的独立30题。

先另存人工填写的CSV，保留原始空表，再执行：

```powershell
conda run --no-capture-output -n ch0201-e-score python scripts/review_evaluation.py human-summary --human-csv docs/M3/evaluation_offline_v2/human_review_filled.csv --mapping docs/M3/evaluation_offline_v2/blind_mapping_private.jsonl --output docs/M3/evaluation_offline_v2/human_review_completed.json
```

有真实裁判结果后，可重复增加 `--judge-scores SCORES`，统计共同有效样本上的人工一致率和分歧，不改写裁判原成绩。未填完的行仍计待核查；未提供真实裁判成绩时一致率为null。

实际评分后，将完整scores按组传入比较入口，例如：

```text
python scripts/review_evaluation.py compare --scores dev_B0=results/m3/dev/e_paid_v1/b0/scores_b0.jsonl --scores dev_B1_k5=results/m3/dev/e_paid_v1/b1/scores_b1.jsonl --output-dir docs/M3/e_comparison_paid_v1
```

支持的组名是 `smoke_B0`、`smoke_B1_k5`、`dev_B0`、`dev_B1_k1`、`dev_B1_k3`、`dev_B1_k5`。目录名/组名区分top-k，公共行内仍为B1。入口从逐题结果重新计算全量与共同成功ID上的成对指标，不把不同分母直接称为提升。分批时先验证无重叠并合成完整逐题文件，再用完整预测做汇总；重复/缺题会报错，不平均批次百分比。

## 验证与限制

详见 [test_results.json](evaluation_offline_v2/test_results.json) 和 [E_delivery.md](E_delivery.md)。E测试覆盖240条真实截断及8个边界输入，使用AST抽出的官方函数比对；不导入会初始化检索的大包。开发产物在 `fixtures/synthetic/evaluation_v1/`，明确标注模拟；可用A入口复核，不能当真实成绩。

E测试的过程目录必须由调用者通过 `E_TEST_WORKDIR` 指定到工作区规定的位置，文件保留供核查；不给该变量会跳过E测试。示例：

```powershell
# 先按本工作区约定设置 E_TEST_WORKDIR 为过程材料目录，再运行：
conda run --no-capture-output -n ch0201-e-score python -X utf8 -m unittest discover -s tests -p test_evaluation.py -v
```

当前规则仅涵盖文本单轮基线。未校准模型、未人工审阅、未冻结参数，不据此选择top-k；这些结论由A结合后续真实结果处理。特殊token导致截后文本为空时，本入口在请求前停止，因为m3.v1成功评分要求非空文本，需A决定接口后再处理；当前240条未遇到此情况。
