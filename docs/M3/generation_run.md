# D 任务：模型生成、批量运行和演示

`scripts/generate.py` 是纯文本单轮入口。B0 只读取 `questions.jsonl`；B1 另外读取 C 的 `evidence.jsonl`。程序不会打开 `answers.jsonl`、metadata、图片、图片 URL、OCR、caption、`full_query` 或历史消息。

## 依赖和凭证

推荐 Python 3.11 独立环境：

```powershell
python -m pip install -r requirements-generation.txt
```

配置 `experiments/m3/generation.json` 的 `provider`、`model`、`endpoint` 和公共生成参数。支持：

- NVIDIA：`provider=nvidia`，凭证环境变量 `NVIDIA_API_KEY`。
- Cloudflare：`provider=cloudflare`，凭证环境变量 `CLOUDFLARE_ACCOUNT_ID` 和 `CLOUDFLARE_API_TOKEN`；模型可设为 `@cf/meta/llama-3.2-11b-vision-instruct`。

密钥只从环境变量读取，不写入配置、请求记录或运行元数据。B0/B1 必须使用同一个配置哈希、provider、model 和生成参数。

## 干运行和正式运行

`--help` 和 `--dry-run` 不需要密钥，也不会联网。dry-run 会写真实 messages、哈希和 `dry_run_no_api_call` 错误状态，不生成虚假回答：

```powershell
python scripts/generate.py --questions QUESTIONS --manifest MANIFEST --baseline B0 `
  --config experiments/m3/generation.json --output results/m3/smoke/predictions_b0.jsonl --dry-run
python scripts/generate.py --questions QUESTIONS --manifest MANIFEST --baseline B1 `
  --evidence EVIDENCE --config experiments/m3/generation.json `
  --output results/m3/smoke/predictions_b1.jsonl --dry-run
```

正式调用去掉 `--dry-run`。每题最多按配置重试（默认最多两次重试），超时、HTTP/API 失败和空响应都是 `generation_status=error`；模型正常输出 `I don't know.` 仍是 `generation_status=ok`。B1 的 evidence `error/missing` 是 `blocked`，不会退化成 B0；evidence `empty` 可以正常调用。

## 批次和恢复

`--batch-ids` 接受 manifest 中同一 subset 的 JSON 字符串数组。批次输出应放在独立目录；若未显式指定 requests/run-meta 路径，程序会按输出文件名生成批次专用的 sidecar，避免覆盖完整运行记录。使用同一 `--run-id` 重跑可恢复已成功的行，失败行会重新尝试：

```powershell
python scripts/generate.py --questions QUESTIONS --manifest MANIFEST --baseline B0 `
  --config experiments/m3/generation.json --batch-ids BATCH_IDS `
  --output results/m3/smoke/batch-001/predictions_b0.jsonl --run-id smoke-b0-batch-001
```

每次运行还会写 `requests_b0/b1.jsonl` 和 `run_meta_b0/b1.json`。请求记录只含两条文本消息、证据来源映射和 SHA256，不含授权头。`usage` 始终是含 `input_tokens`、`output_tokens` 的对象；提供商没有返回用量时值为 `null`。

正式结果仍需使用 A 的 `scripts/check_artifacts.py` 验收，并由 E 评分；dry-run 或 API 失败不能当作实验结果。
