/**
 * Mermaid sources for the 「我的项目」 / 「工具」 architecture diagrams + the shared theme.
 * Only scripts/render-diagrams.ts imports this file; the app never does.
 *
 * These are NOT rendered in the browser: `npm run diagrams` (scripts/render-diagrams.ts)
 * prerenders every diagram (wide + narrow) to static SVG in src/generated/diagrams.ts,
 * so the mermaid package never ships in dist. `npm run build` fails if that file is stale.
 *
 * Keep this file free of imports so Node can load it directly (type stripping).
 */

/** Same stack as --font-sans in index.css, plus a Linux CJK fallback. */
export const DIAGRAM_FONT =
  "'Inter Variable', ui-sans-serif, system-ui, -apple-system, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', 'Noto Sans CJK SC', 'Noto Sans SC', sans-serif"

export const mermaidConfig = {
  startOnLoad: false,
  securityLevel: 'strict',
  theme: 'base',
  look: 'classic',
  // Mermaid 12 defaults to the ELK layout; dagre is all a flowchart needs.
  layout: 'dagre',
  fontFamily: DIAGRAM_FONT,
  themeVariables: {
    fontFamily: DIAGRAM_FONT,
    fontSize: '13px',
    background: '#ffffff',
    primaryColor: '#ffffff',
    primaryTextColor: '#18181b',
    primaryBorderColor: '#d4d4d8',
    secondaryColor: '#f4f4f5',
    tertiaryColor: '#fafafa',
    lineColor: '#a1a1aa',
    textColor: '#3f3f46',
    clusterBkg: '#fafafa',
    clusterBorder: '#e4e4e7',
    titleColor: '#52525b',
    edgeLabelBackground: '#ffffff',
  },
  flowchart: {
    curve: 'basis',
    htmlLabels: true,
    useMaxWidth: true,
    nodeSpacing: 24,
    rankSpacing: 34,
    padding: 10,
    diagramPadding: 6,
    wrappingWidth: 160,
  },
} as const

/** Chunks in the local Chroma index (CV + about_me + tool write-ups); keep in sync with projects.ts. */
const CHUNK_COUNT = 20

const CLASSES = `
  classDef default fill:#ffffff,stroke:#d4d4d8,stroke-width:1px,color:#18181b
  classDef src fill:#f4f4f5,stroke:#d4d4d8,stroke-width:1px,color:#18181b
  classDef store fill:#ffffff,stroke:#71717a,stroke-width:1px,color:#18181b
  classDef accent fill:#18181b,stroke:#18181b,stroke-width:1px,color:#fafafa
  classDef plan fill:#fafafa,stroke:#a1a1aa,stroke-width:1px,stroke-dasharray:4 3,color:#71717a
  linkStyle default stroke:#a1a1aa,stroke-width:1px`

function rag(sub: 'LR' | 'TB') {
  return `flowchart TB
  subgraph build["离线建库 · 向量库为空时构建"]
    direction ${sub}
    SRC1("简历 PDF<br/>2 页"):::src
    SRC2("关于我<br/>about_me.md"):::src
    SRC3("工具介绍<br/>data/tools/*.md"):::src
    SPLIT("切块<br/>1000 / 200 · 工具按章节")
    EMB1("火山引擎多模态 Embedding<br/>2048 维")
    DB[("Chroma<br/>${CHUNK_COUNT} 段")]:::store
    SRC1 --> SPLIT
    SRC2 --> SPLIT
    SRC3 --> SPLIT
    SPLIT --> EMB1 -->|写入| DB
  end
  subgraph query["在线问答 · 每次提问"]
    direction ${sub}
    Q("访客提问<br/>原问题直接检索"):::src
    HIST("最近 6 条消息（约 3 轮）<br/>浏览器随请求带上"):::src
    EMB2("Embedding<br/>查询向量")
    TOPK("Chroma 检索<br/>Top-4 · 编号 [1]–[4]")
    LLM("LLM 流式生成<br/>模型列表由后台管理"):::accent
    UI("前端<br/>句内引用 [n] + 参考来源"):::src
    Q --> EMB2 --> TOPK --> LLM -->|SSE| UI
    HIST --> LLM
  end
  build -.->|检索向量库| query${CLASSES}`
}

/**
 * FastAPI calls both external APIs over HTTPS (one edge from the FastAPI node to the 外部 API
 * cluster keeps the routing clean); Chroma and the admin-managed model list are local.
 */
function deploy(direction: 'LR' | 'TD') {
  return `flowchart ${direction}
  U("浏览器<br/>wanghaoyue.me"):::src
  subgraph ext["外部 API"]
    direction ${direction === 'LR' ? 'TB' : 'LR'}
    LLMAPI("LLM · nuoapi<br/>OpenAI 兼容"):::src
    ARK("火山引擎 Ark<br/>多模态 Embedding"):::src
  end
  subgraph server["阿里云 ECS"]
    NG("Nginx<br/>HTTPS · Let's Encrypt")
    API("uvicorn · FastAPI<br/>systemd 守护"):::accent
    VDB[("Chroma<br/>本地持久化")]:::store
    MODELS[("模型列表<br/>models.json · 后台管理")]:::store
  end
  U -->|HTTPS| NG --> API
  API -->|HTTPS| ext
  API -->|本地| VDB
  API -->|本地| MODELS${CLASSES}`
}

/**
 * RAG 知识库 MCP. Wide follows the call structure: 用户问题 → ChatGPT / Agent → MCP Tool Router,
 * which branches to search_knowledge → Retrieval Layer, get_chunk_context → Context Layer (设计中,
 * dashed) and get_article → Document Layer; all three read Knowledge Storage, which the offline
 * pipeline fills. Narrow stacks the three tool lanes in the order an Agent escalates through them
 * (search → neighbours → full article) so it fits a phone without shrinking the text.
 *
 * Cross-layer edges connect whole subgraphs so each layer keeps its own direction (a node-level
 * edge across a subgraph makes dagre ignore `direction`). The offline pipeline is attached with
 * a reversed edge (storage <-.- offline) so dagre ranks it last, under the storage layer.
 * The deployment boundary stays generic ("Cloudflare 部署"); storage products are unconfirmed.
 */
function ragMcp(wide: boolean) {
  const row = wide ? 'LR' : 'TB'
  const offline = `
  subgraph offline["离线建库"]
    direction ${row}
    CRAWL("爬取博主文章"):::src
    CLEAN("清洗")
    CHUNK("切块")
    EMB("Embedding")
    SAVE("写入存储")
    CRAWL --> CLEAN --> CHUNK --> EMB --> SAVE
  end`
  const storage = `
  subgraph store["Knowledge Storage"]
    direction LR
    D[("Document")]:::store
    C[("Chunks")]:::store
    V[("Vector")]:::store
    M[("Metadata<br/>title · date")]:::store
    D --> C --> V
  end`
  if (wide) {
    return `flowchart TB
  subgraph caller["调用方"]
    direction LR
    Q("用户问题"):::src
    AG("ChatGPT / Agent"):::src
    Q --> AG
  end
  subgraph cf["Cloudflare 部署"]
    direction TB
    ROUTER("MCP Tool Router"):::accent
    T1("search_knowledge"):::accent
    T2("get_chunk_context<br/>设计中"):::plan
    T3("get_article"):::accent
    ROUTER --> T1
    ROUTER -.-> T2
    ROUTER --> T3
    subgraph ret["Retrieval Layer"]
      direction LR
      VS("Vector Search")
      KS("Keyword Search")
      EX("Exact Phrase Search")
      FUSE("Hybrid / Fusion / Dedup")
      CH("Chunk<br/>document_id · chunk_id<br/>chunk_index")
      VS --> FUSE
      KS --> FUSE
      EX --> FUSE
      FUSE --> CH
    end
    subgraph ctx["Context Layer · 设计中"]
      direction LR
      NB("相邻 chunk<br/>document_id + chunk_index"):::plan
    end
    subgraph doc["Document Layer"]
      direction LR
      PG("全文分页<br/>offset → next_offset")
    end
    T1 --> ret
    T2 -.-> ctx
    T3 --> doc
  end${storage}${offline}
  caller -->|MCP 调用| ROUTER
  ret --> store
  ctx -.-> store
  doc --> store
  store <-.-|写入| offline${CLASSES}`
  }
  return `flowchart TB
  Q("用户问题"):::src
  AG("ChatGPT / Agent"):::src
  Q --> AG
  subgraph cf["Cloudflare 部署"]
    direction TB
    ROUTER("MCP Tool Router"):::accent
    subgraph l1["search_knowledge → Retrieval Layer"]
      direction TB
      SRCH("Vector / Keyword /<br/>Exact Phrase Search")
      FUSE("Hybrid / Fusion / Dedup")
      CH("Chunk<br/>document_id · chunk_id<br/>chunk_index")
      SRCH --> FUSE --> CH
    end
    subgraph l2["get_chunk_context → Context Layer"]
      direction TB
      NB("相邻 chunk<br/>document_id + chunk_index<br/>设计中"):::plan
    end
    subgraph l3["get_article → Document Layer"]
      direction TB
      PG("全文分页<br/>offset → next_offset")
    end
    ROUTER --> l1
    l1 -.->|不够再展开| l2
    l2 -.->|仍不够| l3
  end${storage}${offline}
  AG -->|MCP 调用| ROUTER
  l3 -->|三层都读取| store
  store <-.-|写入| offline${CLASSES}`
}

/**
 * Keyed by the diagram ids used in projects.ts / tools.ts. `wide` is shown when the diagram's
 * container is ≥ 640px (a CSS container query), `narrow` below that.
 */
export const diagramSources: Record<string, { wide: string; narrow: string }> = {
  rag: { wide: rag('LR'), narrow: rag('TB') },
  deploy: { wide: deploy('LR'), narrow: deploy('TD') },
  'rag-knowledge-mcp': { wide: ragMcp(true), narrow: ragMcp(false) },
}
