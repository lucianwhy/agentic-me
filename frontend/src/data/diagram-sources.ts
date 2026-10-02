/**
 * Mermaid sources for the 「我的项目」 architecture diagrams + the shared theme.
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

const CLASSES = `
  classDef default fill:#ffffff,stroke:#d4d4d8,stroke-width:1px,color:#18181b
  classDef src fill:#f4f4f5,stroke:#d4d4d8,stroke-width:1px,color:#18181b
  classDef store fill:#ffffff,stroke:#71717a,stroke-width:1px,color:#18181b
  classDef accent fill:#18181b,stroke:#18181b,stroke-width:1px,color:#fafafa
  linkStyle default stroke:#a1a1aa,stroke-width:1px`

function rag(sub: 'LR' | 'TB') {
  return `flowchart TB
  subgraph build["离线建库 · 向量库为空时构建"]
    direction ${sub}
    SRC1("简历 PDF<br/>2 页"):::src
    SRC2("关于我<br/>about_me.md"):::src
    SPLIT("切块<br/>1000 / 200")
    EMB1("火山引擎多模态 Embedding<br/>2048 维")
    DB[("Chroma<br/>7 段")]:::store
    SRC1 --> SPLIT
    SRC2 --> SPLIT
    SPLIT --> EMB1 -->|写入| DB
  end
  subgraph query["在线问答 · 每次提问"]
    direction ${sub}
    Q("访客提问"):::src
    RW("历史感知改写<br/>LLM 生成检索查询")
    EMB2("Embedding<br/>查询向量")
    TOPK("Chroma 检索<br/>Top-4")
    LLM("LLM 流式生成<br/>stuff documents"):::accent
    UI("前端<br/>回答 + 参考来源"):::src
    Q --> RW --> EMB2 --> TOPK --> LLM -->|SSE| UI
  end
  build -.->|检索向量库| query${CLASSES}`
}

/**
 * FastAPI calls both external APIs over HTTPS (one edge from the FastAPI node to the 外部 API
 * cluster keeps the routing clean); Chroma is a local dependency of FastAPI.
 */
function deploy(direction: 'LR' | 'TD') {
  return `flowchart ${direction}
  U("浏览器"):::src
  subgraph ext["外部 API"]
    direction ${direction === 'LR' ? 'TB' : 'LR'}
    LLMAPI("LLM · nuoapi<br/>OpenAI 兼容"):::src
    ARK("火山引擎 Ark<br/>多模态 Embedding"):::src
  end
  subgraph server["京东云轻量服务器 · Ubuntu"]
    NG("Nginx<br/>反向代理")
    API("uvicorn · FastAPI<br/>systemd 守护"):::accent
    VDB[("Chroma<br/>本地持久化")]:::store
  end
  U -->|HTTP| NG --> API
  API -->|HTTPS| ext
  API -->|本地| VDB${CLASSES}`
}

/**
 * Keyed by the diagram ids used in projects.ts. `wide` is shown when the diagram's
 * container is ≥ 640px (a CSS container query), `narrow` below that.
 */
export const diagramSources: Record<string, { wide: string; narrow: string }> = {
  rag: { wide: rag('LR'), narrow: rag('TB') },
  deploy: { wide: deploy('LR'), narrow: deploy('TD') },
}
