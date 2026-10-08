---
id: fengshu-mcp
title: 风叔知识库 MCP
aliases: [风叔知识库 MCP, 风叔知识库, 风叔 MCP, 风叔MCP, search_fengshu_knowledge, get_chunk_context]
---
# 风叔知识库 MCP（博主文章 → 混合检索 → MCP 工具）

## 这是什么

风叔知识库 MCP 是我自己做的一个工具：我把自媒体博主「风叔」的公众号文章爬取下来，清洗、切块、做 embedding，存成一个向量知识库；在上面实现了混合检索（向量检索 + 关键词 / 精确匹配）；整套检索服务部署在 Cloudflare 上，并包装成一个 MCP Server，让 Agent 可以直接连接调用。

做完能跑之后，我又持续优化了好几轮。这个过程最大的价值在于：我的关注点从「功能能不能跑」转到了「这个系统是不是适合被模型稳定调用」。它同时练到了 Agent 工程、MCP 接口设计、RAG、上下文工程（Context Engineering）和系统架构。

## 整体架构（分层）

- 数据层：原始文章、chunk、metadata、embedding。离线流程是：爬取文章 → 清洗 → 切块（每个 chunk 带 document_id / chunk_id / chunk_index 和 metadata）→ embedding → 入库。
- 检索层：向量检索 + 关键词 / 精确匹配，做混合融合（hybrid），再按文档去重、rerank。
- 上下文层：snippet → chunk context（用 document_id + chunk_index 读取相邻 chunk）→ article → 分页全文（offset / next_offset / has_more）。
- MCP 工具层：search_fengshu_knowledge、get_chunk_context、get_article 三个工具。
- Agent 层：Agent 根据问题决定调用哪一层，最后生成回答。
- 检索服务和 MCP 工具层部署在 Cloudflare 上。

整体可以理解成 Retrieval Service + MCP Adapter + Agent 的架构，而不只是「做了个向量数据库」。

## 优化前的问题

- 工具名是自动生成的 mcp______search，模型很难从名字判断什么时候该用它。
- 一次返回的结果太大。
- 典型调用是 search → get_article → 把整篇文章塞给模型：RAG 好不容易把 2 万字过滤成 800 字，又把剩下的 1.9 万字重新拿了回来。
- schema 把 retrieval_type、fusion_method、threshold、cache 等底层参数全部暴露给 Agent，参数越多，通用 Agent 越容易乱调。

## 优化后的做法

- 面向 Agent 的命名和描述：工具改名为 search_fengshu_knowledge、get_chunk_context、get_article，tool description 里写清楚使用策略。
- 高层语义 schema：只暴露 query / top_k / mode / source_scope，底层检索策略由服务端决定。
- chunk / document 分层，渐进式上下文加载：Snippet → Chunk Context → Article → Paginated Full Article。
- 服务端硬限制：单次最多返回 6000～10000 字符（max_chars），全文必须分页读取。
- 分页与可恢复调用：offset / next_offset / has_more / total_chars，状态推进由服务端负责。

## 怎么防止模型一上来就读整篇文章

我是分层兜底的，越往下约束越硬：
1. 最弱的是 Prompt：告诉模型「不要随便读全文」。
2. 更稳的是 Tool Description：写明「普通问答优先 get_chunk_context，不要直接 get_article」，这本质上是在做 Agent policy design。
3. 再稳一点是服务端限制：单次最多返回 6000～10000 字符。
4. 最后是分页：offset → next_offset → has_more。即使 Agent 做了一个不理想的调用，也不会一下把两三万字打回来。
结论：Prompt 是软约束，接口和服务端限制才是硬约束。遇到「模型千万不要做某事」，我会先想能不能用 schema、权限、状态机、服务端限制把错误空间缩小，而不是只写一句 prompt。

## 经验一：MCP 接口是给 Agent 用的

以前做 API，字段合理、功能能调通就行。MCP 多了一层：模型要先理解这个工具什么时候该用。search_fengshu_knowledge 比 mcp______search 好，不只是名字好看，工具名本身就是路由信号。Tool description 也不是普通文档，它实际参与 Agent 的决策。schema 不能把所有底层参数一股脑暴露出去：外层只给 query / top_k / mode / source_scope 这种高层语义参数，retrieval_type / fusion_method / threshold / cache 由服务端自己决定，这是典型的抽象层设计。

## 经验二：RAG 不等于「向量搜一下然后把原文塞给模型」

我把 RAG 拆成几步：query → 找 chunk → 读 chunk 附近 → 必要时再读文章。向量检索负责回答「哪里可能相关」，而不是负责把完整上下文找回来。命中 chunk_15 之后，前后文应该通过 document_id + chunk_index 读取 chunk_14 / 15 / 16，而不是再做一次向量搜索。几个关键对象：document_id 是父文档；chunk_id 是检索单元；chunk_index 是原文顺序；embedding 负责语义召回；上下文扩展负责恢复局部语境。这套理解以后做任何知识库都能复用。

## 经验三：渐进式上下文加载（Context Engineering）

之前的逻辑是 search → get_article → 整篇塞进去。现在是 Snippet → Chunk Context → Article → Paginated Full Article：先给模型最少但够用的信息，不够再逐级展开。价值不只是省 token，还能降低噪声。上下文不是越多越好：2 万字里如果只有 1000 字和问题相关，剩下的内容反而可能降低模型的判断质量。

## 经验四：Prompt 是软约束，接口和服务端限制才是硬约束

约束逐级加硬：prompt → tool description → 服务端单次 6000～10000 字符上限 → 分页。模型约束不能只靠 Prompt，要靠系统设计兜底：用 schema、权限、状态机、服务端限制缩小模型能犯错的空间。

## 经验五：分页、状态与可恢复调用

offset / next_offset / has_more / total_chars 看起来只是几个字段，背后是通用的接口思想。模型不用自己算 6000 + 6000 = 12000，而是永远使用服务端返回的 next_offset，把状态推进权交给服务端。这样即使文本清洗、Unicode、换行规则变化，也不会因为客户端自己算位置而漏字或重复。分页 API、游标 cursor、消息队列的消费 offset、数据库分页、本地文件流式读取，本质都很像。

## 经验六：分层架构 + 代码负责确定性，AI 负责不确定性

chunk 顺序、分页、文档去重、max_chars、权限判断交给代码保证；「这几个 chunk 哪个最有价值」交给 AI / reranker；「文章观点怎么解释」交给 LLM。数据层 → 检索层 → 上下文层 → MCP 工具层 → Agent 层，形成 Retrieval Service + MCP Adapter + Agent 的架构。

## 我的总结

不要只问功能有没有实现，要看信息怎么流、模型看到什么、模型能犯什么错、哪些交给代码保证、哪些留给 AI 判断。这个项目让我从「接了一个 MCP」走到了 Agent-friendly tool design、hybrid retrieval、document / chunk 分层、progressive context loading、pagination 和 hard guardrails。
