# A 的集成工具验证记录

日期：2026-10-07（Asia/Shanghai）。本记录验证软件接口，**没有执行真实CRAG-MM实验**，不能当作M3准确率或真实smoke成果。

## 本次交付

- 独立 `scripts/check_artifacts.py`：逐行schema、ID集合、manifest/query/prompt哈希、批次范围、阶段状态关联、实际配置与两组对照。
- `src/contracts/m3.py`：严格UTF-8/JSON、规范配置哈希、文本提示重建；无模型、索引或API依赖。
- requests证据映射与run_meta文件/配置/计数/阶段输入关联检查，报告未核实范围。
- 五人接口与提示词、README、依赖版本、开发样例、冻结跟踪及M2/M3报告模板。

## 实际验证环境与命令

Windows，Python3.12.9；jsonschema4.26.0及依赖版本见仓库根 `requirements-integration.lock.txt`。Python3.11是推荐环境，尚未在本机实测。

```powershell
.\.venv-integration\Scripts\python.exe -m unittest discover -s tests -q
```

结果：**98 tests / OK，33.470秒**。其中67项CLI接口测试、15项公共控制测试、16项运行元数据及来源关联测试。使用临时合成开发样例；没有调用生成API或裁判API、下载索引/模型、读取正式题集或产生真实评分。

重点覆盖：按ID乱序关联、漏题/重复/未知ID、200条完整数据配20条批次、跨集合session/图像/重复问题、严格JSON及Unicode边界、实际配置哈希、提示与证据映射、故障状态不冒充拒答/错误、运行记录不混用旧证据/预测、确定性评分方法核查，以及报告不能覆盖输入文件。

`--help`独立运行通过；任务包JSON Schema/五份提示词/预算算术检查通过。合成fixture始终明确标记为开发材料；`--require-provenance`拒绝将它作为正式来源验收。

## 仍待实际验收

- B：官方不可变数据版本、真实manifest/分组与EDA。
- C：完整官方Web索引的真实检索、来源与内存测量。
- D：模型API可用性、真实请求与B0/B1生成、实际用量。
- E：真实tokenizer的75-token截断、裁判校准、真实评分与人工复核。
- A：以上交付齐全后的真实全量检查、配置冻结、其他成员电脑复跑和中期材料结论。

结构通过不能证明官方来源真实性、裁判语义正确或实际截断已执行；检查报告保留这些限制。`freeze_record.json`继续保持 `is_frozen=false`，没有把开发检查通过写成实验冻结。

来源更正：`78acf3ab...`是本课程仓库初始化提交；`external/CRAG-MM`没有独立Git checkout，官方上游原始commit未核实。
