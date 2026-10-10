# E 模拟评分验收样例

此目录由E的 `test_simulated_cli_scores_pass_A_and_resume_integrity` 导出。问题、参考、预测均为合成开发数据；三个裁判响应由 `unittest.mock` 注入，真实API请求为0。`output/run_meta_eval_b0.json` 明确设置 `is_simulated=true`、`real_api_requests=0`，usage也是模拟值。不得用于报告模型准确率。

从仓库根目录，在有jsonschema的Python环境执行：

```text
python scripts/check_artifacts.py --manifest fixtures/synthetic/evaluation_v1/manifest.json --questions fixtures/synthetic/evaluation_v1/questions.jsonl --answers fixtures/synthetic/evaluation_v1/answers.jsonl --metadata fixtures/synthetic/evaluation_v1/metadata.jsonl --predictions fixtures/synthetic/evaluation_v1/predictions_b0.jsonl --requests fixtures/synthetic/evaluation_v1/requests_b0.jsonl --scores fixtures/synthetic/evaluation_v1/output/scores_b0.jsonl --config evaluation=fixtures/synthetic/evaluation_v1/e_config.json --run-meta evaluation=fixtures/synthetic/evaluation_v1/output/run_meta_eval_b0.json
```

实际验收退出0，摘要见 `acceptance_summary.json`。这是结构、来源文件哈希与状态计数验收，不能通过正式真实来源验收。不要增加 `--require-provenance` 后宣称是真实成绩。

此目录不包含真实凭证。它保留评分方法、逐题成绩、摘要、官方汇总核对和模拟响应日志，便于A检查E与m3.v1对接。测试源码与当前E源码的哈希保存在元数据中；直接重复测试会在调用者指定的过程目录新建材料，不覆盖本样例。
