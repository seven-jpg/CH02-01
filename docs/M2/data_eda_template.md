# M2 数据与 EDA 说明

**状态：B 已填写真实数据与运行证据（2026-10-09）。** 统计基于公开 validation 全量，不抽样；所有数字来自实际运行。

## 数据来源与范围

| 数据 | dataset ID | 不可变 revision/split | 分析session/turn数 | 加载失败 |
| --- | --- | --- | --- | --- |
| Single-turn | crag-mm-2025/crag-mm-single-turn-public | `e3a061380b9e5c7cab76f6001173872fe9149081`（v0.1.2 分支解析）/ validation | 1938 / 1938 | 0 |
| Multi-turn | crag-mm-2025/crag-mm-multi-turn-public | `5f87aed919b7bb35a00a518ea401e1fb70a02d20`（v0.1.2 分支解析）/ validation | 586 / 2857 | 0 |

- 下载/加载日期：2026-10-07（单轮）、2026-10-08/09（多轮）；本机 HF 缓存 `D:\hf-cache`。
- 实际 features：session_id / image（内嵌 JPEG 字节）/ image_url / turns / answers；turns 与 answers 为 **dict-of-lists**（v0.1.2 格式）。
- 标签词表（各数据集 features 的 ClassLabel names，实测）：领域 13 类（实测 11 类非零，style and fashion 与 sports and games 均为 0）、题型 6 类、动态性 4 类、图像质量 6 类。**两数据集的 ClassLabel 整数顺序不同，必须各自解码。**
- 范围：validation 全量、无抽样。数据集实际含 validation 与 public_test 两个 split——官方文档声称 v0.1.2 只有 validation，与实测不符，以实测为准；public_test 本阶段未用。

- 代码版本、实际命令、输出文件与 SHA256：见"复现与交付"。
- 图片分析成功数/计划数：内嵌图 2009（单轮 1423 + 多轮 586）/ 2009，全部成功；另有 515 行外链图（仅 image_url）不下载，不参与亮度/清晰度/尺寸统计。

## 预处理与异常

- turns/answers 为 dict-of-lists；代码兼容旧 list-of-dicts（`extract_row_turns`，preprocessing/prepare_data.py）。
- 配对：turns 与 answers 各建 interaction_id → ans_full 查找表后配对，**不 zip、不假设顺序**；ground_truth 只取官方 ans_full。
- 编号：interaction_id 全局唯一（重复 0）→ `id_rule=official-id-kept`，无需组合编号；metadata 保留 source_interaction_id 映射。
- 标签：domain/query_category/dynamism/image_quality 经各自数据集 features 的 ClassLabel names 解码为官方名称。
- 数据质量计数：缺失答案 1（多轮 session `04d98259-27af-41b1-a7be-5798fd1b8e95` 第 6 轮 ans_full 为空字符串——已删除缓存重新下载复核，确认为官方数据原始内容）；空 query 0；无 ID 0；重复 ID 0；重复 query 文本 36（单轮）/ 76（多轮）；字节级重复图像 19 组×2（单轮）/ 1 组×2（多轮）；读取失败 0。
- 排除规则：EDA 只计数不筛选（无 ID/空 query/空白答案分别计数报告）；prepare_data 出包时对三类问题排除并计数（M3 单轮实际排除 0）。
- is_egocentric：官方数据无此字段，metadata 一律 null，不凭观感填写。
- image 为空但 image_url 存在不判缺失（validation 515 行属此情况；真正无图 0 行）。冻结后发现数据问题交 A/B 发布新包，不私自删题。

## 抽样与集合

| 集合 | 方案目标 | 实际数量 | 分组/分层规则 | 用途 |
| --- | --- | --- | --- | --- |
| smoke | 20 | 20 | 组为采样单元；seed=42 | 真实链路联调 |
| dev | 50 | 50 | 同上 | 提示、top-k 和长度设置 |
| eval | 200 | 200 | 同上 | 冻结后的初步对照 |

- seed=42。分组（并查集）：同一 session、相同图像（内嵌字节 SHA256 或相同官方 image_url）、相同 query 文本合并为一组，**组不跨集合**；按真实 domain 分布配额贪心分配，子集达目标即关闭。分层与分组冲突时整组进同一集合（组优先；本包实际恰为 20/50/200）。
- 无法识别的限制：内嵌图仅字节级相同可识别；外链图以 URL 相同视为同一图（未下载复核）；内嵌与外链之间互不匹配。image_group_id 前缀：`img:`=内嵌字节图、`url:`=官方 URL 外链图。
- 无交叉检查：A 的 check_artifacts.py 预验收 exit 0（含跨集合分组检查；报告 results/m3/smoke/check_data.json）。
- manifest：`data/processed/m3/manifest.json`，原字节 SHA256 = `e4dc72b4bcfff5b1e5cc3dc4ff62a2ac923e66dcefb733f9d23243d9f2f34fd0`（2026-10-07 定稿的一致新包；历史哈希 632c9d58、03bd35d0 已作废）。冻结记录见 experiments/m3/freeze_record.json（A 维护）。
- 顺序：先确定三集合完整 ID 清单并写 manifest → 优先导出 smoke 20 供联调 → dev/eval 沿用同一 manifest 随后导出；无临时联调版混入。

M3 只用 Single-turn；Multi-turn 本阶段用于 EDA（M4 多轮阶段题源）。

## 统计与图表

图表目录 `results/eda/charts/`（22 张），统计报告 `results/eda/eda_report.json`。

| 分析项 | 图表/统计文件 | 分母、单位、结论 |
| --- | --- | --- |
| session/turn/去重图像数量 | eda_report.json | 分母=全量 validation<br>单轮 1938/1938（每会话恒 1 轮）；多轮 586/2857<br>内嵌图去重 1404（单轮）/585（多轮），外链 515 行 |
| 领域/问题类型分布 | `*_domain.png`、`*_query_category.png` | 分母=turns<br>单轮 plants 307 最多、book 44 最少；多轮 other 583 最多，两数据集分布不同<br>simple-knowledge 题型均过半 |
| 多轮轮数分布 | `multi-turn_turns_per_session.png` | 分母=586 sessions<br>2轮11/3轮20/4轮107/5轮341(58.2%)/6轮107，中位 5 轮 |
| 问题/答案长度 | `*_query_len.png`、`*_answer_len.png`（含 75-token 估计线） | 计数规则：len(str) 字符数<br>query 平均 45-53 字符；答案平均 87-111、最大 723<br>超 300 字符（≈75 token 估计）仅 1.7%（单轮）/1.2%（多轮） |
| 原图尺寸/长宽比/来源 | eda_report.json（image_size_px/image_source_counts） | 内嵌图恒为 3024×4032（长宽比 0.75）<br>单轮 1423 内嵌+515 外链，多轮 586 全内嵌<br>缩放尺寸另列：官方 Phase 2 对 egocentric 降采样至 960×1280 |
| 图像质量标签 | `*_image_quality.png` | 标签来源：turns 列官方 ClassLabel（顶层没有）<br>normal 各约 84%，退化图 16%（truncated/low light/blurred 为主） |
| 缺失/重复/读取失败 | eda_report.json（exclusion_counts/duplicates/load_failures） | 缺失答案 1（多轮空串）、空 query 0、重复 ID 0<br>重复 query 36/76、字节重复图 19/1 组、加载失败 0 |

每张图记录分析范围与成功分母（图内或报告 n 字段）。
亮度/清晰度代理为自设指标，不是官方标签：亮度=灰度均值（0-255）、清晰度=3×3 拉普拉斯卷积方差（图用 log10 刻度），未设阈值、仅作连续指标；与官方质量标签的对照结果见"影响实验设计的发现"第 5 条。

## 特征表示与模型输入

- 原始 query 以 UTF-8 字符串原样保存（questions.jsonl 仅 6 个 schema 字段）；B 不构造检索编码器，检索侧编码/索引由 C 负责（M3 为纯文本检索）。
- 标题/片段进入文本上下文的形式与 token 计数/截断由 D 负责（B1 证据预算 1500 输入 tokens；生成 max_tokens=100）；E 负责评分侧 75-token 截断（官方 tokenizer）。B 不加载 tokenizer，超长答案占比为字符/4 估计，已注明。
- M3 questions 只保留 schema 允许字段；参考答案仅用于评价（answers 只交 E/A）；图片仅用于 EDA。图像实体/OCR/caption 与历史不流入 M3 输入。
- M4 计划：图像检索与多模态融合（RQ1，题源：单轮 1938 题）；多轮历史策略（RQ2，题源：多轮 586 会话、2-6 轮、跨轮复用率 63.3%）；图像质量扰动（RQ3，素材：退化图 16%，代理指标已给出各质量档数值区间）。

## 影响实验设计的发现

1. 26.6%（515 行）图像为外链形式；其余内嵌图分辨率统一为 3024×4032，官方 Phase 2 对 egocentric 图另有 960×1280 降采样。（报告 image_source_counts/image_size_px）
2. 图像几乎不跨会话共享：单轮 1423 张内嵌图仅 19 组重复（1404 唯一，98.7%），多轮 585/586 唯一（99.8%），共享图分组对抽样几乎无影响（smoke/dev/eval 恰好 20/50/200 无超额）。（报告 duplicates.image_dup_group_sizes）
3. 两数据集的图像属性几乎一致：normal 占比 84.1%（单轮）vs 83.7%（多轮）、亮度中位 118.1 vs 118.3、清晰度中位 69.2 vs 69.7，图像质量与单轮/多轮正交，RQ3 扰动实验不会引入"多轮本身更糊/更暗"的混淆。（`*_image_quality.png`、报告 brightness/sharpness_proxy）
4. 退化图占 16%，以 truncated/low light/blurred 为主（三类合计 78%（单轮）/84%（多轮）），rotated/occluded 较少，与 RQ3 计划的人工扰动类型对应。（`*_image_quality.png`）
5. 自设亮度/清晰度代理与官方质量标签方向一致（low light 亮度中位 69 vs normal 119；blurred 清晰度中位 52 vs normal 71），代理公式可信。（`*_proxy_brightness_by_quality.png`、`*_proxy_sharpness_by_quality.png`）
6. 官方 13 类领域中 style and fashion 与 sports and games 在两个数据集的 validation 中均为 0 题，领域结论不能声称覆盖全部 13 类，领域分层实验需明确这两类无样本。（`*_domain.png`）
7. 句首指代几乎不存在（单轮 0.31%、多轮首轮 0%、后续轮 0.04%），指代发生在句中（"what brand is **this** bike?"），句首指代不能作为历史依赖的代理。（报告 opener_reference_rate）
8. 超 75-token 估计线的答案仅 1.7%（单轮）/1.2%（多轮）；答案平均 87-111 字符（约 22-28 token），个别达 723，评分截断的影响面很小。（`*_answer_len.png`）
9. query 普遍简短（平均 45-53 字符、上限 150），多轮（44.98）短于单轮（53.12），检索可直接用原 query；多轮问题更短与其上下文依赖（复用率 63.3%）互为印证。（`*_query_len.png`）
10. dynamism 高度偏斜：static 占 80% 以上（单轮 1559/1938、多轮 2382/2857），real-time 两数据集合计仅 14 条，问题以静态知识为主。（`*_dynamism.png`）
11. 单轮每会话恒 1 轮；多轮 2-6 轮（平均 4.88，5 轮占 58.2%），多轮实验需覆盖各长度会话。（`multi-turn_turns_per_session.png`）
12. 跨轮内容复用率随轮次单调上升（50.2%→73.8%，整体 63.3%），第 5-6 轮近 3/4 的问题引用前文，历史上下文是多轮回答的关键变量；第 6 轮分母仅 107 个会话。（`multi_turn_history_reuse.png`）
13. 多轮与单轮的构成不同：多轮 simple-knowledge 占 55.7%（单轮 37.6%）、领域以 other 583 居首（单轮以 plants 307 居首）、答案更短（86.9 vs 110.9 字符），两阶段结果不可直接对照，多轮对检索证据的预期依赖更强。（`*_domain.png`、`*_query_category.png`）
14. 多轮跨会话重复 query 文本 76 条（模板化），答案配对完整（仅 1 条空串、ID 缺失 0），多轮配对质量与单轮相当。（报告 duplicates）

## 复现与交付

- 实际命令（仓库根目录，conda 环境 CRAG-MM）：
  - `python preprocessing/prepare_data.py --config experiments/m3/data.json --output-dir data/processed/m3`
  - `python preprocessing/eda.py --config experiments/m3/data.json --output-dir results/eda --offline`（--offline 可选，本机缓存已就绪）
- 依赖版本：Python 3.11.17；datasets 5.1.0、huggingface_hub 2.1.1、pandas 3.0.6、numpy 2.4.6、pyarrow 25.0.1、Pillow 12.3.0、matplotlib 3.11.2、seaborn 0.13.2、tqdm 4.70.1、jsonschema 4.26.0；未安装 torch/vLLM/检索库。
- commit：prepare_data.py 为 `7263c9b5ac`；eda.py、data.json（含 eda 段）与本文档为 `ef1b856`。
- 输出路径：`data/processed/m3/`（manifest + 三集合 9 个 jsonl，manifest SHA256 `e4dc72b4...f34fd0`）、`results/eda/eda_report.json`、`results/eda/charts/` 22 张图。
- 峰值内存：未测（16GB RAM 机器，逐行处理、图像即用即弃，未出现内存告警）。
- A/E 复跑人员、时间、输入哈希和统计一致性：待补（数据包交接后由 A/E 填写）。
