# E 离线交付与验收

2026-10-11。**评分程序已完成离线实现与验证，现有输入已完成预检；真实语义评分、人工核查和eval200正式成绩仍待相应授权或材料。** 本次真实裁判请求0次，未自动提交Git，未冻结实验配置。

## 先看这些材料

- [运行说明](E_evaluation_run.md)：专用环境、入口、输入输出、恢复和后续付费保护。
- [评价章节草稿](E_evaluation_report_draft.md)：可交A整合的中期报告内容，明确无正式准确率。
- [六组工作量汇总](evaluation_offline_v2/suite_summary.json) / [CSV](evaluation_offline_v2/suite_summary.csv)：240条、136条规则拒答、104条待判、90份不同裁判输入。
- [人工盲审材料](evaluation_offline_v2/human_blind_review.md) / [填写表](evaluation_offline_v2/human_review.csv)：30条，当前人工完成0条。
- [AI辅助意见](evaluation_offline_v2/ai_review.md)：30条已逐条复核，其中7条保留待确认。请在独立人工判断后再阅读。
- [10个案例草稿](evaluation_offline_v2/cases.md)：保留实际请求证据与因果判断限制。
- [测试记录](evaluation_offline_v2/test_results.json)：137项测试全部通过，28项E测试及109项公共接口/验收相关回归。
- [模拟验收样例](../../fixtures/synthetic/evaluation_v1/README.md)：A现有验收入口退出0，明确模拟，真实请求0。

## 与已有模块的对接

使用项目内最新统一接口同目录的Schema和公共 `src/contracts/m3.py` 哈希函数。没有改动两份Schema、A校验器、公共依赖、根README、B数据、C证据、D预测/请求/运行记录或冻结文件。

输入来自当前固定manifest及六套D预测，按ID关联；不得将答案送给检索/生成。D旧元数据的机器路径以匹配文件名和原始字节SHA256解析，新产物使用相对路径，旧记录保持原样。预检阶段不会输出公共scores，避免用“待裁判”伪装成完成的评分状态。正式阶段遵循m3.v1全部scores字段及run_meta约定。

本次保留初始已有的未提交 `.env.example`、`docs/M3/E_local_setup.md`、`docs/M3/E_tokenizer_provenance.json`，未改写它们或本机 `.env`。新建E独立环境，Python为3.11.17；直接依赖版本与规划一致。未操作系统Python3.13、既有分词器验证环境或其他Conda环境。

## 本次新增文件及职责

|范围|内容与E职责|
|---|---|
|`src/evaluation/__init__.py`、`score.py`、`inputs.py`、`review.py`|评分、校验、缓存、统计、复核材料|
|`scripts/evaluate.py`、`scripts/review_evaluation.py`|独立CLI及批次/复核/比较入口|
|`experiments/m3/evaluation.json`|完整官方提示、参数、tokenizer身份、源码哈希与适配差异|
|`requirements-evaluation.txt`、`requirements-evaluation.lock.txt`、`.lock.json`|E个人环境的可复现依赖|
|`tests/test_evaluation.py`|E测试与A接口联调|
|`fixtures/synthetic/evaluation_v1/`|仅模拟评分与验收材料|
|`results/m3/**/e_offline_v2/`|六组真实输入的预检、规则清单、待调用清单及来源记录|
|`docs/M3/evaluation_offline_v2/`|全局去重、30条盲审/AI建议、10个案例及测试证据|
|本目录三个E新文档|运行、报告草稿、本交接清单|

第一次smoke B1预检快照在 `results/m3/smoke/evaluation_offline_v1/b1/` 保留供追溯；当前交接只用v2。未删除或移动任何用户文件。过程日志与测试临时夹具按工作区约定保留在独立过程目录，不进入提交代码。

提交注意：现有 `.gitignore` 忽略所有 `*.txt`，因此E依赖TXT文件虽已交付，却不会自动出现在普通 `git status` 中。请A显式选择 `git add -f requirements-evaluation.txt requirements-evaluation.lock.txt`，或使用同时交付的锁定JSON核对版本；本次未改公共忽略规则、未暂存文件。提交时排除运行锁文件 `evaluation.lock`、`*.jsonl.lock`，不提交 `.env` 和本地缓存。所有代码不包含机器绝对路径或工作区过程目录名称。

## 真实验证证据

完整环境依赖快照见仓库根的 `requirements-evaluation.lock.json`。实际验证运行：E评分测试28项，公共 `test_contract_controls`、`test_check_artifacts`、`test_run_metadata` 回归109项，合计137项、失败0、错误0、跳过0。公共测试的临时目录由本次调用环境重定向并保留，不改测试源文件，也不执行其自动清理。

E的离线CLI测试屏蔽socket连接与DNS，并模拟OpenAI客户端；六套真实预检同样在socket/DNS保护下完成。`--help`不读凭证、不加载分词器、不联网。240条真实回答与8个边界输入的截断结果同官方函数一致。坏JSON、BOM、重复/缺失/未知ID、错哈希、混合运行、预算不足、错误解析、空usage、缓存恢复、源码/来源变化、并发写入、输出覆盖保护及人工空表均有检查。

模拟评分通过A现有验收入口。它证明公共字段、哈希和计数对接，不能证明真实裁判的语义可靠性、模型可用性或费用。额外原始验证日志留在过程材料中；可提交证据只使用可迁移的相对路径，不带凭证。

## 给A的建议和待办

1. 认可目前E离线就绪；M3“初步准确率”仍需真实语义评分，报告保留待完成标记。
2. 后续获用户授权后，先在smoke B1最多12份待判输入上做小批校准，完成人工判断，处理7条待确认记录，再覆盖其余现有输入。当前全部去重为90份，费用取决于服务商实际usage与当时核实价格。
3. 现有B1的规则拒答少于B0，dev k5拒答最少；不能据此称准确率提升或k5最优。正式比较使用共同成功ID，公开覆盖率。
4. 保留原始D机器路径记录，整合时沿用已存在的路径映射能力；E没有代替D修订来源记录。
5. 不改公共三标签协议。对部分正确/信息不完整的回答，应先通过人工校准形成一致解释；若需要新增0.5档，由A发布接口新版本。
6. A负责参数冻结；eval200需D先生成。多模态、多轮与鲁棒性仍留给M4。

本次没有难以抉择且阻断离线实现的接口问题。语义边界已保留待确认，没有暗自修改评分规则或替用户决定付费。
