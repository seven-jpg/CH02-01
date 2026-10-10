# 10 个典型案例草稿

以下来自固定30条抽样，包含正确建议、明显错误、拒答和待确认情况。案例用于解释机制，不能代表整体准确率；不是正式裁判确认的案例。证据取自D实际请求，并用doc_id与C原始命中对应。长片段保存于cases.json，供回查。

## C01 数字来自错误门店对象（R002）

来源：dev_B1_k3，interaction_id=efe0f64e-fbea-4b0e-b8a7-118e1433d35c。

问题：how many locations do they have in new york city?

参考：empanada mama has 6 locations in new york city.

原回答：73.

实际评分文本：73.

观察：预测73对应提示中的7-Eleven纽约门店数；参考问的是empanada mama的6家。证据中可见明确对象错配。

限制：已观察到对象错配；其形成与只用含they的原问题检索有关，是否仅因缺图仍待后续多模态实验。

实际提示证据（节选；完整文本见JSON）：

- `https://app.foursquare.com/locations/7-eleven/new-york-city_chunk_0`：NYC is finally getting the 7-11's we deserved!7-11 is planning to open hundreds of new stores in Manhattan - driving local bodegas out. NYC is mall-like enough for my taste already so I'm recommending a city-wide boycott of 7-11. Find 7-Eleven locations near you. See hours, menu, directions, photos, and tips for the 73 7-Eleven locations in New York City.
- `https://www.lyft.com/hub/hours/new-york_chunk_0`：New York Service Locations and Hours
- `https://www.nyc.gov/assets/dsny/site/resources/recycling-and-garbage-laws/collection-setout-laws-for-residents_chunk_0`：Nyc

## C02 问题缺少明确对象时拒答（R003）

来源：dev_B0，interaction_id=d998d529-026c-49f5-a673-e3450c4db395。

问题：what's the typical blooming period for this plant?

参考：dracaena reflexa typically blooms in mid winter.

原回答：I don't know.

实际评分文本：I don't know.

观察：原问题只说this plant，B0未使用检索证据，回答标准拒答。

限制：拒答已确认；无法仅凭本条断言视觉模型一定能答对。

实际提示证据：无，B0按设计只使用原问题。

## C03 检索片段的恐龙对象与参考不符（R005）

来源：dev_B1_k1，interaction_id=a9e389a2-74df-4c79-aa0c-ac7b3eda0eed。

问题：How does the height of a human compare to this specific dinosaur?

参考：The Pachycephalosaurus had an approximate height of 10 feet, which is significantly taller than an average human, whose height averages around 5.6 feet. 

原回答：The Utah Raptor, a dinosaur likely being referred to, was closer to the height of a man.

实际评分文本：The Utah Raptor, a dinosaur likely being referred to, was closer to the height of a man.

观察：实际提示包含Utah Rapter接近人高的段落，预测Utah Raptor；参考要求Pachycephalosaurus约10英尺。

限制：证据和回答都出现另一对象；未重新检查原图，不能将责任全部归为生成错误。

实际提示证据（节选；完整文本见JSON）：

- `https://www.reddit.com/r/Damnthatsinteresting/comments/1002vsb/video_i_saw_comparing_a_human_to_the_size_of_many/_chunk_0`：829 votes, 83 comments. 20M subscribers in the Damnthatsinteresting community. For the most interesting things on the internetPosted by u/DirkDieGurke - 829 votes and 83 comments But I think this is mainly to show the scale comparison. Regardless they should’ve either said length or height in the video title. I think they pulled the models off Jurassic World: Evolution and then seemed to just make up heights or incorrectly use lengths in its plac

## C04 相关证据下的部分正确回答（R007）

来源：dev_B1_k5，interaction_id=b328be7f-85ba-4b36-9ad9-b5f2a080dc0b。

问题：how are these different from hachiya persimmons?

参考：fuyu persimmons are round and squat, compared with hachiya persimmons, which are elongated in shape. moreover, fuyu persimmons are far less astringent than hachiya persimmons, and can be enjoyed while firm as well as soft, unlike hachiya perssimons, which much be incredibly soft to eat.

原回答：Fuyu persimmons are not astringent, have a mild flavor, and can be eaten when firm, while Hachiya persimmons are astringent, tart, and must be eaten when extremely ripe.

实际评分文本：Fuyu persimmons are not astringent, have a mild flavor, and can be eaten when firm, while Hachiya persimmons are astringent, tart, and must be eaten when extremely ripe.

观察：提示含Fuyu/Hachiya的涩味、软硬度及形状信息；回答保留前两类差异，遗漏形状。

限制：是否应算CORRECT尚待校准；不能将有相关证据直接等同于答全。

实际提示证据（节选；完整文本见JSON）：

- `https://www.youtube.com/watch?v=XUh6N_vLISk&pp=ygUMI3V2YXNwYXR0b2tp_chunk_0`：Fuyu vs. Hachiya Persimmon - Differences, Tips & Persimmon ...
- `https://www.tiktok.com/discover/fuyu-persimmon-vs-tropical-persimmon-vs-hachiya-persimmon_chunk_0`：Fuyu Persimmon Vs Tropical Persimmon Vs Hachiya ...
- `https://realfoodmostlyplants.com/fuyu-persimmons-and-hachiya-persimmons/_chunk_0`：Ripe hachiyas are unbelievably soft – and are often almost liquified into a smooth pulp inside. You can tell the difference between Hachiya and Fuyu persimmons, because Hachiyas are elongated and oval shaped instead of squatted and round.Fuyu and Hachiya persimmons are the two most common persimmon varieties available in North America. What's the difference? They will ripen after being picked, so buying rock-hard fuyus and allowing them to ripen 
- `https://www.tiktok.com/@metmarket/video/7431609988705062190_chunk_0`：Fuyu vs. Hachiya: Exploring the Two Sides of Persimmons
- `https://blog.bostonorganics.com/fuyu-vs-hachiya-persimmons-explained_chunk_1`：Persimmons are one of fall's greatest gifts! Take a second to learn about the two most common varieties and discover how to best enjoy these tasty treats.Beautiful orangey, red Persimmons are now in season and will show up in many boxes during their October-February season. An often underrated treat, persimmons are sweet and delicious, adding a honey-like brightness to desserts, salads and as a snack. Two primary varieties of persimmons are avail

## C05 同一俗名对应不同物种（R011）

来源：dev_B1_k5，interaction_id=ef31c7ad-356b-461c-ba64-4bf478aefe90。

问题：Why is this plant called the Devil's tobacco?

参考：Lobelia polyphylla is called the Devil's tobacco because of its because of its hallucinogenic effects when smoked.

原回答：It's called Devil's Tobacco because its narrow, hairy foliage bears a resemblance to tobacco.

实际评分文本：It's called Devil's Tobacco because its narrow, hairy foliage bears a resemblance to tobacco.

观察：提示第三条介绍Lobelia tupa并以叶片像烟草解释俗名；参考对象是Lobelia polyphylla，命名原因不同。回答跟随了提示片段。

限制：俗名检索有歧义；这支持证据对象错配分析，尚不证明检索器在可识别对象的情况下必然失败。

实际提示证据（节选；完整文本见JSON）：

- `https://wiki.tripsit.me/wiki/Devil's_Tobacco_chunk_0`：Devil's Tobacco - TripSit wiki
- `https://www.inaturalist.org/taxa/358073-Lobelia-excelsa_chunk_0`：Devil's Tobacco (Lobelia excelsa) · iNaturalist
- `https://www.onlineflowergarden.com/2020/10/07/gardening/perennial-plants/lobelia-tupa/_chunk_0`：Lobelia tupa is an upright plant with striking gray-green leaves. The narrow, hairy foliage bears a resemblance to tobacco, hence its intriguing nickname, Devil’s Tobacco. The stem of the plant boasts a dark purplish hue, adding a touch of drama to its overall presentation.Lobelia tupa is an upright plant with striking gray-green leaves. The narrow, hairy foliage bears a resemblance to tobacco, hence its intriguing nickname, Devil’s Tobacco. The 
- `http://www.naturalmedicinalherbs.net/herbs/l/lobelia-tupa=devil's-tobacco.php_chunk_1`：medicinal herbs: DEVIL'S TOBACCO - Lobelia tupa
- `https://www.inaturalist.org/taxa/431237-Lobelia-tupa_chunk_0`：devil's tobacco (Lobelia tupa) · iNaturalist

## C06 相同泛指问题难以确定花种（R013）

来源：dev_B1_k3，interaction_id=5b2c9627-71b8-486f-9388-2b93c8a278e1。

问题：what color are the blooms on this plant?

参考：the melaleuca camptoclada has mauve flowers.

原回答：White or nearly white, and some hybrids have pink splotches or entirely pink petals.

实际评分文本：White or nearly white, and some hybrids have pink splotches or entirely pink petals.

观察：提示列出Allium与Phalaenopsis等对象；预测取了兰花的白色/粉色内容，参考却是melaleuca camptoclada的mauve。

限制：错误对象证据清楚；需要M4验证加入图像身份能否缓解。

实际提示证据（节选；完整文本见JSON）：

- `https://www.pacificbulbsociety.org/pbswiki/index.php/AlliumFlavumRelatives_chunk_2`：Allium carinatum L. is from much of Europe into Asia, naturalized elsewhere (the Brittish Isles). Informal sprays of little rose-purple, rose-pink, to white flowers dangling on very long slender pedicels, sometimes with bulbils (though many selections are bulbil-free).Allium carinatum ssp. pulchellum (G.Don) Bonnier & Layens is a European species that is very close to Allium flavum, flowering at the same time in June or July depending on the vari
- `https://www.epicgardening.com/types-of-flowers/_chunk_8`：Finding the right flowers for your home or garden can be very challenging. Not only do you have to think about seasonality, but you have to consider color, climate, environment, sunlight, and more. In this article, gardening enthusiast Jason Wilson walks through over three hundred different ...Finding the right flowers for your home or garden can be very challenging. Not only do you have to think about seasonality, but you have to consider color,
- `https://gardenerspath.com/plants/flowers/grow-phalaenopsis-orchids/_chunk_7`：Phalaenopsis orchids are fantastic but they have unique care requirements compared to other houseplants. Learn everything you need to know now in our guide.Phalaenopsis orchids are fantastic but they have unique care requirements compared to other houseplants. Learn what you need to know now! This species has small white flowers, but there are some hybrids that feature pink splotches or ones with entirely pink petals. Easily mistaken for P. amabi

## C07 证据观点与固定参考冲突（R019）

来源：dev_B1_k1，interaction_id=8e9efe39-8f8e-4f0b-867c-83faf740aa0d。

问题：is this better for the environment than a real one?

参考：no, real christmas trees are better for the environment as they do not have to be shipped and help fight climate change until they are cut down.

原回答：Neither, it's a complex issue with no clear-cut winner.

实际评分文本：Neither, it's a complex issue with no clear-cut winner.

观察：提示文章写both and neither、没有明确赢家；模型照此答Neither，而固定参考给出真实树更环保。

限制：此条按参考评分建议WRONG；不是标准MISSING。不能据此裁决现实环保争论。

实际提示证据（节选；完整文本见JSON）：

- `https://www.texasdisposal.com/blog/real-vs-fake-christmas-trees/_chunk_0`：Are real Christmas trees or fake Christmas trees better for the environment? The answer may seem obvious, but this debate is more complicated than it seems.Additionally, at the end of their lives, disposing of natural trees isn’t as easy as it may seem. While old Christmas trees are a good source for bonfire material, burning the tree simply releases the carbon dioxide it collected during its lifetime. If you are replacing firewood that would hav

## C08 动态数值与参考时间不一致（R020）

来源：dev_B1_k1，interaction_id=896302ba-4a70-415c-a649-bac94ee0ee0d。

问题：compare the number of branches this bank has to bank of america.

参考：wells fargo and bank of america are among the largest banks in the united states, boasting extensive national networks. as of 2024, wells fargo operates 8,050 branches, outpacing bank of america's approximately 4,900 locations.

原回答：Wells Fargo has more branches, with over 5,000 across 40 states, compared to Bank of America's 4,000 branches.

实际评分文本：Wells Fargo has more branches, with over 5,000 across 40 states, compared to Bank of America's 4,000 branches.

观察：提示片段写Wells Fargo超过5000、Bank of America 4000；回答沿用这些值，参考为2024年8050/4900。

限制：比较方向一致但数字不符；片段未提供可验证的对应采集日期，不能擅自认定参考错误或用今天的数替换。

实际提示证据（节选；完整文本见JSON）：

- `https://www.finder.com/wells-fargo-vs-bank-of-america-accounts_chunk_0`：Less accessible customer service. Unlike Wells Fargo, Bank of America doesn’t offer 24/7 customer service. Branches only in 38 states.Less accessible customer service. Unlike Wells Fargo, Bank of America doesn’t offer 24/7 customer service. Branches only in 38 states. Bank of America doesn’t have branches in Alabama, Alaska, Hawaii, Louisiana, Mississippi, Montana, Nebraska, North Dakota, South Dakota, West Virginia, Wisconsin or Wyoming. Not on 

## C09 基于证据的简单推理（R023）

来源：dev_B1_k1，interaction_id=6e3bb48d-fab7-4c75-9c1d-5a047f1544f0。

问题：In which century was the person that this dish is named after born?

参考：The Chateaubriand dish is named after François-René de Chateaubriand, who was born on 4 September 1768.

原回答：18th century

实际评分文本：18th century

观察：实际提示列出Chateaubriand出生于1768，回答18th century与参考生日对应。

限制：AI建议CORRECT；仍不是已获真实裁判确认的正式成功案例。

实际提示证据（节选；完整文本见JSON）：

- `https://en.wikipedia.org/wiki/List_of_foods_named_after_people_chunk_1`：Poires Mary Garden – Mary Garden ... the 20th century. Born in Scotland, she emigrated to the U.S. as a child, then came to Paris in 1897 to complete her training. After her 1900 debut at the Opéra-Comique, she was much sought-after by composers for starring roles in their operas. Escoffier made this dish in her honor, ...Poires Mary Garden – Mary Garden (1874–1967) was a hugely popular opera singer in Europe and the U.S. at the start of the 20th

## C10 只见论坛标题就产生价格方向（R026）

来源：dev_B1_k1，interaction_id=2a4d9d48-a2c8-4051-8f95-46539b642c6a。

问题：is the kindle version of this book cheaper or more expensive than the paperback edition?

参考：on amazon.com, the paperback edition of this book is $15.59 while the kindle edition is $8.99, making it the least expensive option.

原回答：The Kindle edition is more expensive than the paperback.

实际评分文本：The Kindle edition is more expensive than the paperback.

观察：唯一提示证据是why is the kindle edition more expensive than a paperback的论坛标题；参考指定书籍的价格关系恰好相反。

限制：标题缺少目标书籍与价格，回答方向与标题一致；不能把该标题视为目标书籍的事实证据。

实际提示证据（节选；完整文本见JSON）：

- `https://uk.amazonforum.com/s/question/0D54P00006zI6P8SAK/why-is-the-kindle-edition-more-expensive-than-a-paperback_chunk_0`：why is the kindle edition more expensive than a paperback?
