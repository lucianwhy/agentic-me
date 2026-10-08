---
id: rag-knowledge-mcp
title: RAG 知识库 MCP
aliases: [RAG Knowledge MCP, RAG知识库MCP, 知识库 MCP, 风叔知识库, 风叔 MCP, search_knowledge, get_chunk_context]
---
# RAG 知识库 MCP（RAG Knowledge MCP）

## 一句话介绍

RAG 知识库 MCP 是我自己做的一个工具：将文章知识库封装为 MCP Tool，让 ChatGPT / Agent 可以直接搜索观点、定位原文并按需获取上下文，而不是一次把整个知识库塞进模型。定位：把个人知识库做成可被 Agent 稳定调用的 RAG 服务，并围绕检索质量、上下文成本和工具接口做了一轮工程化优化。关键词：Agent-friendly Tool Design、Hybrid RAG、Progressive Context Loading、Guardrails / Token Efficiency。

## 解决什么问题

数据来源是一位自媒体博主（风叔）的公众号文章。我把文章爬取下来，清洗、切块、做 embedding，在上面实现向量 + 关键词 + 精确短语的混合检索，部署在 Cloudflare 上，再包装成 MCP Server 让 ChatGPT / Agent 直接调用。第一版能搜到内容，但真正当作 Agent Tool 用起来以后，问题变成了：工具接口是否适合模型调用、每次调用要花多少上下文。

## 当前实现状态（重要）

- 已实现：search_knowledge（混合检索，返回片段和 document_id / chunk_id 定位信息）、get_article（全文分页读取，offset / next_offset）、服务端单次返回上限 max_chars、semantic / exact / balanced 三种高层 mode、文档级去重。
- 设计中、尚未实现：get_chunk_context，也就是按 document_id + chunk_index 读取相邻 chunk 的上下文扩展。渐进式上下文加载里的 Chunk Context / Neighbor Chunks 这一级目前还在设计中。
- 如果有人问 get_chunk_context 实现了没有：还没有，目前处于设计中。

在线体验：站点后端充当 MCP 客户端，用普通 JSON-RPC 走 Streamable HTTP 调用已部署的知识库。公开白名单是 search_fengshu_knowledge 和 get_fengshu_article。服务端把 top_k 限在 ≤ 5、max_chars 限在 ≤ 3000、检索词限在 200 字以内，并按 IP 限流。公开体验只检索免费文章。get_chunk_context 仍在设计中，本站未开放。

## 架构

调用链路：用户问题 → ChatGPT / Agent → MCP Tool Router，分三路：
- search_knowledge → Retrieval Layer：Vector Search / Keyword Search / Exact Phrase Search → Hybrid / Fusion / Dedup → Chunk（document_id + chunk_id + chunk_index）。已实现。
- get_chunk_context → Context Layer：用 document_id + chunk_index 取相邻 chunk。设计中、尚未实现。
- get_article → Document Layer：用 offset / next_offset 分页读全文。已实现。
三者都读同一份 Knowledge Storage：Document → Chunks → Vector，加上 Metadata（title、date）。MCP 工具和检索服务部署在 Cloudflare；离线流程是 爬取文章 → 清洗 → 切块 → embedding → 写入存储。旧版工具名是自动生成的 mcp______search，现在改名为 search_knowledge。

## 核心能力

1. 打通 Document → Chunk → Embedding → Retrieval → MCP Tool → Agent 链路，用 document_id / chunk_id 建立父文档与片段的映射。
2. Agent-friendly 接口：把底层检索参数抽象成 semantic / exact / balanced 三种高层 mode。
3. 渐进式上下文加载 Snippet → Chunk Context → Full Article：Snippet 和全文分页已上线，中间的 Chunk Context（get_chunk_context）设计中、尚未实现。
4. 向量 / 关键词 / 精确短语检索融合 + 文档级去重 + offset / next_offset 分页。

## 问题一：RAG 搜到了正确内容，但 Token 爆了

原因：检索本身是对的，但旧版典型调用是 search → get_article，把整篇文章塞回模型。RAG 好不容易把两万字过滤成几百字，又把剩下的全文拿了回来。优化：把 search_knowledge 的职责收窄为「找位置」，只返回片段和定位信息，需要更多上下文时再按需读取。学到：Retrieval Quality ≠ Agent Experience，检索质量好不等于 Agent 用起来好。

## 问题二：为什么不能命中 Chunk 后直接读整篇

原因：直接 get_article 跳过了中间层级，大部分内容和问题无关，浪费 token 又引入噪声。优化方向：Snippet → Target Chunk → Neighbor Chunks → Full Article 逐级展开。目前已上线的是 Snippet（search_knowledge）和 Full Article 分页（get_article）；中间的 Neighbor Chunks 要靠 get_chunk_context，这个工具还在设计中、尚未实现。学到：上下文不是越多越好，这就是 Context Engineering。

## 问题三：为什么上下文不能再用向量搜索

原因：向量检索回答「哪里可能相关」，不负责恢复完整语境。设计方案（get_chunk_context，设计中、尚未实现）：命中 chunk_15 后，用 document_id + chunk_index 读取 chunk_14 / 15 / 16，而不是再搜一次。学到：Retrieval（找位置）和 Context Reconstruction（恢复语境）是两件事。document_id 是父文档，chunk_id 是检索单元，chunk_index 是原文顺序。

## 问题四：模型为什么总喜欢调全文接口

原因：旧工具名 mcp______search 没有语义，描述只是普通文档，模型分不清该用哪个工具。优化：语义化命名并在 tool description 里写清分工：search_knowledge = 找位置，get_chunk_context = 局部上下文（设计中、尚未实现），get_article = 文章级读取。学到：Tool Description 是 Agent 路由提示词的一部分，名字本身就是路由信号。

## 问题五：软约束 vs 硬约束（怎么防止模型读整篇文章）

只靠 prompt 写「不要随便读全文」，模型还是可能一次拉回两三万字。我的做法是逐级加硬：Prompt → Tool Description → 服务端单次返回上限 max_chars → 分页（offset → next_offset）。即使 Agent 做了一个不理想的调用，也不会一次拿回整篇。学到：Prompt 是软约束，接口和服务端限制才是硬约束；遇到「模型千万不要做某事」，先想能不能用 schema、权限、状态机、服务端限制缩小错误空间。

## 问题六：分页要用服务端的 next_offset

不要让模型自己 offset += max_chars：一旦文本清洗、Unicode 或换行规则变化，就会重复或漏字。每次返回 next_offset / has_more，模型永远使用服务端给的 next_offset，状态推进由服务端负责。这和分页 API、游标 cursor、消息消费 offset、数据库分页是同一个思路。

## 问题七：Tool Schema 抽象

优化前把底层参数都暴露给 Agent：retrieval_type、fusion_method、threshold、context_expansion、rerank、metadata_only 等。优化后只保留 query、top_k、mode（semantic / exact / balanced）、source_scope、date_range；balanced 是否等于「向量 + 关键词 + RRF」由服务端决定。我的体会：给模型更多参数并不一定让 Agent 更强，有时候减少可选参数反而能提升稳定性。

## 简历上怎么写（简历亮点）

四个关键词：Agent-friendly Tool Design — 不是普通 REST API，而是考虑 LLM 怎么理解、怎么选工具；Hybrid RAG — 向量召回 + keyword/exact + metadata；Progressive Context Loading — snippet → chunk context → 全文；Guardrails / Token Efficiency — 接口职责、分页、max_chars 控制行为与上下文成本。

1. 设计 Document → Chunk → Embedding → Retrieval → MCP Tool → Agent 检索链路，通过 document_id / chunk_id 建立父文档与检索片段映射。
2. 优化 Agent-friendly MCP 接口，将底层复杂检索参数抽象为 semantic / exact / balanced 等高层模式，减少模型工具选择和参数错误。
3. 针对长文本 RAG 上下文膨胀问题，设计 Snippet → Chunk Context → Full Article 渐进式上下文加载机制，避免检索命中后直接注入整篇长文。其中 Chunk Context（get_chunk_context，相邻 chunk 扩展）设计中、尚未实现；Snippet 与全文分页已上线。
4. 支持向量检索、关键词/精确检索、文档级去重及分页读取，并通过 offset / next_offset 控制长文章按需读取，降低无效上下文和 Token 消耗。

## 我学到了什么

- Agent-friendly Tool Design：工具名、描述、schema 都是给模型看的路由信号，参数越少越稳定。
- Hybrid RAG：检索负责「找位置」，向量、关键词、精确短语融合，再做文档级去重。
- Progressive Context Loading：先给最少但够用的上下文，不够再逐级展开。
- Guardrails / Token Efficiency：max_chars、分页和服务端 next_offset 是硬约束。
总结：不要只问功能有没有实现，要看信息怎么流、模型看到什么、模型能犯什么错、哪些交给代码保证、哪些留给 AI 判断。
