# E评价资料索引

实验方法、主要结果与局限见[评价与结果分析](../E_evaluation.md)，环境配置和复现命令见[运行说明](run.md)。本目录保存支撑材料，按需查阅。

|材料|内容|
|---|---|
|[complete_v1/README.md](complete_v1/README.md)|完整评分时的结果快照、汇总、案例、公共验收与请求审计|
|[validation/comparison_v1.json](validation/comparison_v1.json)|比较入口校验修复后的47项测试、六组比较和异常副本验证|
|[validation/offline_repair_v1.json](validation/offline_repair_v1.json)|早期输入与恢复逻辑验证记录|
|[review/tokenizer_provenance.json](review/tokenizer_provenance.json)|固定分词器来源、版本和哈希|
|[review/review_sampling.json](review/review_sampling.json)|seed 42分层抽样方法及样本数|
|[review/blind_review.jsonl](review/blind_review.jsonl)|隐藏组别后的30条待复核记录|
|[review/blind_mapping_private.jsonl](review/blind_mapping_private.jsonl)|样本与原组别、ID的对应关系|
|[review/ai_reviews.jsonl](review/ai_reviews.jsonl)|30条AI辅助复核意见，人工核查数为0|
|[reference_map.json](reference_map.json)|历史记录中旧资料路径与现存位置的对应关系|

`calibration_ids.json`、`failed_ids.json`和`remaining_unrequested_ids.json`被评分运行记录引用，保留原位置；`preflight.json`与`continuation_authorization.json`保存当时的检查和调用范围记录。`../evaluation_offline_v2/smoke_b1_remaining_ids.json`为早期1024运行引用的批次清单。

`complete_v1/`为原始实验快照，文件及其哈希清单保持不变，其中测试数和源码哈希描述的是评分完成时的版本。当前方法与运行方式以主说明和`run.md`为准。历史验证中的早期资料原路径通过`reference_map.json`查找，不改写原验证记录。
