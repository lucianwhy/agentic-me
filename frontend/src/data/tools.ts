/**
 * Tools shown in the 「工具」 tab and the sidebar quick-nav. Add an entry to `tools` to list more
 * (MCP servers, IDE plugins, ...).
 *
 * `id` must match data/tools/<id>.md on the backend: that file is the knowledge-base copy of the
 * same write-up, and chat sources retrieved from it carry `tool_ids: [id]`, which highlights the
 * sidebar row. No invented numbers (article counts, latency, ...) and no links that aren't real.
 */
import {
  BookOpenText,
  Boxes,
  Braces,
  Layers,
  ListOrdered,
  type LucideIcon,
  Network,
  ShieldCheck,
} from 'lucide-react'

/** A term with a one-line definition (rendered as a hover card). */
export type Term = { term: string; definition: string }

export type Lesson = {
  title: string
  /** One-line thesis shown under the title. */
  thesis: string
  points: string[]
  icon: LucideIcon
  /** Short code-ish chips (tool names, fields). */
  chips?: string[]
  terms?: Term[]
  /** Escalating steps rendered as a ladder (soft → hard). */
  ladder?: { label: string; note: string }[]
}

export type CompareRow = { aspect: string; before: string; after: string }

export type Tool = {
  id: string
  name: string
  /** Sidebar label (keep short). */
  short: string
  subtitle: string
  /** Sidebar tag, e.g. "MCP" / "RAG". */
  navTag: string
  icon: LucideIcon
  tags: string[]
  summary: string
  /** The single most important takeaway, shown highlighted in the hero. */
  value: { from: string; to: string }
  /** Question the sidebar 「问 AI」 action prefills (never auto-sent). */
  ask: string
  diagram: { id: string; caption: string }
  layers: { name: string; detail: string }[]
  compare: CompareRow[]
  lessons: Lesson[]
  takeaway: string
  /** 「可以问我」 prefill questions. */
  questions: string[]
}

export const tools: Tool[] = [
  {
    id: 'fengshu-mcp',
    name: '风叔知识库 MCP',
    short: '风叔知识库 MCP',
    subtitle: '博主文章 → 混合检索 → MCP 工具',
    navTag: 'MCP',
    icon: BookOpenText,
    tags: ['MCP', 'Hybrid RAG', 'Cloudflare', 'Context Engineering', 'Agent 工程'],
    summary:
      '我把自媒体博主「风叔」的文章爬取下来，清洗、切块、做 embedding，存成向量知识库；在上面实现了向量 + 关键词 / 精确匹配的混合检索，部署在 Cloudflare 上，再包装成 MCP Server 给 Agent 直接调用。能跑之后又迭代了好几轮，专门优化「模型怎么稳定地调用它」。',
    value: { from: '功能能不能跑', to: '系统是否适合被模型稳定调用' },
    ask: '你做的风叔知识库 MCP 是怎么设计的？优化过程中最大的收获是什么？',
    diagram: {
      id: 'fengshu-mcp',
      caption: 'Agent 通过 MCP 调用三个工具，各自进入不同的层：search 走混合检索返回 snippet，get_chunk_context 按 document_id + chunk_index 读相邻 chunk，get_article 分页读全文。',
    },
    layers: [
      { name: '数据层', detail: '原始文章 / chunk / metadata / embedding' },
      { name: '检索层', detail: 'vector + keyword / exact → hybrid → 文档去重 / rerank' },
      { name: '上下文层', detail: 'snippet → chunk context → article 分页' },
      { name: 'MCP 工具层', detail: 'search_fengshu_knowledge · get_chunk_context · get_article' },
      { name: 'Agent 层', detail: '根据问题决定调用哪一层，再生成回答' },
    ],
    compare: [
      { aspect: '工具命名', before: '自动生成的 mcp______search，模型很难判断什么时候该用', after: 'search_fengshu_knowledge 等语义化命名，名字本身就是路由信号' },
      { aspect: '工具描述', before: '只是普通文档', after: '写进调用策略：普通问答优先 get_chunk_context，不要直接 get_article' },
      { aspect: '参数 schema', before: 'retrieval_type / fusion_method / threshold / cache 全部暴露', after: '只暴露 query / top_k / mode / source_scope，底层策略服务端决定' },
      { aspect: '上下文获取', before: 'search → get_article 整篇塞回：2 万字过滤成 800 字，又把 1.9 万字拿了回来', after: 'Snippet → Chunk Context → Article → 分页全文，逐级展开' },
      { aspect: '返回体积', before: '一次返回的结果太大', after: '服务端单次最多 6000～10000 字符（max_chars）' },
      { aspect: '读全文', before: '一次性返回整篇', after: 'offset / next_offset / has_more 分页，状态由服务端推进' },
      { aspect: '约束方式', before: '主要靠 prompt 提醒', after: 'schema + 服务端上限 + 分页组成硬约束' },
    ],
    lessons: [
      {
        title: 'MCP 接口是给 Agent 用的',
        thesis: '以前做 API 能调通就行；MCP 多了一层：模型要先理解这个工具什么时候该用。',
        icon: Braces,
        points: [
          '工具名就是路由信号：search_fengshu_knowledge 比 mcp______search 好，不只是好看。',
          'Tool description 参与 Agent 决策。写明「普通问答优先 get_chunk_context，不要直接 get_article」，本质是在做 Agent policy design。',
          'schema 只暴露 query / top_k / mode / source_scope；retrieval_type / fusion_method / threshold / cache 由服务端决定。参数越多，通用 Agent 越容易乱调，这是抽象层设计。',
        ],
        chips: ['search_fengshu_knowledge', 'query', 'top_k', 'mode', 'source_scope'],
      },
      {
        title: 'RAG ≠ 向量搜一下塞原文',
        thesis: 'query → 找 chunk → 读邻近 chunk → 必要时再读文章。',
        icon: Network,
        points: [
          '向量检索负责回答「哪里可能相关」，而不是负责把完整上下文找回来。',
          '命中 chunk_15 后，前后文用 document_id + chunk_index 读取 chunk_14 / 15 / 16，而不是再做一次向量搜索。',
          '这套对象模型以后做任何知识库都能复用。',
        ],
        terms: [
          { term: 'document_id', definition: '父文档，一篇文章一个。' },
          { term: 'chunk_id', definition: '检索单元，向量检索命中的就是它。' },
          { term: 'chunk_index', definition: '在原文里的顺序，用来取前后相邻的 chunk。' },
          { term: 'embedding', definition: '负责语义召回：找到「哪里可能相关」。' },
          { term: '上下文扩展', definition: '负责恢复局部语境：按顺序读回命中位置的前后文。' },
        ],
      },
      {
        title: '渐进式上下文加载',
        thesis: '先给模型最少但够用的信息，不够再逐级展开。这属于 Context Engineering。',
        icon: Layers,
        points: [
          '以前是 search → get_article → 整篇塞进去；现在是 Snippet → Chunk Context → Article → Paginated Full Article。',
          '价值不只是省 token，还能降低噪声。',
          '上下文不是越多越好：2 万字里只有 1000 字相关，剩下的反而可能拉低模型的判断质量。',
        ],
        chips: ['Snippet', 'Chunk Context', 'Article', 'Paginated Full Article'],
      },
      {
        title: 'Prompt 是软约束，接口和服务端限制才是硬约束',
        thesis: '遇到「模型千万不要做某事」，先想能不能从系统设计上把错误空间缩小。',
        icon: ShieldCheck,
        points: [
          '约束逐级加硬，最后即使 Agent 做了一个不理想的调用，也不会一下把两三万字打回来。',
          '优先用 schema、权限、状态机、服务端限制兜底，而不是只多写一句 prompt。',
        ],
        ladder: [
          { label: 'Prompt', note: '「不要随便读全文」' },
          { label: 'Tool description', note: '普通问答优先 chunk context' },
          { label: '服务端上限', note: '单次 6000～10000 字符' },
          { label: '分页', note: 'offset → next_offset → has_more' },
        ],
      },
      {
        title: '分页、状态与可恢复调用',
        thesis: '把状态推进权交给服务端：模型永远用服务端返回的 next_offset。',
        icon: ListOrdered,
        points: [
          '模型不用自己算 6000 + 6000 = 12000。',
          '即使文本清洗、Unicode、换行规则变了，也不会因为客户端自己算位置而漏字或重复。',
          '同一个思路到处都是：分页 API、游标 cursor、消息消费 offset、数据库分页、文件流式读取。',
        ],
        chips: ['offset', 'next_offset', 'has_more', 'total_chars'],
      },
      {
        title: '分层架构：代码负责确定性，AI 负责不确定性',
        thesis: '数据层 → 检索层 → 上下文层 → MCP 工具层 → Agent 层。',
        icon: Boxes,
        points: [
          '代码保证：chunk 顺序、分页、文档去重、max_chars、权限判断。',
          'AI / reranker 判断「这几个 chunk 哪个最有价值」；LLM 负责「文章观点怎么解释」。',
          '最终是 Retrieval Service + MCP Adapter + Agent 的架构，而不只是「做了个向量数据库」。',
        ],
        chips: ['Retrieval Service', 'MCP Adapter', 'Agent'],
      },
    ],
    takeaway: '不要只问功能有没有实现，要看信息怎么流、模型看到什么、模型能犯什么错、哪些交给代码保证、哪些留给 AI 判断。',
    questions: [
      '你的 MCP 怎么防止模型读整篇文章？',
      '为什么命中 chunk 后用 document_id + chunk_index 取上下文，而不是再搜一次？',
      'MCP 工具的 schema 为什么只暴露 query / top_k / mode / source_scope？',
    ],
  },
]
