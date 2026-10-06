本包是分工、AI提示词和统一接口规范。A的scripts/check_artifacts.py已实现；其余角色实现和真实实验仍待交付。

发群顺序：
1. 复制00群消息.txt，把B/C/D/E替换成队友姓名。
2. 发整个压缩包；全组先读01统一接口与验收.txt。
3. 各人把自己的“任务与AI提示词”文件、公共接口文件和代码仓库交给AI。
4. A发布确认后的接口版本与生成/评分配置；第一天先用20条真实smoke接通。

文件：
00 群消息
01 公共接口与验收
02 A组长任务与AI提示词
03 B数据任务与AI提示词
04 C检索任务与AI提示词
05 D生成任务与AI提示词
06 E评价任务与AI提示词
07 API接入与预算
接口字段.schema.json：Draft2020-12的行级格式定义，已有A的scripts/check_artifacts.py执行行级和跨文件检查。

每个人收到的是同一接口版本。任何变更由A发布新版本。
本包没有复制官方代码或原始数据。A同时向大家提供现有项目仓库；官方参考来源为https://github.com/facebookresearch/CRAG-MM，避免误拿旧facebookresearch/CRAG。任务包可放在各自项目docs/M2_M3_execution目录，各人的本机根路径可不同。
JSON schema只能检查结构、状态和值，不能证明结果真实，也不能替代ID集合、数据版本、分组、配置与来源检查。
smoke/dev/eval规模与API用量是规划，不是已完成样本；费用不是承诺账单。
