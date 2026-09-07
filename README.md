# CH02-01：Meta CRAG-MM 多模态 RAG 项目

## 项目简介

本项目为天津大学《机器学习综合实践》课程项目 **CH02-01**，选题来源于 **KDD Cup 2025 Meta CRAG-MM Challenge**。

项目以 CRAG-MM 多模态视觉问答数据与检索环境为基础，构建一个可运行的多模态 RAG 系统，并围绕课程给定的三个研究问题进行实验和分析。

本项目的重点并不是重新参加 KDD Cup，也不是完整复现比赛冠军方案，而是将 CRAG-MM 作为实验平台，通过对比实验研究多模态信息、多轮上下文以及图像质量对系统性能的影响。

---

## 研究问题

### RQ1：多模态检索效果

多模态检索（图像 + 文本）相比纯文本检索，在答案准确性上的提升幅度如何？

计划比较：

- 纯文本检索
- 图像 + 文本多模态检索

---

### RQ2：多轮上下文策略

多轮对话中，不同上下文利用策略对答案质量有什么影响？

计划比较：

- Full History：使用全部历史对话
- Summary：使用历史摘要
- Sliding Window：仅使用最近若干轮对话

---

### RQ3：图像质量鲁棒性

图像质量扰动对多模态 RAG 系统性能有什么影响？

计划研究：

- Clean：原始图片
- Blur：图像模糊
- Occlusion：图像遮挡
- Low-light：低光照

---

## CRAG-MM 数据

本项目使用 CRAG-MM 官方公开数据，主要包括：

### Single-turn

单轮视觉问答数据：

```text
Image + Question -> Answer
Image
 + Turn 1
 + Turn 2
 + Turn 3
 + ...
 CH02-01/
│
├── src/
│   └── 小组自行开发的核心代码
│
├── scripts/
│   └── 数据下载、预处理和实验运行脚本
│
├── tests/
│   └── 测试代码
│
├── experiments/
│   ├── rq1/
│   ├── rq2/
│   └── rq3/
│
├── docs/
│   └── M1/
│       └── M1 阶段文档、系统设计和 RQ 拆解
│
├── external/
│   └── CRAG-MM/
│       └── Meta 官方 CRAG-MM Benchmark 参考代码
│
├── data/
│   └── CRAG-MM 数据，不提交 Git
│
├── search_indices/
│   └── Image Search / Web Search 检索数据，不提交 Git
│
├── checkpoints/
│   └── 本地模型权重，不提交 Git
│
├── .gitignore
└── README.md
docs/               官方说明文档
evaluation/         官方评价代码
example_agents/     官方示例 Agent
example_scripts/    示例运行脚本
utils/              公共工具
local_evaluation.py 本地 Evaluation 入口