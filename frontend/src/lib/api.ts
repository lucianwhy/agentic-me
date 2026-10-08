/** Thin client for the existing FastAPI endpoints (same-origin; proxied by Vite in dev). */

export type Contact = {
  type: 'email' | 'phone' | 'github' | 'linkedin' | 'scholar' | string
  label: string
  value: string
  href: string
}

export type SuggestedQuestion = { label: string; question: string }

/** Empty-chat suggestions grouped into category tabs (实习 / 项目 / 技术深度 / 为什么选我). */
export type SuggestedQuestionGroup = { id: string; label: string; questions: SuggestedQuestion[] }

/** One structured resume entry (copied from the CV); `ask` is the preset 问 AI question. */
export type ResumeEntry = {
  /** Stable card id ("projects-0"); matches Source.resume_entry_ids. Optional on older backends. */
  id?: string
  title: string
  organization: string
  role: string
  dates: string
  highlights: string[]
  tags: string[]
  link: string
  link_label: string
  ask: string
}

export type ResumeSkillGroup = { name: string; items: { name: string; ask: string }[] }

export type Resume = {
  education: ResumeEntry[]
  internships: ResumeEntry[]
  projects: ResumeEntry[]
  skills: ResumeSkillGroup[]
}

export type Profile = {
  name: string
  headline: string
  avatar_url: string
  cv_url: string
  cv_download_name: string
  contacts: Contact[]
  intro_title: string
  intro: string
  disclaimer: string
  welcome: string
  input_placeholder: string
  suggested_questions: SuggestedQuestion[]
  /** Optional on older backends. */
  suggested_question_groups?: SuggestedQuestionGroup[]
  resume?: Resume
  skills: string[]
  limits: {
    max_query_length: number
    max_job_text_length: number
    min_job_text_length: number
    rate_limit_ms: number
  }
}

export type AuthStatus = {
  authenticated: boolean
  auth_enabled: boolean
  user?: { company?: string; code?: string } | null
}

export type ModelsResponse = {
  models: string[]
  default: string
  labels: Record<string, string>
  items?: { id: string; label: string }[]
}

/** Thrown when auth is enabled and the visitor has no session. */
export class AuthRequiredError extends Error {
  constructor() {
    super('需要登录')
  }
}

type ErrorPayload = { message?: unknown; detail?: unknown } | null | undefined

export function extractErrorMessage(data: ErrorPayload, fallback: string): string {
  if (!data) return fallback
  if (typeof data.message === 'string' && data.message) return data.message
  if (typeof data.detail === 'string' && data.detail) return data.detail
  const detail = data.detail as { message?: unknown } | undefined
  if (detail && typeof detail === 'object' && typeof detail.message === 'string' && detail.message) {
    return detail.message
  }
  return fallback
}

async function readJson<T>(response: Response): Promise<T> {
  return (await response.json().catch(() => ({}))) as T
}

function request(url: string, init: RequestInit = {}) {
  return fetch(url, { ...init, credentials: 'include' })
}

export async function getProfile(): Promise<Profile> {
  const response = await request('/api/profile')
  if (!response.ok) throw new Error(`加载个人信息失败（HTTP ${response.status}）`)
  return response.json()
}

export async function getAuthStatus(): Promise<AuthStatus> {
  const response = await request('/auth/status')
  return response.json()
}

export async function login(inviteCode: string): Promise<{ success: boolean; error?: string; user?: AuthStatus['user'] }> {
  try {
    const response = await request('/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ invite_code: inviteCode }),
    })
    const data = await readJson<{ detail?: string; user?: AuthStatus['user'] }>(response)
    if (response.ok) return { success: true, user: data.user }
    return { success: false, error: data.detail || '邀请码无效' }
  } catch (error) {
    console.error('Login error:', error)
    return { success: false, error: '登录失败，请重试。' }
  }
}

export async function logout(): Promise<void> {
  await request('/auth/logout', { method: 'POST' })
}

export async function getModels(): Promise<ModelsResponse | null> {
  try {
    const response = await request('/models')
    return response.ok ? response.json() : null
  } catch {
    return null
  }
}

export async function generateSummary(): Promise<{ summary_md?: string; message?: string }> {
  const response = await request('/summary', { method: 'POST' })
  const data = await readJson<ErrorPayload & { summary_md?: string; message?: string }>(response)
  if (!response.ok) throw new Error(extractErrorMessage(data, '摘要生成失败'))
  return data ?? {}
}

export async function analyzeJobMatch(text: string): Promise<{ analysis?: string }> {
  const response = await request('/job-match', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  })
  const data = await readJson<ErrorPayload & { analysis?: string }>(response)
  if (!response.ok) throw new Error(extractErrorMessage(data, '匹配分析失败'))
  return data ?? {}
}

/** One retrieved chunk as sent in the final `done` event (content is capped at 300 chars server-side). */
export type Source = {
  content?: string
  metadata?: Record<string, unknown>
  /** Sidebar cards this chunk is about (computed server-side from the full chunk). Absent on older backends. */
  resume_entry_ids?: string[]
  /** Sidebar 工具 rows (data/tools/<id>.md chunks, or chunks naming a tool). Absent on older backends. */
  tool_ids?: string[]
}

export type StreamStage = 'retrieving' | 'generating'

type StreamHandlers = {
  onToken?: (chunk: string) => void
  /** Optional progress events (`{"type":"status","stage":...}`); older backends never send them. */
  onStatus?: (stage: StreamStage, info: { source_count?: number }) => void
  onDone?: (sources: Source[]) => void
  onError?: (message: string) => void
  signal?: AbortSignal
}

/**
 * POST /chat/stream and parse the SSE wire protocol:
 *   data: {"type":"token","content":"..."} | {"type":"done",...} | {"type":"error","message":"..."}
 */
export type ChatTurn = { role: 'user' | 'assistant'; content: string }

export async function streamChat(
  query: string,
  model: string,
  { onToken, onStatus, onDone, onError, signal }: StreamHandlers = {},
  history: ChatTurn[] = [],
) {
  const response = await request('/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    // The server is stateless: each visitor's own recent turns travel with the request.
    body: JSON.stringify({ query, model, history }),
    signal,
  })
  if (response.status === 401) throw new AuthRequiredError()
  if (!response.ok) {
    const data = await readJson<ErrorPayload>(response)
    throw new Error(extractErrorMessage(data, `请求失败（HTTP ${response.status}）`))
  }
  if (!response.body) throw new Error('浏览器不支持流式读取')

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  let sawDone = false

  const handleData = (raw: string) => {
    const trimmed = raw.trim()
    if (!trimmed || trimmed === '[DONE]') return
    let evt: { type?: string; content?: unknown; message?: string; stage?: string; source_count?: number; sources?: unknown }
    try {
      evt = JSON.parse(trimmed)
    } catch {
      return // ignore malformed partial JSON
    }
    if (evt.type === 'token' && typeof evt.content === 'string') {
      onToken?.(evt.content)
    } else if (evt.type === 'status' && (evt.stage === 'retrieving' || evt.stage === 'generating')) {
      onStatus?.(evt.stage, { source_count: evt.source_count })
    } else if (evt.type === 'done') {
      sawDone = true
      onDone?.(Array.isArray(evt.sources) ? (evt.sources as Source[]) : [])
    } else if (evt.type === 'error') {
      const msg = evt.message || '生成回答失败，请稍后重试'
      onError?.(msg)
      throw new Error(msg)
    }
  }

  const handleEvent = (rawEvent: string) => {
    for (const line of rawEvent.split(/\r?\n/)) {
      if (line.startsWith('data:')) handleData(line.slice(5).trimStart())
    }
  }

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let sep: number
    while ((sep = buffer.indexOf('\n\n')) >= 0) {
      handleEvent(buffer.slice(0, sep))
      buffer = buffer.slice(sep + 2)
    }
  }
  if (buffer.trim()) handleEvent(buffer)
  if (!sawDone) onDone?.([])
}

export type RetrievedChunk = {
  rank: number
  source: string
  source_label: string
  page: number | null
  content: string
  chars: number
  /** Exact cosine similarity between the query and chunk embeddings. */
  similarity: number | null
  /** Chroma's raw distance (squared L2). */
  distance: number | null
}

export type RetrieveResult = {
  query: string
  k: number
  metric: 'cosine'
  total_chunks: number
  embedding_dims: number
  embed_ms: number
  search_ms: number
  took_ms: number
  chunks: RetrievedChunk[]
}

/** Retrieval-only demo (no LLM call): POST /api/retrieve. */
export async function retrieveChunks(query: string): Promise<RetrieveResult> {
  const response = await request('/api/retrieve', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query }),
  })
  if (response.status === 401) throw new AuthRequiredError()
  const data = await readJson<ErrorPayload & Partial<RetrieveResult>>(response)
  if (!response.ok) throw new Error(extractErrorMessage(data, `检索失败（HTTP ${response.status}）`))
  return data as RetrieveResult
}

export type McpToolDescriptor = {
  name: string
  title?: string
  description?: string
  inputSchema?: Record<string, unknown>
}

export type McpToolsResponse = {
  available: boolean
  mock: boolean
  server: string
  chunk_context_enabled: boolean
  tools: McpToolDescriptor[]
  degraded: boolean
  message?: string
  /** Set in mock mode, or whenever MCP_NOTICE is non-empty. */
  notice?: string | null
}

export type McpCallResponse = {
  tool: string
  arguments: Record<string, unknown>
  latency_ms: number
  result: unknown
  is_error: boolean
  error_text: string | null
  mock: boolean
  clamped: string[]
}

/** HTTP failure from the MCP proxy. `retryAfter` is the server's `retry_after` seconds on 429. */
export class McpCallError extends Error {
  readonly status: number
  readonly retryAfter?: number

  constructor(message: string, status: number, retryAfter?: number) {
    super(message)
    this.name = 'McpCallError'
    this.status = status
    this.retryAfter = retryAfter
  }
}

function mcpFailure(response: Response, data: ErrorPayload & { retry_after?: unknown }, fallback: string): McpCallError {
  const message = response.status === 503 ? extractErrorMessage(data, '体验暂不可用') : extractErrorMessage(data, fallback)
  const retryAfter = typeof data?.retry_after === 'number' ? data.retry_after : undefined
  return new McpCallError(message, response.status, retryAfter)
}

/** GET /api/mcp/tools. `available: false` is a normal 200, not an error. */
export async function fetchMcpTools(signal?: AbortSignal): Promise<McpToolsResponse> {
  const response = await request('/api/mcp/tools', { signal })
  if (response.status === 401) throw new AuthRequiredError()
  const data = await readJson<ErrorPayload & { retry_after?: unknown } & Partial<McpToolsResponse>>(response)
  if (!response.ok) throw mcpFailure(response, data, `加载 MCP 工具失败（HTTP ${response.status}）`)
  return data as McpToolsResponse
}

/** POST /api/mcp/call. Tool `is_error` stays a 200 and is returned, not thrown. */
export async function callMcpTool(
  tool: string,
  args: Record<string, unknown>,
  signal?: AbortSignal,
): Promise<McpCallResponse> {
  const response = await request('/api/mcp/call', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tool, arguments: args }),
    signal,
  })
  if (response.status === 401) throw new AuthRequiredError()
  const data = await readJson<ErrorPayload & { retry_after?: unknown } & Partial<McpCallResponse>>(response)
  if (!response.ok) throw mcpFailure(response, data, `调用失败（HTTP ${response.status}）`)
  return data as McpCallResponse
}
