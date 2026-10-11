# D 生成、批量运行与演示记录

## 交付范围

D 实现了纯文本 B0/B1 生成入口。B0 只接收原始 query；B1 额外接收 C 的 Web 文本 evidence。两组使用同一 NVIDIA provider、同一 `meta/llama-3.2-11b-vision-instruct` 模型和同一 generation 配置。请求不包含答案、图片、图片 URL、OCR、caption、`full_query` 或历史消息。

实现文件：

- `models/text_agent.py`：NVIDIA/Cloudflare REST 适配器、超时和有限重试。
- `scripts/generate.py`：输入校验、证据清理、提示构造、批次、恢复、预测/请求/run_meta 输出。
- `experiments/m3/generation.json`：冻结的公共生成参数。
- `requirements-generation.txt`：轻量依赖。
- `scripts/demo_generation.py`：只读演示生成器，不调用 API、不读取答案。

## 冻结配置

当前 eval 使用 A 的冻结选择：`top_k=1`。生成配置哈希为 `dee0e5ea47324393e87687794da30c00b91e5f7f3f31203e18b7bdea79342502`，manifest 哈希为 `e4dc72b4bcfff5b1e5cc3dc4ff62a2ac923e66dcefb733f9d23243d9f2f34fd0`。

| 参数 | 实际值 |
|---|---|
| provider | NVIDIA |
| model | `meta/llama-3.2-11b-vision-instruct` |
| temperature / top_p | `0 / 1` |
| max_tokens | `100` |
| seed | `42` |
| evidence budget | 1500 tokens 的字符估算（4 chars/token） |
| retries | 最多 2 次重试，指数退避 |

## 真实生成统计

所有正式生成行均为 `generation_status=ok`，没有技术失败或 blocked 行。

| subset | baseline | N | input tokens | output tokens |
|---|---|---:|---:|---:|
| smoke | B0 | 20 | 1,725 | 113 |
| smoke | B1, top-k=5 | 20 | 21,038 | 291 |
| dev | B0 | 50 | 4,345 | 296 |
| dev | B1, top-k=5 | 50 | 58,780 | 653 |
| dev | B1, top-k=1 | 50 | 16,834 | 456 |
| dev | B1, top-k=3 | 50 | 37,665 | 532 |
| eval | B0 | 200 | 17,523 | 1,157 |
| eval | B1, top-k=1 | 200 | 71,337 | 1,891 |

Smoke、dev 和 eval 的 A 验收均检查了 ID 覆盖、manifest/query/config 哈希、requests 重建和 run_meta 文件哈希。eval 生成验收报告为 `results/m3/selected_k1_run1/eval/acceptance_generation.json`，结果为 `valid=true`、`errors=[]`。

## 评分交接

smoke/dev 的评分已经由 E 生成，结果显示 B0 主要是拒答控制组；dev 的 top-k 选择按 Truthfulness 优先确定为 k1。eval predictions 已交给 E，eval scores 和最终 summary 由 E 继续生成。评分使用第三方裁判，不能称为官方排行榜完全同口径；D 不修改 E 的评分逻辑。

## 演示命令

下面命令只读取真实 smoke 工件，生成 Markdown 演示，不调用 API：

```powershell
python scripts/demo_generation.py `
  --questions data/processed/m3/smoke/questions.jsonl `
  --evidence results/m3/smoke/evidence.jsonl `
  --predictions-b0 results/m3/smoke/predictions_b0.jsonl `
  --predictions-b1 results/m3/smoke/predictions_b1.jsonl `
  --scores-b0 results/m3/smoke/e_paid_4096_v1/b0/scores_b0.jsonl `
  --scores-b1 results/m3/smoke/e_paid_4096_v1/b1/scores_b1.jsonl `
  --output docs/M3/D_demo_smoke.md
```

演示时说明：B0 没有证据，面对视觉指代 query 常输出正常的 `I don't know`；B1 会使用 C 的文本命中，但检索对象不一定与图片指代对象一致，因此可能正确、拒答或答错。不能把 B1 的非空回答直接称作提升。

## 已知限制

- NVIDIA API 是在线推理，不是 CRAG-MM 官方离线榜单复现。
- API 费用和账号额度由实际平台账户决定；run_meta 记录 tokens，但不伪造价格。
- eval 的最终正确率、错误率、拒答率和 Truthfulness 等待 E 的 eval 评分。
- 当前没有独立人工复核结果；报告中不把 AI 辅助复核当作独立人工一致率。
