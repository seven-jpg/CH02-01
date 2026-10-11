# E个人环境；此脚本只读比较，不发送API请求。请从项目根目录运行。
$env:PYTHONNOUSERSITE='1'
$env:PYTHONUTF8='1'
$env:PYTHONIOENCODING='utf-8'
# 输出目录必须使用未存在的名称，以保留原结果。
conda run --no-capture-output -n ch0201-e-score python scripts/review_evaluation.py compare `
  --scores smoke_B0=results/m3/smoke/e_paid_4096_v1/b0/scores_b0.jsonl `
  --scores smoke_B1_k5=results/m3/smoke/e_paid_4096_v1/b1/scores_b1.jsonl `
  --scores dev_B0=results/m3/dev/e_paid_4096_v1/b0/scores_b0.jsonl `
  --scores dev_B1_k1=results/m3/dev_topk_sweep_run1/top_k_1/e_paid_4096_v1/b1/scores_b1.jsonl `
  --scores dev_B1_k3=results/m3/dev_topk_sweep_run1/top_k_3/e_paid_4096_v1/b1/scores_b1.jsonl `
  --scores dev_B1_k5=results/m3/dev/e_paid_4096_complete_v1/b1/scores_b1.jsonl `
  --output-dir docs/M3/evaluation_paid_4096_reproduction
