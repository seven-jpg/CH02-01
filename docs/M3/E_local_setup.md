# E：本机裁判与分词器配置

当前配置已经准备好，供后续 E 评分程序显式读取。评分入口尚未实现，配置文件本身不会自动运行评分。

## 文件放置与 Git

- 本机凭证与路径放在仓库根目录 `.env`。
- 分词器放在 `.cache/tokenizers/llama-3.2-1b-instruct/tokenizer.json`，只需约 9 MB 的分词器文件，无需模型权重。
- 现有 `.gitignore` 已忽略 `.env`、`.env.*` 与 `.cache/`，并允许提交不含密钥的 `.env.example`。
- `.env.example`、本说明及来源核验记录可以提交；本机缓存和真实凭证不提交。
- 当前仓库已有 `.cache` 中的文件只存在于本机。其他成员拉取 Git 后，要按下面的固定来源下载并校验，不能假设 Git 已包含分词器。

## 配置字段

| 字段 | 用途 |
| --- | --- |
| `JUDGE_PROVIDER` | 裁判服务商标识，当前为 `autodl` |
| `JUDGE_API_KEY` | 裁判 API 密钥，仅从本机读取 |
| `JUDGE_BASE_URL` | OpenAI 兼容客户端的 base_url，当前为 `https://www.autodl.art/api/v1` |
| `JUDGE_MODEL` | 裁判请求中的准确 model 名称，当前为 `DeepSeek-V4.1-Flash` |
| `RESPONSE_TOKENIZER_PATH` | 已核验 tokenizer.json 的本地路径；相对路径以仓库根目录解析，不以启动终端的目录解析 |
| `RESPONSE_TOKENIZER_SHA256` | 本地 tokenizer.json 的预期 SHA256；加载前核验，不匹配时明确报错 |
| `HF_TOKEN` | 仅用于另行下载 HF 受限仓库文件。当前本地加载流程不需要，不作为评分前置条件 |

所有设置必须显式加载 `.env`。凭证不写入代码、日志、运行结果、可提交配置或配置哈希输入。按公共接口和现有配置哈希规则记录非敏感实验设置；不能将本机绝对缓存路径当作实验差异。

## 分词器决策与核验

当前账号对 `meta-llama/Llama-3.2-1B-Instruct` 官方 HF 仓库的访问申请已被拒，带 token 下载返回 403。当前采用公开发行仓库的同文件副本，分词器逻辑标识仍为 `meta-llama/Llama-3.2-1B-Instruct`。

| 项目 | 已核验值 |
| --- | --- |
| 官方版本 | `9213176726f574b556790deb65791e0c5aa438b6` |
| 公开发行仓库 | `onnx-community/Llama-3.2-1B-Instruct-ONNX` |
| 公开发行固定版本 | `f91ba3ec08fde6b664d0b1a02cf4305b53a41141` |
| 官方、公开发行与下载文件的 Git blob ID | `5cc5f00a5b203e90a27a3bd60d1ec393b07971e8` |
| 文件大小 | 9,085,657 字节 |
| 文件 SHA256 | `79e3e522635f3171300913bb421464a87de6222182a0570b9b2ccba2a964b2b4` |

[固定文件下载链接](https://huggingface.co/onnx-community/Llama-3.2-1B-Instruct-ONNX/resolve/f91ba3ec08fde6b664d0b1a02cf4305b53a41141/tokenizer.json)。下载后必须核验 SHA256。公开仓库 main 最新文件有变化，不得省略固定版本或校验。

本机缓存内保留 LICENSE.txt、USE_POLICY.md、下载来源、公开元数据与验证记录。许可与使用政策由公开发行仓库固定版本 `14007543b6dc92de88daf96a9aa85d2f95ace6ef` 获取，分词器本身从上表指定的历史版本获取。简要记录见本目录 `E_tokenizer_provenance.json`。

官方评测使用底层 `tokenizers.Tokenizer`。通过 `Tokenizer.from_file` 直接加载同一 tokenizer.json 即可；当前没有替换或使用公开发行仓库的 tokenizer_config.json。

```python
from tokenizers import Tokenizer

# tokenizer_path 为配置解析后的本地路径，先核验 SHA256。
tokenizer = Tokenizer.from_file(str(tokenizer_path))
tokenizer.enable_truncation(max_length=75)
encodings = tokenizer.encode_batch(agent_responses)
agent_responses_scored = [tokenizer.decode(enc.ids) for enc in encodings]
```

沿用官方 encode_batch/decode 默认参数及特殊 token 行为，不自行改为 add_special_tokens=False，不套聊天模板，不先按字符截取。75 指官方编码长度，包括 tokenizer 默认加入的特殊 token。

记录原答案和实际评分文本。m3.v1 中的 `response_tokenizer` 保持官方逻辑名称，`response_max_tokens` 保持 75；另外记录真实下载来源、版本和文件校验值。使用其他裁判模型的差异仍须如实披露。

已有验证：Python 3.11.17 / tokenizers 0.23.3，以本地官方参考源码抽取的截断函数测试 240 条真实预测和 7 个边界样例，全部通过。这里只验证了文件和截断，未运行正式裁判评分。

## 可直接交给负责 E 实现的 AI

请先阅读项目内 E 分工、统一接口与本说明，再实现 E 评分功能。

显式加载仓库根目录 `.env`。裁判配置使用 `JUDGE_PROVIDER`、`JUDGE_API_KEY`、`JUDGE_BASE_URL`、`JUDGE_MODEL`，通过 OpenAI 兼容接口调用，model 名称按配置原样传递。这些设置只用于评分裁判。密钥只在本机读取，不写进代码、日志、评分产物或 Git。

分词器使用 `.env` 中 `RESPONSE_TOKENIZER_PATH` 指定的本地 tokenizer.json，加载前与 `RESPONSE_TOKENIZER_SHA256` 比较。相对路径以仓库根目录解析。官方 HF 访问已被拒，但这个公开发行固定版本文件已核验与官方 Git blob 一致，240 条真实预测及 7 个边界样例已通过官方截断函数验证，不必等待 HF 审核，HF_TOKEN 不作为本地评分的前置条件。

采用 `tokenizers.Tokenizer.from_file` 加载，沿用官方 `enable_truncation(max_length=75)`、`encode_batch`、`decode` 默认行为。保留原答案和实际评分文本，记录来源、版本、校验值、依赖版本。文件缺失、校验失败或分词器加载失败时明确报错，不能自动下载 main 最新文件、换用其他分词器、按字符估算或忽略截断。

保持公共 m3.v1 输出字段、官方 tokenizer 逻辑标识与 75-token 口径不变。接入本地文件后继续按 E 分工做裁判校准、真实 smoke、dev 和冻结后的正式评价。当前配置与 tokenizer 验证不等于评分实现或正式指标已完成。
