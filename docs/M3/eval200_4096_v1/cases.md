# eval200：10个典型案例

案例是目的性选择，用于解释现象，不代表类别分布。标签为本次真实裁判／规则成绩；原因解释为AI辅助分析，不是因果实验。复核时不查看图像，也未增加付费请求。

## C01 电影对象错配

题号：`34fc07c2-3e27-4f09-a154-26e23b83d0ed`

问题：what is that movie about?

参考：piece by piece is an animated biographical documentary comedy film that follows the life and career of american musician pharrell williams, through the lens of lego animation.

B0原回答：I don't know.

B0评分文本：I don't know.

B0标签：**MISSING**（idk）

B0评分理由：

> None

B1 k1原回答：The movie "One Fast Move" is a sports drama about a character's experiences with familial relationships, particularly those marked by absence and the longing for connection.

B1 k1评分文本：The movie "One Fast Move" is a sports drama about a character's experiences with familial relationships, particularly those marked by absence and the longing for connection.

B1 k1标签：**WRONG**（llm）

B1 k1评分理由：

> The prediction describes a different movie (“One Fast Move”) rather than the movie in the ground truth (“Piece by Piece”), so it is unrelated/contradictory to the ground truth.
> 
> Result: WRONG

观察与限制：检索标题及内容为One Fast Move，预测沿用该电影；参考对象为Piece by Piece。可见对象错配，不能单凭这一例断定缺图是唯一原因。

检索来源：[One Fast Move (2024) - User reviews - IMDb](https://www.imdb.com/title/tt21096576/reviews/)；doc_id：`https://www.imdb.com/title/tt21096576/reviews/_chunk_11`

证据摘录：

> One Fast Move (2024) - Movies, TV, Celebs, and more...Now I didn't have any excitement for this movie, but I gotta be honest after watching this movie, I actually enjoyed this movie more than I would've anticipated. Positives for One Fast Move (2024): This was a very simple sports drama movie with some great racing scenes and it's done very well. I also really enjoyed his dynamics with both Eric Dane and Maia Reficco. And finally, the racing scenes in this movie are done very well. Negatives for One Fast Move (2024): There are certain things about KJ Apa's charactersy particularly in regards to his backstory that really left me scratching my head. The narrative is well-paced, balancing action with moments of introspection, making it a compelling watch. Overall, "One Fast Move" is a good film that resonates with anyone who has experienced the complexities of familial relationships, especially those marked by absence and the longing for connection. The actors are very fair in the way they express their feelings without saying them openlytI understand that motorcycle enthusiasts are a little disappointed, but I am very surprised by the violence of their comments. One Fast Move is a fi

实际提示使用的证据：

> One Fast Move (2024) - Movies, TV, Celebs, and more...Now I didn't have any excitement for this movie, but I gotta be honest after watching this movie, I actually enjoyed this movie more than I would've anticipated. Positives for One Fast Move (2024): This was a very simple sports drama movie with some great racing scenes and it's done very well. I also really enjoyed his dynamics with both Eric Dane and Maia Reficco. And finally, the racing scenes in this movie are done very well. Negatives for One Fast Move (2024): There are certain things about KJ Apa's charactersy particularly in regards to his backstory that really left me scratching my head. The narrative is well-paced, balancing action with moments of introspection, making it a compelling watch. Overall, "One Fast Move" is a good film that resonates with anyone who has experienced the complexities of familial relationships, especially those marked by absence and the longing for connection. The actors are very fair in the way they express their feelings without saying them openlytI understand that motorcycle enthusiasts are a little disappointed, but I am very surprised by the violence of their comments. One Fast Move is a film that touches your heart.


## C02 数字正确摘录但对象错误

题号：`5a3a5ec1-f231-4c4f-a833-c42af35ec177`

问题：how much does one of these weigh?

参考：member's mark gas patio heater's assembled weight is 55 pounds.

B0原回答：I don't know.

B0评分文本：I don't know.

B0标签：**MISSING**（idk）

B0评分理由：

> None

B1 k1原回答：120-150 pounds.

B1 k1评分文本：120-150 pounds.

B1 k1标签：**WRONG**（llm）

B1 k1评分理由：

> The predicted weight (120–150 pounds) does not match the ground truth weight (55 pounds).
> 
> Result: WRONG

观察与限制：证据讨论烘干机120–150磅，预测复述该区间；参考问的是55磅的露台取暖器。摘录真实数字不保证答对所问物品。

检索来源：[How Much Does the Average Dryer Weigh? Discover Safe Moving Tips Here](https://appliancemastery.com/how-much-does-the-average-dryer-weigh/)；doc_id：`https://appliancemastery.com/how-much-does-the-average-dryer-weigh/_chunk_1`

证据摘录：

> Discover the average weight of dryers and essential tips for moving them safely in this insightful article. Learn about the importance of preparation, using proper tools like a dolly and moving straps, lifting with caution, and the option of seeking professional assistance for heavier models.Average Weight: The average weight of a dryer typically ranges from 120 to 150 pounds. Type Variation: Gas dryers tend to be a bit heavier than electric dryers due to additional components. Ultra-Light Models: Some compact or portable dryers weigh less than 100 pounds, making them easier to move around. Heavy-Duty Models: On the other hand, commercial dryers can weigh over 200 pounds due to their larger capacity and durable build. See Also Find Eco-Friendly Ways to Recycle Old Washers and Dryers Locally Ever wondered how much your trusty dryer actually weighs? Picture this: you’re moving into a new home and suddenly realize you have to lug that bulky appliance up a flight of stairs. The struggle is real! But fear not, we’ve got you covered. In this article, we’ll uncover the mystery behind the average weight of dryers and provide you with some valuable insights. Have you ever found yourself in 

实际提示使用的证据：

> Discover the average weight of dryers and essential tips for moving them safely in this insightful article. Learn about the importance of preparation, using proper tools like a dolly and moving straps, lifting with caution, and the option of seeking professional assistance for heavier models.Average Weight: The average weight of a dryer typically ranges from 120 to 150 pounds. Type Variation: Gas dryers tend to be a bit heavier than electric dryers due to additional components. Ultra-Light Models: Some compact or portable dryers weigh less than 100 pounds, making them easier to move around. Heavy-Duty Models: On the other hand, commercial dryers can weigh over 200 pounds due to their larger capacity and durable build. See Also Find Eco-Friendly Ways to Recycle Old Washers and Dryers Locally Ever wondered how much your trusty dryer actually weighs? Picture this: you’re moving into a new home and suddenly realize you have to lug that bulky appliance up a flight of stairs. The struggle is real! But fear not, we’ve got you covered. In this article, we’ll uncover the mystery behind the average weight of dryers and provide you with some valuable insights. Have you ever found yourself in a pickle trying to figure out how to transport or install a dryer without breaking a sweat? Well, understanding the weight of your dryer can save you from unnecessary hassle and frustration. Understanding these factors can give you insight into why dryers vary in weight across different models and types. Here are some key influencers to consider: Larger dryers with higher capacity drums tend to we


## C03 检索后比较方向正确

题号：`cbd67f91-c5ef-4ce1-a45e-458ee3ed2b14`

问题：Between this specie and cats, which has the highest number of breeds?

参考：According to the American Kennel Club, there are 190 dog breeds, in contrast to the Cat Fanciers' Association, which lists 42 different breeds of cats.

B0原回答：I don't know.

B0评分文本：I don't know.

B0标签：**MISSING**（idk）

B0评分理由：

> None

B1 k1原回答：Dogs.

B1 k1评分文本：Dogs.

B1 k1标签：**CORRECT**（llm）

B1 k1评分理由：

> The prediction "Dogs" matches the ground truth, which states dogs have 190 breeds compared to cats' 42 breeds. Thus, the prediction is correct.
> 
> Result: CORRECT

观察与限制：证据标题指出猫品种少于狗，预测回答Dogs，与参考比较方向一致。无需复述全部品种数量也能回答所问方向。

检索来源：[Why are there fewer breeds of cats compared to dogs?](https://pet-happy.com/why-are-there-fewer-cat-breeds-than-dog-breeds/)；doc_id：`https://pet-happy.com/why-are-there-fewer-cat-breeds-than-dog-breeds/_chunk_0`

证据摘录：

> In this article, you&#x27;ll learn the history of cat breeds, how many breeds of cats there are, categories, most popular breeds, &amp; the best cat breed for allergies.The above gives an rough insight into the number of feline breeds. Many national and regional organizations exist, and the number of unique ones they recognize differ, but most acknowledge between 40 and 80. The more intriguing question is, how has this number changed over time? There are many different categories of cat breeds, but they can generally be divided into two main types of cats: pedigree and non-pedigree. The above gives an rough insight into the number of cat breeds. Many national and regional organizations exist, and the number of breeds they recognize differ, but most acknowledge between 40 and 80. How many cat breeds do you know? The first that come to my mind are Persian, Siamese, British Shorthair, Devon Rex, and Maine Coon, but this is where it usually stops. This is because there are not as many cat breeds as there are dog breeds. Despite the above, it will likely take many centuries (if ever) before we see as much variety in cat breeds as we do in dogs. This is because dogs were bred for their s

实际提示使用的证据：

> In this article, you'll learn the history of cat breeds, how many breeds of cats there are, categories, most popular breeds, & the best cat breed for allergies.The above gives an rough insight into the number of feline breeds. Many national and regional organizations exist, and the number of unique ones they recognize differ, but most acknowledge between 40 and 80. The more intriguing question is, how has this number changed over time? There are many different categories of cat breeds, but they can generally be divided into two main types of cats: pedigree and non-pedigree. The above gives an rough insight into the number of cat breeds. Many national and regional organizations exist, and the number of breeds they recognize differ, but most acknowledge between 40 and 80. How many cat breeds do you know? The first that come to my mind are Persian, Siamese, British Shorthair, Devon Rex, and Maine Coon, but this is where it usually stops. This is because there are not as many cat breeds as there are dog breeds. Despite the above, it will likely take many centuries (if ever) before we see as much variety in cat breeds as we do in dogs. This is because dogs were bred for their service. Such as to herd sheep, hunt, and pull sleds through the snow.


## C04 答案正确但证据对象不同

题号：`cd0cc4cd-34e9-4daa-a189-25e4840f0fe2`

问题：what type of fuel does this vehicle typically use?

参考：the toyota fj cruiser typically uses gasoline.

B0原回答：I don't know.

B0评分文本：I don't know.

B0标签：**MISSING**（idk）

B0评分理由：

> None

B1 k1原回答：Regular unleaded gasoline.

B1 k1评分文本：Regular unleaded gasoline.

B1 k1标签：**CORRECT**（llm）

B1 k1评分理由：

> The prediction specifies "Regular unleaded gasoline," which is a type of gasoline and is grounded by the ground truth stating the vehicle typically uses gasoline.
> 
> Result: CORRECT

观察与限制：证据标题指向Volvo V70，参考对象为Toyota FJ Cruiser；预测汽油与参考相符。标签正确不能证明证据准确匹配，也不能确认模型依赖了该证据。

检索来源：[Which type of fuel should you use in your V70?](https://www.startmycar.com/us/volvo/v70/guides/recommended-type-of-fuel)；doc_id：`https://www.startmycar.com/us/volvo/v70/guides/recommended-type-of-fuel_chunk_0`

证据摘录：

> Which type of fuel should you use in your V70?

实际提示使用的证据：

> Which type of fuel should you use in your V70?


## C05 人口数字不符

题号：`d61f9487-e538-44a8-87ef-9950267d5128`

问题：what is the population of this county?

参考：the county population is 32,172.

B0原回答：I don't know.

B0评分文本：I don't know.

B0标签：**MISSING**（idk）

B0评分理由：

> None

B1 k1原回答：448,229.

B1 k1评分文本：448,229.

B1 k1标签：**WRONG**（llm）

B1 k1评分理由：

> The prediction gives a population of 448,229, which does not match the ground truth of 32,172.
> 
> Result: WRONG

观察与限制：证据指向Santa Barbara County，而预测448229与参考32172不符。证据记录不能单独确认参考县名，不据此猜测具体目标县。

检索来源：[Santa Barbara County, California - Wikipedia](https://en.wikipedia.org/wiki/Santa_Barbara_County,_California)；doc_id：`https://en.wikipedia.org/wiki/Santa_Barbara_County,_California_chunk_8`

证据摘录：

> Four of the Channel Islands – San Miguel Island, Santa Cruz Island, Santa Rosa Island and Santa Barbara Island – are in Santa Barbara County. They form the largest part of the Channel Islands National Park (which also includes Anacapa Island in Ventura County). Santa Barbara County has a mountainous interior abutting several coastal plains on the west and south coasts of the county. The largest concentration of population ...Four of the Channel Islands – San Miguel Island, Santa Cruz Island, Santa Rosa Island and Santa Barbara Island – are in Santa Barbara County. They form the largest part of the Channel Islands National Park (which also includes Anacapa Island in Ventura County). Santa Barbara County has a mountainous interior abutting several coastal plains on the west and south coasts of the county. The largest concentration of population is on the southern coastal plain, referred to as the "south coast" – meaning the part of the county south of the Santa Ynez Mountains. The presidio and mission kept Vizcaino's denomination, as did the later city and county – a common practice which has preserved the names of many of the 21 California Missions. Other missions in Santa Barbara C

实际提示使用的证据：

> Four of the Channel Islands – San Miguel Island, Santa Cruz Island, Santa Rosa Island and Santa Barbara Island – are in Santa Barbara County. They form the largest part of the Channel Islands National Park (which also includes Anacapa Island in Ventura County). Santa Barbara County has a mountainous interior abutting several coastal plains on the west and south coasts of the county. The largest concentration of population ...Four of the Channel Islands – San Miguel Island, Santa Cruz Island, Santa Rosa Island and Santa Barbara Island – are in Santa Barbara County. They form the largest part of the Channel Islands National Park (which also includes Anacapa Island in Ventura County). Santa Barbara County has a mountainous interior abutting several coastal plains on the west and south coasts of the county. The largest concentration of population is on the southern coastal plain, referred to as the "south coast" – meaning the part of the county south of the Santa Ynez Mountains. The presidio and mission kept Vizcaino's denomination, as did the later city and county – a common practice which has preserved the names of many of the 21 California Missions. Other missions in Santa Barbara County are located in Santa Ynez and Lompoc. European contacts had devastating effects on the Chumash people, including a series of disease epidemics that drastically reduced Chumash population. In 2022, cauliflower was number two due to the weather and popularity of cauliflower rice. County farmers began growing hemp after it was removed from a list of controlled substances along with other provis


## C06 比较问题只回答一侧背景

题号：`c43db3c4-83af-4b79-96a9-cdb8901c6b92`

问题：what is the difference between the origin of this food and sushi?

参考：onigiri makes rice portable and easy to eat as well as preserving it, while sushi originated as a way of preserving fish.

B0原回答：I don't know

B0评分文本：I don't know

B0标签：**MISSING**（idk）

B0评分理由：

> None

B1 k1原回答：The origin of the food is fermented rice in Southeast Asia, while sushi is the modern form that originated in Japan.

B1 k1评分文本：The origin of the food is fermented rice in Southeast Asia, while sushi is the modern form that originated in Japan.

B1 k1标签：**WRONG**（llm）

B1 k1评分理由：

> The prediction contradicts the ground truth: it does not mention onigiri’s role in making rice portable/preserved, and it describes sushi’s origin differently from the ground truth (“preserving fish” vs. “modern form in Japan”). So it is incorrect according to guideline 8.
> 
> Result: WRONG

观察与限制：证据及预测集中在寿司起源，未表达参考所要求的饭团便携／保鲜与寿司保存鱼的对比。

检索来源：[The Origins of Sushi: Is Sushi Japanese or Chinese Dish?](https://www.chefmaezaki.com/post/the-origins-of-sushi-is-sushi-japanese-or-chinese-dish)；doc_id：`https://www.chefmaezaki.com/post/the-origins-of-sushi-is-sushi-japanese-or-chinese-dish_chunk_1`

证据摘录：

> Alright, we get it. You may be wondering: since when is there a sushi history? Well, turns out this popular dish really does have quite an interesting history! The earliest forms of sushi originated in Southeast Asia, where fermented rice was commonly eaten as a way to preserve fish.The Japanese adapted and experimented with sushi over the centuries, rapidly reducing fermentation time and introducing innovations like nigiri. So modern fresh sushi is really a Japanese creation, even though its ancestral origins are Chinese. Other Asian countries like Korea and Vietnam also have their own versions of sushi which have evolved locally. Sushi is one of the most popular foods around the world today. The combination of raw fish, rice, and seaweed seems distinctly Japanese. But is sushi actually from Japan, or does it have roots in Chinese cuisine? The history and origins of sushi are complex and fascinating. Is sushi Japanese or Chinese? Well, it started in China but developed its modern form that we know today in Japan. Learn about its fascinating evolution... Alright, we get it. You may be wondering: since when is there a sushi history? Well, turns out this popular dish really does have

实际提示使用的证据：

> Alright, we get it. You may be wondering: since when is there a sushi history? Well, turns out this popular dish really does have quite an interesting history! The earliest forms of sushi originated in Southeast Asia, where fermented rice was commonly eaten as a way to preserve fish.The Japanese adapted and experimented with sushi over the centuries, rapidly reducing fermentation time and introducing innovations like nigiri. So modern fresh sushi is really a Japanese creation, even though its ancestral origins are Chinese. Other Asian countries like Korea and Vietnam also have their own versions of sushi which have evolved locally. Sushi is one of the most popular foods around the world today. The combination of raw fish, rice, and seaweed seems distinctly Japanese. But is sushi actually from Japan, or does it have roots in Chinese cuisine? The history and origins of sushi are complex and fascinating. Is sushi Japanese or Chinese? Well, it started in China but developed its modern form that we know today in Japan. Learn about its fascinating evolution... Alright, we get it. You may be wondering: since when is there a sushi history? Well, turns out this popular dish really does have quite an interesting history! The earliest forms of sushi originated in Southeast Asia, where fermented rice was commonly eaten as a way to preserve fish.


## C07 材料比较的对象错配

题号：`360824f1-6cfb-46f1-a3ad-0cc88f583242`

问题：is this better in metal or plastic?

参考：metal rakes are ideal for tougher projects like moving sand or stones, while plastic rakes are great for raking leaves or lawns.

B0原回答：I don't know.

B0评分文本：I don't know.

B0标签：**MISSING**（idk）

B0评分理由：

> None

B1 k1原回答：Plastic sink drain assemblies are generally lighter, less expensive, and easier to install than metal ones.

B1 k1评分文本：Plastic sink drain assemblies are generally lighter, less expensive, and easier to install than metal ones.

B1 k1标签：**WRONG**（llm）

B1 k1评分理由：

> The prediction discusses plastic sink drain assemblies, while the ground truth is about metal and plastic rakes. This is unrelated to the ground truth, so it is incorrect according to guideline 8.
> 
> Result: WRONG

观察与限制：证据标题为水槽排水组件的金属／塑料比较，参考为耙子；预测回答排水组件的优点。

检索来源：[What are the advantages of plastic versus metal sink drain assemblies? - Quora](https://www.quora.com/What-are-the-advantages-of-plastic-versus-metal-sink-drain-assemblies)；doc_id：`https://www.quora.com/What-are-the-advantages-of-plastic-versus-metal-sink-drain-assemblies_chunk_0`

证据摘录：

> What are the advantages of plastic versus metal sink drain assemblies? - Quora

实际提示使用的证据：

> What are the advantages of plastic versus metal sink drain assemblies? - Quora


## C08 所有权关系错配

题号：`0a1f3aaa-7a4f-489a-954b-312393fcae79`

问题：do the current owners of this have a familial connection to the original owner?

参考：yes, the current owners of wölffer estate vineyard, marc and joey wölffer, are the children of the original owner, christian wölffer.

B0原回答：I don't know.

B0评分文本：I don't know.

B0标签：**MISSING**（idk）

B0评分理由：

> None

B1 k1原回答：No.

B1 k1评分文本：No.

B1 k1标签：**WRONG**（llm）

B1 k1评分理由：

> The prediction contradicts the ground truth, which states there is a familial connection. Therefore, the prediction is incorrect.
> 
> Result: WRONG

观察与限制：证据为Jimmy Dean公司收购历史，参考为Wölffer葡萄园原主与现主的亲属关系；预测No与参考Yes相反。

检索来源：[Where Is Jimmy Dean Sausage Made? (Answered!) – Home Kitchen Talk](https://homekitchentalk.com/where-is-jimmy-dean-sausage-made/)；doc_id：`https://homekitchentalk.com/where-is-jimmy-dean-sausage-made/_chunk_3`

证据摘录：

> A great man once said, “Sausage is a great deal like life. You get out of it about what you put in.” That man, of course, was Jimmy Dean. Jimmy Dean was a successful countryThe fully cooked sausage includes Dean’s signature flavors using fresh premium pork. They can be enjoyed anytime, day or night. ... A warm croissant, biscuit, or muffin stuffed with premium ingredients and tasty meat. ... For those who love breakfast for dinner: a frozen breakfast bowl offering up to 26g of protein, including eggs and cheese. In 1984, the Sara Lee Corporation (a Fortune 100 company) bought the Jimmy Dean Meat Company for $80 million. Dean explained that in 2004 he was dropped entirely as the spokesman because he was “too old.” · In 2014, Sara Lee Foods and Hillshire Farm were bought by Tyson Foods. They won a bidding war against Pilgrim’s Pride and agreed to purchase Sara Lee and Ball Park hot dogs for $8.5 billion. Today, the Jimmy Dean brand is worth around $1.8 billion and has a massive portfolio offering more than 170 breakfast items. Jimmy Dean was a successful country singer, actor, and businessman who had no idea that his sausage company would one day become American’s favorite. Jimmy Dea

实际提示使用的证据：

> A great man once said, “Sausage is a great deal like life. You get out of it about what you put in.” That man, of course, was Jimmy Dean. Jimmy Dean was a successful countryThe fully cooked sausage includes Dean’s signature flavors using fresh premium pork. They can be enjoyed anytime, day or night. ... A warm croissant, biscuit, or muffin stuffed with premium ingredients and tasty meat. ... For those who love breakfast for dinner: a frozen breakfast bowl offering up to 26g of protein, including eggs and cheese. In 1984, the Sara Lee Corporation (a Fortune 100 company) bought the Jimmy Dean Meat Company for $80 million. Dean explained that in 2004 he was dropped entirely as the spokesman because he was “too old.” · In 2014, Sara Lee Foods and Hillshire Farm were bought by Tyson Foods. They won a bidding war against Pilgrim’s Pride and agreed to purchase Sara Lee and Ball Park hot dogs for $8.5 billion. Today, the Jimmy Dean brand is worth around $1.8 billion and has a massive portfolio offering more than 170 breakfast items. Jimmy Dean was a successful country singer, actor, and businessman who had no idea that his sausage company would one day become American’s favorite. Jimmy Dean opened his first sausage plant in 1969 in Plainview, Texas.


## C09 B0宽泛回答获正确、B1拒答

题号：`d9f20acb-a904-4c52-8d62-b0a5d08aca3c`

问题：why don't they go blind from sandstorms?

参考：camels are protected from blowing sand by their heavy eyelashes.

B0原回答：The eyes have a natural protective mechanism that helps prevent damage from sand particles.

B0评分文本：The eyes have a natural protective mechanism that helps prevent damage from sand particles.

B0标签：**CORRECT**（llm）

B0评分理由：

> The prediction is a generalized version of the ground truth: heavy eyelashes are a natural protective mechanism for the eyes against sand. Thus it is grounded by the ground truth.
> 
> Result: CORRECT

B1 k1原回答：I don't know.

B1 k1评分文本：I don't know.

B1 k1标签：**MISSING**（idk）

B1 k1评分理由：

> None

观察与限制：B0只说眼睛存在天然保护机制，未明确参考的浓密睫毛，但本次裁判接受为CORRECT；B1拒答。这体现裁判对概括答案的宽松程度，值得真人重点复核。保留原始标签，不另行调用裁判或改分。

检索来源：[Shabanu Blog Post: How to Survive a Sandstorm by Shabanu | Olivia's Digital Portfolio](https://blog.lrei.org/22oliviabportfolio/2016/05/02/shabanu-blog-post-written-by-shabanu/)；doc_id：`https://blog.lrei.org/22oliviabportfolio/2016/05/02/shabanu-blog-post-written-by-shabanu/_chunk_1`

证据摘录：

> The sand always goes into the dunes and low to the ground, so the storm will be less forceful at the top of a hill. Look for high ground if you can find a safe, solid, high point, but only if the storm doesn’t have lightning and there is no danger of being hit by really heavy, flying piece of debris. If you have a camel...The sand always goes into the dunes and low to the ground, so the storm will be less forceful at the top of a hill. Look for high ground if you can find a safe, solid, high point, but only if the storm doesn’t have lightning and there is no danger of being hit by really heavy, flying piece of debris. If you have a camel, have it sit down and press yourself against its side so you are safer from flying objects. She is also a nomad so she lives in different parts of Pakistan before she is married. She has an aunt and two little cousins. She also has a dog named Sher Dil and a camel named Mithoo. She takes care of all the camels and goes to the Sibi fair with her father to sell them. I am so happy that we had shelter but this is what you should do in case you are outside in a sandstorm. ... Put a chadr or turban over your face so that you are protected and the sand d

实际提示使用的证据：

> The sand always goes into the dunes and low to the ground, so the storm will be less forceful at the top of a hill. Look for high ground if you can find a safe, solid, high point, but only if the storm doesn’t have lightning and there is no danger of being hit by really heavy, flying piece of debris. If you have a camel...The sand always goes into the dunes and low to the ground, so the storm will be less forceful at the top of a hill. Look for high ground if you can find a safe, solid, high point, but only if the storm doesn’t have lightning and there is no danger of being hit by really heavy, flying piece of debris. If you have a camel, have it sit down and press yourself against its side so you are safer from flying objects. She is also a nomad so she lives in different parts of Pakistan before she is married. She has an aunt and two little cousins. She also has a dog named Sher Dil and a camel named Mithoo. She takes care of all the camels and goes to the Sibi fair with her father to sell them. I am so happy that we had shelter but this is what you should do in case you are outside in a sandstorm. ... Put a chadr or turban over your face so that you are protected and the sand doesn’t go into your eyes, nostrils, or mouth. We just had a really large sandstorm cross our camp. The winds were blowing hard and whipping our skin. Even in the safety of our mud hut, dust still got in and made our throats as dry as the desert sand.


## C10 拒答伴随错误对象解释

题号：`f6fa0a84-2952-4a82-9783-cbd284ea4ac5`

问题：what is the average lifespan of these animals?

参考：12-17 years

B0原回答：I don't know.

B0评分文本：I don't know.

B0标签：**MISSING**（idk）

B0评分理由：

> None

B1 k1原回答：I don't know. The text only provides a range of lifespans for black and white rhinos in captivity, but not an average lifespan.

B1 k1评分文本：I don't know. The text only provides a range of lifespans for black and white rhinos in captivity, but not an average lifespan.

B1 k1标签：**MISSING**（idk）

B1 k1评分理由：

> None

观察与限制：B1以标准拒答开头，后文讨论犀牛寿命；依既定外层规则仍为MISSING。参考为12–17年。后文对象不符不能把规则拒答改为技术失败，也不在eval临时修改规则。

检索来源：[HOW LONG DO RHINOS LIVE? Facts and species!](https://howlongdolive.com/rhinos-lifespan/)；doc_id：`https://howlongdolive.com/rhinos-lifespan/_chunk_2`

证据摘录：

> All about HOW LONG DO GIRAFFES LIVE. Their life expectancy depends on many things, like species, predators, hunting...But, it is not unusual for young rhinos to become victims of other predators like hyenas, lions, wild dogs and crocodiles. The governments in all the countries where rhinos live have taken measures to prevent poaching. They are also trying to stop illegal horn trade which makes hunters kill rhinos. Rhinos or rhinoceroses are well-known for their large bodies, huge legs and their horns (some of them have one other have two horns). The black rhinos live between 35 and 50 years while the white rhinos live between 40 and 50 years. These figures are mostly related to the animals that live in captivity. It’s very difficult to determine their life expectancy in the wild because they are affected by poaching, predators, and hunting.

实际提示使用的证据：

> All about HOW LONG DO GIRAFFES LIVE. Their life expectancy depends on many things, like species, predators, hunting...But, it is not unusual for young rhinos to become victims of other predators like hyenas, lions, wild dogs and crocodiles. The governments in all the countries where rhinos live have taken measures to prevent poaching. They are also trying to stop illegal horn trade which makes hunters kill rhinos. Rhinos or rhinoceroses are well-known for their large bodies, huge legs and their horns (some of them have one other have two horns). The black rhinos live between 35 and 50 years while the white rhinos live between 40 and 50 years. These figures are mostly related to the animals that live in captivity. It’s very difficult to determine their life expectancy in the wild because they are affected by poaching, predators, and hunting.

