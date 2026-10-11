# D 生成演示

本演示只读取 questions、evidence、predictions 和可选 scores，不调用模型、不读取 answers。

## 案例 1: `129fc5be-e485-4e82-a5d3-fcbee8503d3e`

- Query：what are females of these animals called?
- Evidence status：`ok`；命中数：`4`
- 来源：What Are Female Foxes Called? A Detailed Look At Fox Terminology - Berry Patch Farms；URL：https://www.berrypatchfarms.net/what-are-female-foxes-called/
- 来源：Animals；URL：https://kids.nationalgeographic.com/animals
- 来源：How to Tell the Difference Between a Male & Female Fox \| Pets on Mom.com；URL：https://animals.mom.com/how-to-tell-the-difference-between-a-male-female-fox-4195577.html

| 项目 | B0 | B1 |
|---|---|---|
| 回答 | I don't know | Vixen. |
| 状态 | `ok` | `ok` |
| 输入 tokens | 84 | 847 |
| 输出 tokens | 5 | 5 |
| 评分 | MISSING | CORRECT |

## 案例 2: `1427a108-1ac1-4f0c-90ec-7dc58dbff93a`

- Query：Where can this plant typically be found?
- Evidence status：`ok`；命中数：`4`
- 来源：The Carnivorous Plant FAQ: Where can I see wild carnivorous plants?；URL：https://www.sarracenia.com/faq/faq4220.html
- 来源：Common Dandelion \| Missouri Department of Conservation；URL：https://mdc.mo.gov/discover-nature/field-guide/common-dandelion
- 来源：Growing pygmy Drosera \| ICPS；URL：https://www.carnivorousplants.org/grow/guides/PygmyDrosera

| 项目 | B0 | B1 |
|---|---|---|
| 回答 | I don't know. | I don't know |
| 状态 | `ok` | `ok` |
| 输入 tokens | 84 | 1132 |
| 输出 tokens | 6 | 5 |
| 评分 | MISSING | MISSING |

## 案例 3: `1baffe9f-b104-44b9-b9e2-3f98a4d572e6`

- Query：what are some recreational features at this park?
- Evidence status：`ok`；命中数：`4`
- 来源：Bear Creek Lake Park (Everything To Know Before A Visit) - The Tourist Checklist；URL：https://thetouristchecklist.com/bear-creek-lake-park/
- 来源：Veltus Park；URL：https://www.mypacer.com/parks/186129/veltus-park-glenwood-springs
- 来源：Veltus Park: Recreation Centers in Colorado, United States；URL：https://veltus-park.wheree.com/

| 项目 | B0 | B1 |
|---|---|---|
| 回答 | I don't know | Volleyball, tennis, basketball courts, playground equipment, horseshoe pits, covered picnic shelters, walking trails, and off-leash dog area. |
| 状态 | `ok` | `ok` |
| 输入 tokens | 85 | 1151 |
| 输出 tokens | 5 | 32 |
| 评分 | MISSING | WRONG |

