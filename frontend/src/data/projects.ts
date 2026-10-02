/**
 * Projects shown in the 「我的项目」 tab. Add another entry to `projects` to list more.
 *
 * Every number here must be real (from code, config or measurements); keep the
 * `source` field honest so the hover text tells visitors where a number comes from.
 */
import {
  Activity,
  ArrowLeftRight,
  Boxes,
  Braces,
  Database,
  FileSearch,
  FileText,
  GitPullRequestArrow,
  Layers,
  LayoutTemplate,
  type LucideIcon,
  MessagesSquare,
  Quote,
  Radio,
  Scissors,
  Server,
  ServerCog,
  ShieldCheck,
  Sparkles,
  Workflow,
} from 'lucide-react'

export type ProjectStatus = { label: string; tone: 'live' | 'open-source' | 'neutral' }
export type ProjectLink = { label: string; href: string; kind: 'github' | 'live' }
export type TechItem = { name: string; group: '后端' | 'AI / 检索' | '前端' | '运维'; role: string }
export type Metric = {
  label: string
  value: string
  unit?: string
  hint: string
  source: string
  /** Shown on the project list card (keep to ~3). */
  featured?: boolean
  /** Compact label for the list card. */
  short?: string
}
export type PipelineStep = { phase: 'build' | 'query'; title: string; subtitle: string; description: string; code: string; icon: LucideIcon }
export type Feature = { title: string; description: string; icon: LucideIcon; tags?: string[]; size?: 'wide' | 'tall' | 'normal' }
/** `id` must match a key in data/diagram-sources.ts (and so in src/generated/diagrams.ts). */
export type DiagramMeta = { id: string; label: string; caption: string }
export type InfraItem = { title: string; summary: string; icon: LucideIcon; points: string[] }

export type Project = {
  slug: string
  name: string
  tagline: string
  summary: string
  period: string
  role: string
  icon: LucideIcon
  statuses: ProjectStatus[]
  links: ProjectLink[]
  stack: TechItem[]
  metrics: Metric[]
  pipeline: PipelineStep[]
  /** Architecture diagrams; Mermaid code lives in data/diagram-sources.ts (prerendered to SVG at build time). */
  diagrams?: DiagramMeta[]
  features: Feature[]
  infra: InfraItem[]
  /** Interactive retrieval demo (POST /api/retrieve). Only meaningful for this site itself. */
  demo?: { sampleQuestions: string[] }
}

export const projects: Project[] = [
  {
    slug: 'agentic-me',
    name: 'agentic-me',
    tagline: '会回答问题的智能简历：招聘方直接用中文提问，答案只来自简历与「关于我」。',
    summary:
      '基于 RAG 的个人简历问答站，也就是你正在浏览的这个网站。FastAPI + LangChain 负责检索与生成，Chroma 存向量，前端用 React + shadcn/ui 重写，回答流式输出并附带参考来源。',
    period: '2026/09 – 至今',
    role: '独立开发 · 全栈',
    icon: MessagesSquare,
    statuses: [
      { label: '已上线', tone: 'live' },
      { label: '开源', tone: 'open-source' },
    ],
    links: [
      { label: 'GitHub', href: 'https://github.com/lucianwhy/agentic-me', kind: 'github' },
      { label: '117.72.170.211', href: 'http://117.72.170.211', kind: 'live' },
    ],
    stack: [
      { name: 'Python', group: '后端', role: '后端语言' },
      { name: 'FastAPI', group: '后端', role: 'HTTP / SSE 接口、静态资源与 Jinja 管理页' },
      { name: 'LangChain', group: 'AI / 检索', role: 'history-aware retriever + stuff documents chain' },
      { name: 'Chroma', group: 'AI / 检索', role: '本地持久化向量库（collection: chatcv）' },
      { name: '火山引擎 Embedding', group: 'AI / 检索', role: 'doubao-embedding-vision 多模态接口，2048 维' },
      { name: 'OpenAI 兼容 LLM', group: 'AI / 检索', role: '默认 gpt-5.6-sol，可切换 Luna' },
      { name: 'React 19', group: '前端', role: '对话页 SPA' },
      { name: 'TypeScript', group: '前端', role: '类型安全的数据与组件' },
      { name: 'Vite', group: '前端', role: '开发热更新与构建' },
      { name: 'Tailwind CSS v4', group: '前端', role: '样式' },
      { name: 'shadcn/ui', group: '前端', role: 'Card / Tabs / Item / Accordion 等组件' },
      { name: 'Ubuntu', group: '运维', role: '京东云轻量服务器' },
      { name: 'Nginx', group: '运维', role: '反向代理' },
      { name: 'systemd', group: '运维', role: '守护 uvicorn 进程' },
    ],
    metrics: [
      { label: 'Embedding 维度', short: '向量维度', featured: true, value: '2048', hint: '每个切块一个 2048 维向量', source: '读取 Chroma 中存储的向量长度' },
      { label: '检索 Top-K', value: '4', hint: '每次取最相近的 4 段资料', source: 'config/base.yml · vectorstore.retrieval_k' },
      { label: '切块大小 / 重叠', value: '1000', unit: '/ 200 字', hint: 'RecursiveCharacterTextSplitter', source: 'config/base.yml · embedding.chunk_size / chunk_overlap' },
      { label: '向量库切块', short: '向量库切块', featured: true, value: '7', unit: '段', hint: '简历 4 段 + 关于我 3 段', source: '本地查询 Chroma collection 计数' },
      { label: '资料来源', value: '2', unit: '份', hint: '简历 PDF（2 页）+ about_me.md', source: 'data/ 目录与切块 metadata.source' },
      { label: '首字延迟', value: '7–13', unit: 's', hint: '含查询改写、检索与模型首个 token', source: '近期无头浏览器实测（本地实例）' },
      { label: '完整回答', value: '13–20', unit: 's', hint: '从发送到流式输出结束', source: '近期无头浏览器实测（本地实例）' },
      { label: '纯检索耗时', short: '检索耗时', featured: true, value: '≈1', unit: 's', hint: '1 次 Embedding 调用 + Chroma 查询', source: 'POST /api/retrieve 实测（下方演示会实时显示）' },
    ],
    pipeline: [
      {
        phase: 'build',
        title: '资料加载',
        subtitle: '简历 PDF · 关于我',
        description: 'PyPDFLoader 读取 2 页简历，TextLoader 读取 about_me.md，并标注来源 cv / about_me。',
        code: 'vectorstore_provider.py',
        icon: FileText,
      },
      {
        phase: 'build',
        title: '切块',
        subtitle: '1000 字 / 重叠 200',
        description: 'RecursiveCharacterTextSplitter 按段落与句子切分，共得到 7 段。',
        code: 'chunk_size · chunk_overlap',
        icon: Scissors,
      },
      {
        phase: 'build',
        title: '向量化',
        subtitle: '火山引擎多模态 Embedding',
        description: '调用 /embeddings/multimodal（doubao-embedding-vision），逐段生成 2048 维向量。',
        code: 'ark_embeddings.py',
        icon: Braces,
      },
      {
        phase: 'build',
        title: 'Chroma 向量库',
        subtitle: '本地持久化',
        description: '向量与原文、页码一起存入 data/vector_db，collection 名为 chatcv。',
        code: 'data/vector_db',
        icon: Database,
      },
      {
        phase: 'query',
        title: '检索 Top-4',
        subtitle: 'history-aware retriever',
        description: '先结合对话历史让 LLM 改写成检索查询，再取最相近的 4 段资料。',
        code: 'create_history_aware_retriever',
        icon: FileSearch,
      },
      {
        phase: 'query',
        title: 'LLM 流式生成',
        subtitle: 'SSE 逐 token 推送',
        description: '4 段资料填入提示词，OpenAI 兼容接口流式生成；检索/生成阶段实时推送状态。',
        code: 'POST /chat/stream',
        icon: Radio,
      },
      {
        phase: 'query',
        title: '来源引用',
        subtitle: 'done 事件附带片段',
        description: '结束事件携带检索片段（≤300 字、来源与页码），前端折叠展示「参考来源」。',
        code: '{"type":"done","sources":[…]}',
        icon: Quote,
      },
    ],
    diagrams: [
      {
        id: 'rag',
        label: 'RAG 流程',
        caption: '离线把资料切块、向量化写入 Chroma；提问时先结合对话历史改写查询，再检索 Top-4 片段交给模型流式回答。',
      },
      {
        id: 'deploy',
        label: '部署架构',
        caption: '单台京东云轻量服务器：Nginx 反代到 systemd 守护的 uvicorn；FastAPI 通过 HTTPS 调用外部 LLM 与 Embedding API，向量库在本机。',
      },
    ],
    features: [
      {
        title: 'SSE 流式输出',
        description: '答案逐 token 推送到浏览器，打字光标跟随；Nginx 侧关闭缓冲（X-Accel-Buffering: no）。',
        icon: Radio,
        tags: ['text/event-stream', 'token / done / error'],
        size: 'wide',
      },
      {
        title: '参考来源引用',
        description: '每条回答下可展开参考片段，标明「简历 PDF · 第 N 页」或「关于我」。',
        icon: Quote,
        size: 'tall',
      },
      {
        title: '实时检索状态',
        description: '后端推送 retrieving / generating 阶段事件，等待时显示进度与已找到的资料数。',
        icon: Activity,
        size: 'tall',
      },
      {
        title: '模型切换',
        description: 'Sol（质量）/ Luna（更快）随时切换，选择保存在浏览器本地。',
        icon: ArrowLeftRight,
      },
      {
        title: '一键摘要 · 岗位匹配',
        description: '生成可转发的中文专业摘要；粘贴 JD 评估匹配度。',
        icon: Sparkles,
      },
      {
        title: '管理后台热更新',
        description: '管理后台需密码登录，可在线修改模型、接口地址与推理强度，保存后立即生效，无需重启服务。',
        icon: ShieldCheck,
        tags: ['模型', '接口地址', '推理强度', '即时生效'],
        size: 'wide',
      },
      {
        title: 'React + shadcn/ui 前端',
        description: 'Vite + TypeScript + Tailwind v4，构建产物随仓库提交，服务器无需 Node。',
        icon: LayoutTemplate,
        tags: ['Vite', 'TypeScript', 'Tailwind v4', 'shadcn/ui', 'zinc'],
        size: 'wide',
      },
    ],
    infra: [
      {
        title: '京东云轻量服务器',
        summary: 'Ubuntu · 单机部署',
        icon: Server,
        points: ['应用目录本身就是 git 仓库', 'Python 虚拟环境运行 uvicorn（FastAPI）', '向量库随数据目录持久化在本机'],
      },
      {
        title: 'Nginx 反向代理',
        summary: '统一入口 → uvicorn',
        icon: Layers,
        points: ['统一入口转发页面、API 与 /assets 静态资源', '流式接口返回 X-Accel-Buffering: no，避免 SSE 被缓冲'],
      },
      {
        title: 'systemd 守护',
        summary: '开机自启 · 异常自动拉起',
        icon: ServerCog,
        points: ['uvicorn 以系统服务运行', '日志可通过 journalctl 查看'],
      },
      {
        title: 'git pull 一键部署',
        summary: '一条命令完成更新',
        icon: GitPullRequestArrow,
        points: ['部署脚本在服务器上 git pull 拉取最新代码并重启服务', '前端 frontend/dist 已提交到仓库，部署时不需要 Node 构建', '密钥只放在服务器 .env，不进仓库'],
      },
    ],
    demo: {
      sampleQuestions: ['他用过 LangGraph 吗？', '做过哪些多智能体项目？', '实习经历是什么？', '会哪些数据库？'],
    },
  },
]

export const groupIcon: Record<TechItem['group'], LucideIcon> = {
  后端: Boxes,
  'AI / 检索': Workflow,
  前端: LayoutTemplate,
  运维: Server,
}

