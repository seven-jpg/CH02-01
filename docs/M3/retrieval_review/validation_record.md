# 本次代码与工件验证记录

2026-10-10，Windows，组长电脑的 `.venv-integration` Python 环境。

- 完整测试命令：`python -X utf8 -m unittest discover -s tests -q`；134 项通过，包括原 98 项、11 项路径映射边界检查和25项诊断/实验准备检查。测试使用临时合成输入或模拟子进程，不代表模型实验成绩。
- `audit_retrieval.py` 在真实 dev50 缓存上运行成功：50 条 ok、214 条 hits。没有读取 answers、模型、索引或 API。
- `sweep_retrieval.py` 在真实 dev50 问题和固定 manifest 上完成 prepare-only：准备 top_k=1/3/5 的独立配置和命令。没有生成任何新 evidence；本机计划在 `results/m3/dev_topk_sweep/plan.json`，包含本机路径，未提交到 Git。
- `check_artifacts.py` 使用显式 `D:\CH02-01` 到本地仓库目录映射验收原始 C smoke20/dev50。两次退出0，错误0，技术失败0。提供另外两个集合的 questions/metadata，检查覆盖完整270条分组与编号。详见 [smoke_acceptance.json](smoke_acceptance.json) 和 [dev_acceptance.json](dev_acceptance.json)。
- 已分别确认原始 smoke/dev run_meta 所记录的 manifest、questions、evidence 字节 SHA256 与本机文件相同。没有编辑 C 原始 run_meta、证据、manifest 或检索配置。
- 检索、验收、诊断及扫参入口的 `--help` 均通过；不要求重库、密钥或联网。修改文件编译检查和 `git diff --check` 通过。

验收报告仍公开“官方来源真实性须结合来源记录和人工验证”“答案语义及75-token评价需E验证”。本次没有重新执行索引，没有正式生成或评分，没有证明最优top_k，没有完成eval200，完整实验保持未冻结。
