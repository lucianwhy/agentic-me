/**
 * Tools shown in the 「工具」 tab and the sidebar quick-nav. Every tool uses the same page
 * template, so adding one (DTS 自动化、闲鱼自动化、公众号 MCP …) only means adding an entry here:
 *
 *   1. 解决什么问题  problem          6. 遇到的问题 → 原因 → 优化 → 学到什么  problems
 *   2. 架构图        diagram          7. 我学到了什么                          learned + takeaway
 *   3. 在线体验      playground       8. 1 分钟讲清楚                          pitch
 *      （可选；紧接架构图，缺省则跳过并重编号）
 *   4. 核心能力      capabilities     9. GitHub / Demo（只在有链接时显示）       links
 *   5. 简历亮点      resumeBullets
 *      （可选；缺省则跳过并重编号）
 *
 * `id` must match data/tools/<id>.md on the backend: that file is the knowledge-base copy of the
 * same write-up, and chat sources retrieved from it carry `tool_ids: [id]`, which highlights the
 * sidebar row. Honesty rules: no invented numbers or links, and anything not built yet carries
 * `status: 'designing' | 'planned'` (rendered as a visible 设计中 / 规划中 badge).
 */
import { BookOpenText, Gauge, Layers, ListOrdered, type LucideIcon, Network, Route, ShieldCheck, SlidersHorizontal } from 'lucide-react'

/** Build status of a capability / problem / architecture part. Omitted = implemented. */
export type ToolStatus = 'done' | 'designing' | 'planned'

export const STATUS_LABEL: Record<Exclude<ToolStatus, 'done'>, string> = { designing: '设计中', planned: '规划中' }

export type Keyword = { label: string; note: string }

/** One line on the 「简历亮点」 card. `status` marks unfinished work (visible badge + honest clipboard text). */
export type ResumeBullet = {
  text: string
  status?: ToolStatus
  /** Which part is not built yet (shown under the bullet, next to the badge). */
  statusNote?: string
  /** Appended in parentheses when copying, so clipboard text stays honest. */
  copyNote?: string
}

export type Capability = {
  title: string
  detail: string
  chips?: string[]
  status?: ToolStatus
  /** Which part is not built yet (shown next to the badge). */
  statusNote?: string
}

export type ToolProblem = {
  title: string
  /** 现象 / 原因 */
  cause: string
  /** 优化 */
  fix: string
  /** 学到什么 */
  learned: string
  /** One-line insight, e.g. "Retrieval Quality ≠ Agent Experience". */
  insight?: string
  icon: LucideIcon
  status?: ToolStatus
  statusNote?: string
  /** Escalating steps (soft → hard) drawn as a ladder. */
  ladder?: { label: string; note: string }[]
  /** A flow drawn as chips with arrows; items with `status` get a badge. */
  flow?: { label: string; status?: ToolStatus }[]
  /** Before / after lists (e.g. schema parameters). */
  schema?: { before: string[]; after: string[]; note?: string }
  /** Tool → role mapping (e.g. search_knowledge = 找位置). */
  roles?: { name: string; role: string; status?: ToolStatus }[]
  quote?: string
  chips?: string[]
}

/**
 * Optional 「在线体验」, rendered immediately after 架构图.
 * `contextStatus: 'designing'` disables that tool's button and shows a 设计中 badge.
 */
export type ToolPlayground = {
  kind: 'mcp'
  /** Header label, including where the server runs. */
  server: string
  /** One line under the section title. */
  intro: string
  examples: string[]
  searchTool: string
  articleTool: string
  contextTool: string
  contextStatus?: ToolStatus
}

export type Tool = {
  id: string
  name: string
  nameEn?: string
  /** Sidebar quick-nav: label, tag (MCP / RAG / 自动化 …) and a short subtitle. */
  short: string
  navTag: string
  navSubtitle: string
  icon: LucideIcon
  /** Hero: the one-liner, a positioning line and four keyword tags. */
  oneLiner: string
  positioning: string
  keywords: Keyword[]
  /** 1. 解决什么问题 */
  problem: { oneLiner: string; paragraph: string; dataSource?: string }
  /** 2. 架构图 — `id` must be a key in data/diagram-sources.ts. */
  diagram: { id: string; caption: string; legend?: string }
  /** 3. 在线体验 — optional; omitted tools skip the section and numbering shifts. */
  playground?: ToolPlayground
  /** 4. 核心能力 (rendered 01–04). */
  capabilities: Capability[]
  /** 5. 简历亮点 — optional; omitted tools skip the section and numbering shifts. */
  resumeBullets?: ResumeBullet[]
  /** 6. 遇到的问题 → 原因 → 优化 → 学到什么 */
  problems: ToolProblem[]
  /** 7. 我学到了什么 — one line per keyword, then the takeaway quote. */
  learned: { keyword: string; text: string }[]
  takeaway: string
  /** 8. 1 分钟讲清楚 (paragraphs, first person). */
  pitch: string[]
  /** 9. Shown only when set. */
  links?: { github?: string; demo?: string }
  /** Sidebar / hero 「问 AI」 prefill (never auto-sent). */
  ask: string
  /** 「可以问我」 prefill questions. */
  questions: string[]
}

export const tools: Tool[] = [
  {
    id: 'rag-knowledge-mcp',
    name: 'RAG 知识库 MCP',
    nameEn: 'RAG Knowledge MCP',
    short: 'RAG 知识库 MCP',
    navTag: 'MCP',
    navSubtitle: '博主文章 → 混合检索 → MCP 工具',
    icon: BookOpenText,
    oneLiner: '将文章知识库封装为 MCP Tool，让 ChatGPT / Agent 可以直接搜索观点、定位原文并按需获取上下文，而不是一次把整个知识库塞进模型。',
    positioning: '把个人知识库做成可被 Agent 稳定调用的 RAG 服务，并围绕检索质量、上下文成本和工具接口做了一轮工程化优化。',
    keywords: [
      { label: 'Agent-friendly Tool Design', note: '不是普通 REST API，而是考虑 LLM 怎么理解、怎么选工具' },
      { label: 'Hybrid RAG', note: '向量召回 + keyword/exact + metadata' },
      { label: 'Progressive Context Loading', note: 'snippet → chunk context → 全文' },
      { label: 'Guardrails / Token Efficiency', note: '接口职责、分页、max_chars 控制行为与上下文成本' },
    ],
    problem: {
      oneLiner: '让 Agent 能在一个文章知识库里「找到位置、读够上下文」，而不是把整个知识库或整篇文章塞进模型。',
      paragraph:
        '我把一位自媒体博主的公众号文章爬下来做成知识库：清洗、切块、embedding，在上面做向量 + 关键词 + 精确短语的混合检索，部署在 Cloudflare 上，再包装成 MCP Server，让 ChatGPT / Agent 直接调用。第一版能搜到内容，但真正当作 Agent Tool 用起来以后，问题变成了：工具接口是不是适合模型调用、每次调用要花多少上下文。',
      dataSource: '数据来源：一位自媒体博主的公众号文章',
    },
    diagram: {
      id: 'rag-knowledge-mcp',
      caption:
        '用户问题经 ChatGPT / Agent 到 MCP Tool Router，分三路：search_knowledge 走混合检索定位 chunk；get_chunk_context 按 document_id + chunk_index 取相邻 chunk（设计中）；get_article 分页读全文。三者都读同一份知识存储，由离线流程写入。',
      legend: '虚线框 = 设计中，尚未上线',
    },
    playground: {
      kind: 'mcp',
      server: 'fengshu-knowledge（Cloudflare Workers · Streamable HTTP）',
      intro: '通过本站后端调用已部署的知识库 MCP（白名单 + 服务端限幅 + 按 IP 限流），每一步请求与返回都会展示在时间线里。',
      examples: ['AI 会取代哪些工作', '普通人怎么应对 AI 冲击', '做题家', '信息不对称'],
      searchTool: 'search_fengshu_knowledge',
      articleTool: 'get_fengshu_article',
      contextTool: 'get_chunk_context',
      contextStatus: 'designing',
    },
    capabilities: [
      {
        title: '端到端 RAG → MCP 链路',
        detail: '打通 Document → Chunk → Embedding → Retrieval → MCP Tool → Agent 链路，用 document_id / chunk_id 建立父文档与片段的映射。',
        chips: ['document_id', 'chunk_id', 'chunk_index'],
      },
      {
        title: 'Agent-friendly 接口',
        detail: '把底层检索参数抽象成 semantic / exact / balanced 三种高层 mode，Agent 只需要表达意图，具体检索策略由服务端决定。',
        chips: ['semantic', 'exact', 'balanced'],
      },
      {
        title: '渐进式上下文加载',
        detail: 'Snippet → Chunk Context → Full Article：先返回片段，不够再逐级展开，避免一上来就读全文。',
        chips: ['Snippet', 'Chunk Context', 'Full Article'],
        status: 'designing',
        statusNote: 'Chunk Context（相邻 chunk 扩展）设计中；Snippet 与全文分页已上线',
      },
      {
        title: '混合检索与分页',
        detail: '向量 / 关键词 / 精确短语检索融合，做文档级去重；全文用 offset / next_offset 分页读取。',
        chips: ['Vector', 'Keyword', 'Exact Phrase', 'Dedup', 'offset / next_offset'],
      },
    ],
    resumeBullets: [
      {
        text: '设计 Document → Chunk → Embedding → Retrieval → MCP Tool → Agent 检索链路，通过 document_id / chunk_id 建立父文档与检索片段映射。',
      },
      {
        text: '优化 Agent-friendly MCP 接口，将底层复杂检索参数抽象为 semantic / exact / balanced 等高层模式，减少模型工具选择和参数错误。',
      },
      {
        text: '针对长文本 RAG 上下文膨胀问题，设计 Snippet → Chunk Context → Full Article 渐进式上下文加载机制，避免检索命中后直接注入整篇长文。',
        status: 'designing',
        statusNote: 'Chunk Context（get_chunk_context，相邻 chunk 扩展）设计中；Snippet 与全文分页已上线',
        copyNote: 'Chunk Context 部分设计中',
      },
      {
        text: '支持向量检索、关键词/精确检索、文档级去重及分页读取，并通过 offset / next_offset 控制长文章按需读取，降低无效上下文和 Token 消耗。',
      },
    ],
    problems: [
      {
        title: 'RAG 搜到了正确内容，但 Token 爆了',
        icon: Gauge,
        insight: 'Retrieval Quality ≠ Agent Experience',
        cause: '检索本身是对的，但旧版的典型调用是 search → get_article，把整篇文章塞回模型：RAG 好不容易把两万字过滤成几百字，又把剩下的全文拿了回来，结果太大。',
        fix: '把 search_knowledge 的职责收窄为「找位置」：只返回片段和定位信息（document_id / chunk_id），需要更多上下文时再由别的工具按需读取。',
        learned: '检索质量好不等于 Agent 用起来好。工具返回什么、返回多少，本身就是设计的一部分。',
      },
      {
        title: '为什么不能命中 Chunk 后直接读整篇',
        icon: Layers,
        status: 'designing',
        statusNote: 'Neighbor Chunks 这一级设计中',
        cause: '命中一个 chunk 后直接 get_article，等于跳过了中间所有层级：大部分内容和问题无关，既浪费 token，又引入噪声。',
        fix: '设计成 Snippet → Target Chunk → Neighbor Chunks → Full Article 逐级展开：先给最少但够用的信息，不够再往下读。两端已上线，中间的 Neighbor Chunks 还在设计中。',
        learned: '上下文不是越多越好，无关内容反而可能拉低模型的判断质量。这就是 Context Engineering。',
        flow: [{ label: 'Snippet' }, { label: 'Target Chunk' }, { label: 'Neighbor Chunks', status: 'designing' }, { label: 'Full Article' }],
      },
      {
        title: '为什么上下文不能再用向量搜索',
        icon: Network,
        insight: 'Retrieval vs Context Reconstruction',
        status: 'designing',
        statusNote: 'get_chunk_context 设计中',
        cause: '向量检索回答的是「哪里可能相关」，不负责把完整语境找回来；用它补上下文，拿回来的可能是别处语义相近的片段。',
        fix: '设计方案：命中 chunk_15 后，用 document_id + chunk_index 直接读取 chunk_14 / 15 / 16，按原文顺序恢复局部语境，而不是再搜一次。',
        learned: '检索（找位置）和上下文重建（恢复语境）是两件事：document_id 是父文档，chunk_id 是检索单元，chunk_index 是原文顺序。',
        chips: ['chunk_14', 'chunk_15', 'chunk_16'],
      },
      {
        title: '模型为什么总喜欢调全文接口',
        icon: Route,
        insight: 'Tool Description = Agent Routing Prompt',
        cause: '旧工具名是自动生成的 mcp______search，描述也只是普通文档。模型分不清什么时候该用哪个工具，最省事的选择就是直接读全文。',
        fix: '工具改用语义化命名，并在 description 里写清楚分工和使用顺序。',
        learned: '工具名和描述是 Agent 路由提示词的一部分：名字本身就是路由信号。',
        roles: [
          { name: 'search_knowledge', role: '找位置' },
          { name: 'get_chunk_context', role: '局部上下文', status: 'designing' },
          { name: 'get_article', role: '文章级读取' },
        ],
      },
      {
        title: '软约束 vs 硬约束',
        icon: ShieldCheck,
        cause: '只在 prompt 里写「不要随便读全文」，模型还是可能一次把两三万字拉回来。',
        fix: '约束逐级加硬：Prompt → Tool Description → 服务端单次返回上限（max_chars）→ 分页。即使 Agent 做了一个不理想的调用，也不会一次拿回整篇。',
        learned: 'Prompt 是软约束，接口和服务端限制才是硬约束。遇到「模型千万不要做某事」，先想能不能用 schema、权限、状态机、服务端限制缩小错误空间。',
        ladder: [
          { label: 'Prompt', note: '「不要随便读全文」' },
          { label: 'Tool Description', note: '写明使用顺序' },
          { label: 'max_chars', note: '服务端单次上限' },
          { label: '分页', note: 'offset → next_offset' },
        ],
      },
      {
        title: '分页要用服务端的 next_offset',
        icon: ListOrdered,
        cause: '如果让模型自己 offset += max_chars，一旦文本清洗、Unicode 或换行规则变化，就会重复或漏掉内容。',
        fix: '每次返回 next_offset / has_more，模型永远使用服务端给的 next_offset，状态推进由服务端负责。',
        learned: '把状态推进权交给服务端。分页 API、游标 cursor、消息消费 offset、数据库分页，本质都是同一个思路。',
        chips: ['offset', 'next_offset', 'has_more'],
      },
      {
        title: 'Tool Schema 抽象',
        icon: SlidersHorizontal,
        cause: '早期把底层参数都暴露给 Agent。参数越多，通用 Agent 越容易乱调。',
        fix: '外层只保留高层语义参数；balanced 具体是不是「向量 + 关键词 + RRF」由服务端决定，Agent 不需要知道。',
        learned: '这是典型的抽象层设计：Agent 表达意图，服务端负责策略。',
        schema: {
          before: ['retrieval_type', 'fusion_method', 'threshold', 'context_expansion', 'rerank', 'metadata_only', '…'],
          after: ['query', 'top_k', 'mode: semantic / exact / balanced', 'source_scope', 'date_range'],
        },
        quote: '给模型更多参数并不一定让 Agent 更强，有时候减少可选参数反而能提升稳定性。',
      },
    ],
    learned: [
      { keyword: 'Agent-friendly Tool Design', text: '工具名、描述、schema 都是给模型看的路由信号；参数越少越稳定。' },
      { keyword: 'Hybrid RAG', text: '检索负责「找位置」：向量、关键词、精确短语融合，再做文档级去重。' },
      { keyword: 'Progressive Context Loading', text: '先给最少但够用的上下文，不够再逐级展开；上下文不是越多越好。' },
      { keyword: 'Guardrails / Token Efficiency', text: 'Prompt 是软约束，max_chars、分页和服务端 next_offset 才是硬约束。' },
    ],
    takeaway: '不要只问功能有没有实现，要看信息怎么流、模型看到什么、模型能犯什么错、哪些交给代码保证、哪些留给 AI 判断。',
    pitch: [
      '最开始的版本很直接：把博主的文章爬下来，切块、embedding，做成向量知识库，再包装成 MCP，让 ChatGPT 能搜。',
      '真正作为 Agent Tool 用起来以后，我发现问题不是能不能搜到，而是接口适不适合模型调用：工具名 mcp______search 没有语义，模型分不清什么时候用哪个工具；搜到之后常常直接调全文接口，把整篇文章塞回上下文，token 一下就爆了。',
      '所以我重新拆了链路：search_knowledge 只负责找位置，get_article 用 offset / next_offset 分页读全文，再加服务端的 max_chars 上限当硬约束；中间按 document_id + chunk_index 读相邻 chunk 的 get_chunk_context 目前还在设计中。Schema 也做了简化，只暴露 query、top_k、mode 这类高层参数，具体检索策略交给服务端。',
      '这一轮让我真正理解了 Tool Routing、Context Engineering、Token 成本和硬约束设计：不只是功能能不能跑，而是这个系统适不适合被模型稳定调用。',
    ],
    ask: '你做的 RAG 知识库 MCP 解决了什么问题？优化过程中最大的收获是什么？',
    questions: [
      '你做的 RAG 知识库 MCP 怎么防止模型读整篇文章？',
      '为什么命中 chunk 后要用 document_id + chunk_index 取上下文，而不是再搜一次？',
      'RAG 知识库 MCP 的 schema 为什么只暴露 query / top_k / mode 这些参数？',
    ],
  },
]
