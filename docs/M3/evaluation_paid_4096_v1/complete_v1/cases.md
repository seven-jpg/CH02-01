# 10个真实评分案例

标签取自本次4096实际运行，原因分析为AI意见，不代表因果实验。原离线案例快照保留。

## C01 数字来自错误门店对象

组别：dev_B1_k3；题号：efe0f64e-fbea-4b0e-b8a7-118e1433d35c

问题：how many locations do they have in new york city?

参考：empanada mama has 6 locations in new york city.

评分文本：73.

真实标签：**WRONG**（llm）

裁判原文：The prediction gives 73 locations, which does not match the ground truth of 6 locations.

Result: WRONG

观察：预测73对应提示中的7-Eleven纽约门店数；参考问的是empanada mama的6家。证据中可见明确对象错配。

限制：已观察到对象错配；其形成与只用含they的原问题检索有关，是否仅因缺图仍待后续多模态实验。

证据：[7-Eleven locations in New York City - See hours, menu, directions, tips, and photos.](https://app.foursquare.com/locations/7-eleven/new-york-city)

> NYC is finally getting the 7-11's we deserved!7-11 is planning to open hundreds of new stores in Manhattan - driving local bodegas out. NYC is mall-like enough for my taste already so I'm recommending a city-wide boycott of 7-11. Find 7-Eleven locations near you. See hours, menu, directions, photos, and tips for the 73 7-Eleven locations in New York City.

证据：[New York Service Locations and Hours](https://www.lyft.com/hub/hours/new-york)

> New York Service Locations and Hours

证据：[Nyc](https://www.nyc.gov/assets/dsny/site/resources/recycling-and-garbage-laws/collection-setout-laws-for-residents)

> Nyc

## C02 问题缺少明确对象时拒答

组别：dev_B0；题号：d998d529-026c-49f5-a673-e3450c4db395

问题：what's the typical blooming period for this plant?

参考：dracaena reflexa typically blooms in mid winter.

评分文本：I don't know.

真实标签：**MISSING**（idk）

裁判原文：官方拒答规则直接判定，未调用裁判。

观察：原问题只说this plant，B0未使用检索证据，回答标准拒答。

限制：拒答已确认；无法仅凭本条断言视觉模型一定能答对。

## C03 检索片段的恐龙对象与参考不符

组别：dev_B1_k1；题号：a9e389a2-74df-4c79-aa0c-ac7b3eda0eed

问题：How does the height of a human compare to this specific dinosaur?

参考：The Pachycephalosaurus had an approximate height of 10 feet, which is significantly taller than an average human, whose height averages around 5.6 feet. 

评分文本：The Utah Raptor, a dinosaur likely being referred to, was closer to the height of a man.

真实标签：**WRONG**（llm）

裁判原文：The prediction refers to a different dinosaur (Utah Raptor) and says it was closer to human height, which contradicts the ground truth about the Pachycephalosaurus being significantly taller than a human.  
Result: WRONG

观察：实际提示包含Utah Rapter接近人高的段落，预测Utah Raptor；参考要求Pachycephalosaurus约10英尺。

限制：证据和回答都出现另一对象；未重新检查原图，不能将责任全部归为生成错误。

证据：[r/Damnthatsinteresting on Reddit: Video I saw comparing a human to the size of many known dinosaurs](https://www.reddit.com/r/Damnthatsinteresting/comments/1002vsb/video_i_saw_comparing_a_human_to_the_size_of_many/)

> 829 votes, 83 comments. 20M subscribers in the Damnthatsinteresting community. For the most interesting things on the internetPosted by u/DirkDieGurke - 829 votes and 83 comments But I think this is mainly to show the scale comparison. Regardless they should’ve either said length or height in the video title. I think they pulled the models off Jurassic World: Evolution and then seemed to just make up heights or incorrectly use lengths in its place. Velociraptor wasn't 5'9" it was much smaller, closer to the size of a large turkey. Utah Rapter which was discovered in the 90s is likely what this is referring to which was closer to the height of a man.

## C04 相关证据下的部分正确回答

组别：dev_B1_k5；题号：b328be7f-85ba-4b36-9ad9-b5f2a080dc0b

问题：how are these different from hachiya persimmons?

参考：fuyu persimmons are round and squat, compared with hachiya persimmons, which are elongated in shape. moreover, fuyu persimmons are far less astringent than hachiya persimmons, and can be enjoyed while firm as well as soft, unlike hachiya perssimons, which much be incredibly soft to eat.

评分文本：Fuyu persimmons are not astringent, have a mild flavor, and can be eaten when firm, while Hachiya persimmons are astringent, tart, and must be eaten when extremely ripe.

真实标签：**CORRECT**（llm）

裁判原文：The prediction correctly captures the key differences in astringency and ripeness/firmness between Fuyu and Hachiya persimmons, which are grounded in the ground truth. Although it omits the shape difference, it does not contradict the ground truth and provides accurate additional details. According to guideline 7, the prediction is grounded by the ground truth.

Result: CORRECT

观察：提示含Fuyu/Hachiya的涩味、软硬度及形状信息；回答保留前两类差异，遗漏形状。

限制：实际裁判标签见本记录；遗漏形状是否影响判分存在解释边界，AI意见与裁判结果分别保留。

证据：[Fuyu vs. Hachiya Persimmon - Differences, Tips & Persimmon ...](https://www.youtube.com/watch?v=XUh6N_vLISk&pp=ygUMI3V2YXNwYXR0b2tp)

> Fuyu vs. Hachiya Persimmon - Differences, Tips & Persimmon ...

证据：[Fuyu Persimmon Vs Tropical Persimmon Vs Hachiya ...](https://www.tiktok.com/discover/fuyu-persimmon-vs-tropical-persimmon-vs-hachiya-persimmon)

> Fuyu Persimmon Vs Tropical Persimmon Vs Hachiya ...

证据：[Fuyu Persimmons and Hachiya Persimmons - Real Food, Mostly Plants](https://realfoodmostlyplants.com/fuyu-persimmons-and-hachiya-persimmons/)

> Ripe hachiyas are unbelievably soft – and are often almost liquified into a smooth pulp inside. You can tell the difference between Hachiya and Fuyu persimmons, because Hachiyas are elongated and oval shaped instead of squatted and round.Fuyu and Hachiya persimmons are the two most common persimmon varieties available in North America. What's the difference? They will ripen after being picked, so buying rock-hard fuyus and allowing them to ripen at home can be a good strategy. They can also be roasted to great effect. They have a mild, pumpkin-like flavor, and are often used as decoration during the Fall. Note: If you encounter seeds, simply remove and discard them. Hachiya persimmons are mouth-puckeringly tart unless extremely ripe. Ripe hachiyas are unbelievably soft – and are often almost liquified into a smooth pulp inside. You can tell the difference between Hachiya and Fuyu persimmons, because Hachiyas are elongated and oval shaped instead of squatted and round. Beneath the deep orange skin lies a golden flesh with flecks of brown, an indication that this is no ordinary persimmon. Many liken the fruit of this variety to both the Fuyu and Hachiya combined with a sprinkling of cinnamon.

证据：[Fuyu vs. Hachiya: Exploring the Two Sides of Persimmons](https://www.tiktok.com/@metmarket/video/7431609988705062190)

> Fuyu vs. Hachiya: Exploring the Two Sides of Persimmons

证据：[Fuyu vs. Hachiya Persimmons - Explained!](https://blog.bostonorganics.com/fuyu-vs-hachiya-persimmons-explained)

> Persimmons are one of fall's greatest gifts! Take a second to learn about the two most common varieties and discover how to best enjoy these tasty treats.Beautiful orangey, red Persimmons are now in season and will show up in many boxes during their October-February season. An often underrated treat, persimmons are sweet and delicious, adding a honey-like brightness to desserts, salads and as a snack. Two primary varieties of persimmons are available - fuyu and hachiya - with differences in how they are eaten and prepared. Both hachiya and fuyu persimmons can range from a light yellow-orange to a deeper, dark reddish orange. In shape, however, the two varieties have distinct differences. Hachiya persimmons are typically an elongated shape, often referred to as heart shaped or similar to an acorn or very plump (roma) tomato. The two varieties of persimmons differ greatly in their astringency. Astringency is the dry, puckering mouthfeel that the tannin of some fruit create if eaten before completely ripe. For persimmons, the hachiya variety is the astringent of the two. Thus, hachiya persimmons should be eaten they are totally softened - you know when to eat a hachiya when it feels like a water balloon or an over-ripe tomato. Many folks, after waiting until their hachiyas are very, very ripe, dig in to the fruit's creamy interior simply with a spoon and eat it plain or mix it in to yogurt or oatmeal for some added sweetness. Because of a perfectly ripe hachiya persimmon's texture, they are good for in baked goods like muffins, cookies and breads.

## C05 同一俗名对应不同物种

组别：dev_B1_k5；题号：ef31c7ad-356b-461c-ba64-4bf478aefe90

问题：Why is this plant called the Devil's tobacco?

参考：Lobelia polyphylla is called the Devil's tobacco because of its because of its hallucinogenic effects when smoked.

评分文本：It's called Devil's Tobacco because its narrow, hairy foliage bears a resemblance to tobacco.

真实标签：**WRONG**（llm）

裁判原文：The prediction gives a different reason for the name than the ground truth: it cites foliage resemblance to tobacco, while the ground truth says it is due to hallucinogenic effects when smoked. This is not grounded by the ground truth and is contradictory.

Result: WRONG

观察：提示第三条介绍Lobelia tupa并以叶片像烟草解释俗名；参考对象是Lobelia polyphylla，命名原因不同。回答跟随了提示片段。

限制：俗名检索有歧义；这支持证据对象错配分析，尚不证明检索器在可识别对象的情况下必然失败。

证据：[Devil's Tobacco - TripSit wiki](https://wiki.tripsit.me/wiki/Devil's_Tobacco)

> Devil's Tobacco - TripSit wiki

证据：[Devil's Tobacco (Lobelia excelsa) · iNaturalist](https://www.inaturalist.org/taxa/358073-Lobelia-excelsa)

> Devil's Tobacco (Lobelia excelsa) · iNaturalist

证据：[Lobelia tupa or Devil's Tobacco | Online Flower Garden](https://www.onlineflowergarden.com/2020/10/07/gardening/perennial-plants/lobelia-tupa/)

> Lobelia tupa is an upright plant with striking gray-green leaves. The narrow, hairy foliage bears a resemblance to tobacco, hence its intriguing nickname, Devil’s Tobacco. The stem of the plant boasts a dark purplish hue, adding a touch of drama to its overall presentation.Lobelia tupa is an upright plant with striking gray-green leaves. The narrow, hairy foliage bears a resemblance to tobacco, hence its intriguing nickname, Devil’s Tobacco. The stem of the plant boasts a dark purplish hue, adding a touch of drama to its overall presentation. Lobelia tupa, commonly known as Devil’s Tobacco, belongs to the Campanulaceae family of plants. This woody-based perennial hails from Chile, where it thrives in its native habitat. Planting: Lobelia tupa can be planted in either spring or fall. Choose a location that receives full sun or partial shade, depending on the climate. The soil should be well-drained and slightly acidic. Optimal growth is achieved in fertile, well-drained soil, and the plant thrives in sunlit areas. Watering: Regular watering is essential, particularly during the first year after planting. This helps the plant establish a strong root system. Once established, Lobelia tupa exhibits increased drought tolerance and requires less frequent watering.

证据：[medicinal herbs: DEVIL'S TOBACCO - Lobelia tupa](http://www.naturalmedicinalherbs.net/herbs/l/lobelia-tupa=devil's-tobacco.php)

> medicinal herbs: DEVIL'S TOBACCO - Lobelia tupa

证据：[devil's tobacco (Lobelia tupa) · iNaturalist](https://www.inaturalist.org/taxa/431237-Lobelia-tupa)

> devil's tobacco (Lobelia tupa) · iNaturalist

## C06 相同泛指问题难以确定花种

组别：dev_B1_k3；题号：5b2c9627-71b8-486f-9388-2b93c8a278e1

问题：what color are the blooms on this plant?

参考：the melaleuca camptoclada has mauve flowers.

评分文本：White or nearly white, and some hybrids have pink splotches or entirely pink petals.

真实标签：**WRONG**（llm）

裁判原文：The prediction states the blooms are white or pink, while the ground truth says the flowers are mauve. This contradicts the ground truth.

Result: WRONG

观察：提示列出Allium与Phalaenopsis等对象；预测取了兰花的白色/粉色内容，参考却是melaleuca camptoclada的mauve。

限制：错误对象证据清楚；需要M4验证加入图像身份能否缓解。

证据：[Allium flavum relatives | Pacific Bulb Society](https://www.pacificbulbsociety.org/pbswiki/index.php/AlliumFlavumRelatives)

> Allium carinatum L. is from much of Europe into Asia, naturalized elsewhere (the Brittish Isles). Informal sprays of little rose-purple, rose-pink, to white flowers dangling on very long slender pedicels, sometimes with bulbils (though many selections are bulbil-free).Allium carinatum ssp. pulchellum (G.Don) Bonnier & Layens is a European species that is very close to Allium flavum, flowering at the same time in June or July depending on the variety grown. The second photo is of a a dwarf bluish-purple form and a creamy white form, collected on Mt. Olympus, Greece. This is the plant that was offered by Hoog & Dix as a blue-flowered form of Allium flavum ssp. tauricum, but it is undoubtedly a "pulchellum" variant. Since the photograph shows such a confusing jumble of flowers, I circled the topic species in red. Allium carinatum ssp. pulchellum f. album is a white form often sold by Dutch bulb dealers. Photos below by Travis Owen of an adaptable selection. It has thrived in sun and shade, though it flowers better in the sun. The leaves are nearly evergreen in irrigated beds, dying down after new leaves have already broke the soil surface. Allium convallarioides Grossh. is a European species that's not generally in cultivation. It is a pleasing species with handsome umbels of white flowers. It is similar in appearance to Allium paniculatum L. and Allium pallens L., but in this species the slightly "ballooned" hollow leaves distinguish it from the other species.

证据：[301 Different Types of Flowers With Names and Pictures](https://www.epicgardening.com/types-of-flowers/)

> Finding the right flowers for your home or garden can be very challenging. Not only do you have to think about seasonality, but you have to consider color, climate, environment, sunlight, and more. In this article, gardening enthusiast Jason Wilson walks through over three hundred different ...Finding the right flowers for your home or garden can be very challenging. Not only do you have to think about seasonality, but you have to consider color, climate, environment, sunlight, and more. In this article, gardening enthusiast Jason Wilson walks through over three hundred different types of flowers including their names and pictures of each! This evergreen perennial exotic flower is sometimes called the Tail Flower. It has been awarded the RHS Garden Merit Award. It can bloom all year long in the right conditions, with one plant producing four to six flowers throughout the year. Flowers are six inches long, usually red in color, waxy in appearance, and have a tail-shaped spadic. Are you looking to add some flowers to your home or garden but aren't sure which to add? Explore over 300 different types of flowers! The flowers are star-shaped and arranged in clusters on top of sturdy stems. Bluestar is low maintenance, pest and disease resistant, and native to the US, making it a top choice for all American gardens. It needs moist and loamy soils to thrive. · Another name for these little beauties is Quaker Ladies. ... Also known as Quaker Ladies, this is a flowering perennial plant that boasts delicate and compact blooms.

证据：[How to Grow and Care for Moth Orchids | Gardener’s Path](https://gardenerspath.com/plants/flowers/grow-phalaenopsis-orchids/)

> Phalaenopsis orchids are fantastic but they have unique care requirements compared to other houseplants. Learn everything you need to know now in our guide.Phalaenopsis orchids are fantastic but they have unique care requirements compared to other houseplants. Learn what you need to know now! This species has small white flowers, but there are some hybrids that feature pink splotches or ones with entirely pink petals. Easily mistaken for P. amabilis, P. aphrodite flowers are about an inch smaller and pinkish-red at the base of the central petal. Their Diamond series features flowers with some pretty striking patterns and colors. The beautiful moon orchid, as this species is often called, is one of the varieties most commonly found in stores. P. amabilis flowers are typically white or nearly white. Each blossom can be up to four inches across and there can be dozens on a single plant. Each of these lasts for weeks, and the plant continually sends out new flowers all summer long. The plants themselves can grow over three feet tall indoors with proper care. Its size and beauty isn’t what makes P. amabilis so popular, though.

## C07 证据观点与固定参考冲突

组别：dev_B1_k1；题号：8e9efe39-8f8e-4f0b-867c-83faf740aa0d

问题：is this better for the environment than a real one?

参考：no, real christmas trees are better for the environment as they do not have to be shipped and help fight climate change until they are cut down.

评分文本：Neither, it's a complex issue with no clear-cut winner.

真实标签：**WRONG**（llm）

裁判原文：The prediction says neither is better, which contradicts the ground truth stating that real Christmas trees are better for the environment. So it is incorrect according to guideline 8.

Result: WRONG

观察：提示文章写both and neither、没有明确赢家；模型照此答Neither，而固定参考给出真实树更环保。

限制：此条按参考评分建议WRONG；不是标准MISSING。不能据此裁决现实环保争论。

证据：[Real vs. Fake Christmas Trees: Which is Better for The Environment?](https://www.texasdisposal.com/blog/real-vs-fake-christmas-trees/)

> Are real Christmas trees or fake Christmas trees better for the environment? The answer may seem obvious, but this debate is more complicated than it seems.Additionally, at the end of their lives, disposing of natural trees isn’t as easy as it may seem. While old Christmas trees are a good source for bonfire material, burning the tree simply releases the carbon dioxide it collected during its lifetime. If you are replacing firewood that would have been burned anyways, using a Christmas tree would become an environmentally conscious avenue. Fake Christmas Trees: Which is Better for The Environment? ... According to a 2021 survey, three-quarters of American households display Christmas trees during the holiday season. That’s about 94 million Christmas trees (even without factoring in the publicly displayed trees), and every one of those households had to make the same choice: display a real or a fake tree. Does the fresh, Christmas tree smell outweigh the necessary upkeep? Does the simplicity of a fake tree mean more than the specific look and feel of the tree? Is the family tradition of cutting a tree down something to look forward to, or is it not worth all the hassle? All of these considerations are valid and common reasons to pick a real or fake tree, but questions around the environmental impact of each method have recently risen into more prominence. So what’s better for the environment, real or fake? The quick answer is “both and neither.” There isn’t a clear-cut winner in this debate, but there are factors to consider and myths to dispel when making your selection. Before getting any further, there is one myth that needs to be addressed. Christmas trees are not being ripped from natural forests and ecosystems.

## C08 动态数值与参考时间不一致

组别：dev_B1_k1；题号：896302ba-4a70-415c-a649-bac94ee0ee0d

问题：compare the number of branches this bank has to bank of america.

参考：wells fargo and bank of america are among the largest banks in the united states, boasting extensive national networks. as of 2024, wells fargo operates 8,050 branches, outpacing bank of america's approximately 4,900 locations.

评分文本：Wells Fargo has more branches, with over 5,000 across 40 states, compared to Bank of America's 4,000 branches.

真实标签：**WRONG**（llm）

裁判原文：The prediction correctly states that Wells Fargo has more branches, but its branch counts (over 5,000 vs. 4,000) differ substantially from the ground truth (8,050 vs. approximately 4,900). According to guideline 3.2, this is incorrect.

Result: WRONG

观察：提示片段写Wells Fargo超过5000、Bank of America 4000；回答沿用这些值，参考为2024年8050/4900。

限制：比较方向一致但数字不符；片段未提供可验证的对应采集日期，不能擅自认定参考错误或用今天的数替换。

证据：[Bank of America vs. Wells Fargo: Which one wins? | finder.com](https://www.finder.com/wells-fargo-vs-bank-of-america-accounts)

> Less accessible customer service. Unlike Wells Fargo, Bank of America doesn’t offer 24/7 customer service. Branches only in 38 states.Less accessible customer service. Unlike Wells Fargo, Bank of America doesn’t offer 24/7 customer service. Branches only in 38 states. Bank of America doesn’t have branches in Alabama, Alaska, Hawaii, Louisiana, Mississippi, Montana, Nebraska, North Dakota, South Dakota, West Virginia, Wisconsin or Wyoming. Not on its deposit accounts. However, it does have the Go Far Rewards program for credit cards, which allows you to redeem points for travel, gift cards and more. Yes. Wells Fargo is currently offering up to $400 when you open an eligible checking account and perform qualifying activities. Wells Fargo vs. Bank of America branches and ATMs More branches. Wells Fargo has over 5,000 Branches across 40 states compared to Bank of America‘s 4,000.

## C09 基于证据的简单推理

组别：dev_B1_k1；题号：6e3bb48d-fab7-4c75-9c1d-5a047f1544f0

问题：In which century was the person that this dish is named after born?

参考：The Chateaubriand dish is named after François-René de Chateaubriand, who was born on 4 September 1768.

评分文本：18th century

真实标签：**CORRECT**（llm）

裁判原文：The person, François-René de Chateaubriand, was born in 1768, which is in the 18th century. The prediction matches this.

Result: CORRECT

观察：实际提示列出Chateaubriand出生于1768，回答18th century与参考生日对应。

限制：AI建议CORRECT；仍不是已获真实裁判确认的正式成功案例。

证据：[List of foods named after people - Wikipedia](https://en.wikipedia.org/wiki/List_of_foods_named_after_people)

> Poires Mary Garden – Mary Garden ... the 20th century. Born in Scotland, she emigrated to the U.S. as a child, then came to Paris in 1897 to complete her training. After her 1900 debut at the Opéra-Comique, she was much sought-after by composers for starring roles in their operas. Escoffier made this dish in her honor, ...Poires Mary Garden – Mary Garden (1874–1967) was a hugely popular opera singer in Europe and the U.S. at the start of the 20th century. Born in Scotland, she emigrated to the U.S. as a child, then came to Paris in 1897 to complete her training. After her 1900 debut at the Opéra-Comique, she was much sought-after by composers for starring roles in their operas. Escoffier made this dish in her honor, and is said to have told a friend once that all his best dishes had been created "for the ladies". Queen of Sheba cake – the originally French gâteau de la reine Saba, a chocolate cake, is named for the 10th-century-BC African Queen of Sheba, guest of King Solomon of Israel. Lamprey à la Rabelais – François Rabelais (c. 1484–1553), French monk, turned physician, turned famed writer and satirist, was honored in this dish by Delmonico's chef Charles Ranhofer. Tournedos Rachel – from singing in the streets of Paris as a child, Swiss-born Elisa-Rachel Félix (1821–1858) went on to become known as the greatest French tragedienne of her day. He liked to cook, and is remembered in San Francisco restaurants with this dish. Reggie Bar – Reggie Jackson (born 1946), American baseball player of the 1970s, had this now-discontinued candy bar named for him. Salad Réjane – Gabrielle Réjane was the stage name for Gabrielle-Charlotte Reju (1856–1920), a French actress at the start of the 20th century. Charlotte Russe – a dessert invented by the French chef Marie Antoine Carême (1784–1833), who named it in honor of his Russian employer Czar Alexander I ("Russe" being the French equivalent of the adjective, "Russian"). Other historians say that this sweet dish took its name from Queen Charlotte (1744–1818), wife of George III. Chateaubriand – a cut and a recipe for steak named for Vicomte François René de Chateaubriand (1768–1848), French writer and diplomat. His chef Montinireil is thought to have created the dish around 1822 while Chateaubriand was ambassador to England.

## C10 只见论坛标题就产生价格方向

组别：dev_B1_k1；题号：2a4d9d48-a2c8-4051-8f95-46539b642c6a

问题：is the kindle version of this book cheaper or more expensive than the paperback edition?

参考：on amazon.com, the paperback edition of this book is $15.59 while the kindle edition is $8.99, making it the least expensive option.

评分文本：The Kindle edition is more expensive than the paperback.

真实标签：**WRONG**（llm）

裁判原文：The prediction contradicts the ground truth: the Kindle edition is cheaper ($8.99) than the paperback ($15.59), not more expensive.  
Result: WRONG

观察：唯一提示证据是why is the kindle edition more expensive than a paperback的论坛标题；参考指定书籍的价格关系恰好相反。

限制：标题缺少目标书籍与价格，回答方向与标题一致；不能把该标题视为目标书籍的事实证据。

证据：[why is the kindle edition more expensive than a paperback?](https://uk.amazonforum.com/s/question/0D54P00006zI6P8SAK/why-is-the-kindle-edition-more-expensive-than-a-paperback)

> why is the kindle edition more expensive than a paperback?
