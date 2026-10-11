# eval200运行与增量合入说明

以下命令从项目根目录运行，路径相对项目根目录。E本人使用Miniforge的ch0201-e-score，其他成员可以使用满足requirements-evaluation.txt的独立环境。不要运行付费评分命令来复现统计；已有最终成绩时只需离线比较。

## 离线统计复现

```powershell
python scripts/review_evaluation.py compare --scores eval_B0=results/m3/selected_k1_run1/eval/e_eval_paid_4096_v1/b0/scores_b0.jsonl --scores eval_B1_k1=results/m3/selected_k1_run1/eval/e_eval_paid_4096_v1/b1/scores_b1.jsonl --output-dir results/m3/selected_k1_run1/eval/e_comparison_reproduction_v1
```

输出目录必须尚未使用；成功后应得到共同评分200题、B1胜25/平108/负67，正确率差0.12、truthfulness差−0.21。比较入口读取原manifest/questions/answers/metadata、D预测及相邻E运行记录，核验输入输出哈希和方法身份，不需要API密钥或分词器。

```powershell
python scripts/evaluation_records.py audit --journal results/m3/selected_k1_run1/eval/e_eval_judge_4096_v1.jsonl --output results/m3/selected_k1_run1/eval/e_audit_reproduction_v1.json
```

应得93次请求、93次成功、total_tokens=221106。审计工具的authorization_verified=false表示工具本身不能证明用户授权，不代表授权缺失；本次用户指令和request_budget.json记载100次总上限。

## 实际执行参数

本次两组均调用scripts/evaluate.py，输入为data/processed/m3/eval下questions/answers/metadata、原manifest及selected_k1_run1/eval下对应predictions。配置固定experiments/m3/evaluation_4096.json。B0 run_id=e-eval200-4096-v1-b0，B1 run_id=e-eval200-4096-v1-b1；共享缓存为e_eval_judge_4096_v1.jsonl。B0开始时剩余额度100，调用上限100；B0发送2次后，B1调用上限98，实际再发送91次并复用1份输入。总数为93，未启用重试。正式结果目录为e_eval_paid_4096_v1/b0与b1。

正式预检使用以下离线命令（已运行，不必重复）：

```powershell
python scripts/review_evaluation.py prepare --suite eval --config experiments/m3/evaluation_4096.json --run-prefix e_eval_preflight_4096_v1 --output-dir docs/M3/eval200_4096_v1/review
```

增量包只带suite_summary、抽样及复核材料，不带重复预检工作文件；若要重新生成预检，改用新的run-prefix和output-dir，不能覆盖已人工填写的表。

## 人工回填

真人独立填写review/human_review.csv的human_verdict、human_reason、reviewer后：

```powershell
python scripts/review_evaluation.py human-summary --human-csv docs/M3/eval200_4096_v1/review/human_review.csv --mapping docs/M3/eval200_4096_v1/review/blind_mapping_private.jsonl --judge-scores results/m3/selected_k1_run1/eval/e_eval_paid_4096_v1/b0/scores_b0.jsonl --judge-scores results/m3/selected_k1_run1/eval/e_eval_paid_4096_v1/b1/scores_b1.jsonl --output docs/M3/eval200_4096_v1/review/human_summary_filled_v1.json
```

人类标注与AI复核分别记录，未填写保持待核查。发现分歧先报告，不自动覆盖机器成绩。

## 公共验收与环境

acceptance_eval.json保存了本次严格来源验收。检查器允许重复传入同一stage的--run-meta，本次同时传入generation的B0/B1记录、evaluation的B0/B1记录和retrieval记录，并传入两组requests、scores与B1 evidence。D/C原始记录包含其他机器路径，运行时用--path-map将记录中的旧项目根映射到当前根；该参数由本地路径决定，原记录及其SHA256不能被改写。离线包校验器不使用这些历史绝对路径定位文件。

新增或修改代码仅为src/evaluation/review.py、scripts/review_evaluation.py、tests/test_evaluation.py。公共Schema和评分核心未改，原smoke/dev的默认套件仍为六组、1024历史配置；eval预检必须显式指定4096配置。测试通过E_TEST_WORKDIR指定过程产物目录后运行`python -m unittest discover -s tests -p test_evaluation.py`，本次49项通过。

增量包校验器只依赖Python标准库，读取文件哈希及C/W/M、共同集合、标签转移和请求日志；不会访问网络或重新调用裁判。完整CLI复现仍需要旧包中的合同模块、轻量官方参考源码及E依赖。包内没有分词器文件、凭证或B/C/D输入，应与组长已有项目和D的eval交付合并使用。
