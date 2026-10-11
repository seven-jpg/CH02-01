# eval200 正式评分与成对比较

2026-10-11完成同一固定eval200的B0/B1共400条评分。生成、评分覆盖率均为100%，最终技术失败0；B1采用A在dev选择并冻结的k=1。eval结果未用于重新选择k、提示、截断或裁判参数。

|组别|固定/生成/评分|正确C|错误W|拒答M|正确率|错误率|拒答率|truthfulness|
|---|---:|---:|---:|---:|---:|---:|---:|---:|
|B0|200/200/200|2|0|198|1%|0%|99%|0.01|
|B1 k1|200/200/200|26|66|108|13%|33%|54%|−0.20|

共同成功评分集合为全部200题。B1−B0：正确率+12个百分点、错误率+33个百分点、拒答率−45个百分点、truthfulness−0.21。按每题分值比较，B1胜25题、平108题、负67题。没有将两个不同分母直接相比。

|B0 → B1|CORRECT|WRONG|MISSING|
|---|---:|---:|---:|
|CORRECT|1|0|1|
|WRONG|0|0|0|
|MISSING|25|66|107|

检索让模型从拒答转向更多实际回答，其中25题转为正确、66题转为错误；另有1题由B0正确转为B1拒答。B0几乎总是拒答，较高truthfulness不能解释为回答能力更强。本结果为200题上的描述性比较，不声称统计显著、参数全局最优或完整多模态效果。

## 方法与请求审计

沿用官方提示、已核验Llama-3.2-1B-Instruct分词器的75-token截断及三类计分；语义裁判为AutoDL的DeepSeek-V4.1-Flash，temperature=0、max_tokens=4096、timeout=120秒，SDK及应用自动重试均为0。此方法与官方排行榜裁判不同，不声称同口径。

306条按拒答规则处理，无精确匹配；94条语义记录因一个两组相同输入去重为93份。真实请求93次、全部成功、补试0次，未发生结果不明的请求；两组共用响应日志，但成绩各自保留生成来源。提供商返回total_tokens合计221106，已知usage为93次，未知0次。货币价格未核实，不估算费用。用户授权上限100次，实际未用到补试余量。

汇总分母为N=C+W+M，accuracy=C/N、hallucination_rate=W/N、missing_rate=M/N、truthfulness=(C−W)/N。技术失败保留null、不计入C/W/M；本次无技术失败。历史smoke/dev的240条及其调用用量单独保留，不合并进eval分母或本次93次请求。

## 复核与案例

seed=42，从400条预测记录抽样20条语义、10条拒答，覆盖29个不同问题。AI依据盲化材料先形成建议，再核对裁判，30/30一致，其中语义20/20、规则10/10。AI建议不是独立人工核查，亦不能证明裁判可靠；独立人工完成数仍为0。原AI建议未在核对后修改，原始成绩未变。

human_review.csv保留空白人工列；先向真人提供human_blind_review.md、blind_review.jsonl和human_review.csv，身份映射、AI建议及机器比较结果不要提前展示。复核文件位于review/。10个目的性案例见[cases.md](cases.md)，其中包含对象错配、数字错误、正确答案与错误证据并存、拒答，以及宽泛回答被裁判接受的局限。

## 产物与验证

成绩位于`results/m3/selected_k1_run1/eval/e_eval_paid_4096_v1/b0`和`b1`；响应日志为同一eval目录中的`e_eval_judge_4096_v1.jsonl`。目录内的scores、summary、official_check和run_meta保留完整来源与方法。

- [全量汇总](comparison/completed_summary.csv)、[成对比较与标签转移](comparison/completed_comparisons.json)、[逐题比较](comparison/paired_questions.csv)。
- [请求审计](request_audit.json)、[预算记录](request_budget.json)、[400条独立重算](verification.json)、[公共验收](acceptance_eval.json)。
- [运行与合入说明](run.md)、[AI复核对照](review/ai_judge_comparison.json)、[人工核查状态](review/human_status.json)。

49项E模拟回归通过，测试网络已阻断。公共验收链接两组生成和评价运行记录，连同跨集合隔离检查通过；400条截断文本、规则标签及保存语义响应重算一致。验收仍不能证明参考来源真实性或独立人工语义可靠性。A负责汇总全组冻结与中期报告；本次不改写A的冻结记录。
