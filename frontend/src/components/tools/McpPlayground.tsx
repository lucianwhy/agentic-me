import { ChevronRight, CornerDownLeft, ExternalLink, Search } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { ToolStatusBadge } from '@/components/tools/ToolStatusBadge'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import { Input } from '@/components/ui/input'
import { Kbd } from '@/components/ui/kbd'
import { Progress } from '@/components/ui/progress'
import { Skeleton } from '@/components/ui/skeleton'
import { Spinner } from '@/components/ui/spinner'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import type { ToolPlayground } from '@/data/tools'
import {
  AuthRequiredError,
  callMcpTool,
  fetchMcpTools,
  McpCallError,
  type McpCallResponse,
  type McpToolsResponse,
} from '@/lib/api'
import { cn } from '@/lib/utils'

const MAX_QUERY = 200
const ARTICLE_PAGE_CHARS = 1500

const MODES = [
  { id: 'balanced', hint: '向量 + 关键词融合（服务端决定）' },
  { id: 'semantic', hint: '纯向量语义召回' },
  { id: 'exact', hint: '精确短语命中' },
] as const

type Mode = (typeof MODES)[number]['id']
type TopK = 3 | 5

type ToolsState =
  | { kind: 'loading' }
  | { kind: 'ready'; data: McpToolsResponse }
  | { kind: 'error'; message: string }

type TimelineEntry = {
  id: number
  step: number
  tool: string
  phase: 'running' | 'done' | 'error'
  call?: McpCallResponse
  message?: string
  retryAfter?: number
}

type SearchHit = {
  documentId: string
  title: string
  url: string | null
  date: string | null
  sourceType: string | null
  access: string | null
  chunkId: string | null
  chunkIndex: number | null
  snippet: string
  exactMatch: boolean
  snippetTruncated: boolean
}

type Props = {
  playground: ToolPlayground
  ensureAuth: () => boolean
  onAuthRequired: () => void
  /** False while invite-code auth is on and the visitor has no session. */
  authed: boolean
}

function isAbort(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  return value as Record<string, unknown>
}

function asString(value: unknown): string | null {
  return typeof value === 'string' && value ? value : null
}

function asNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

/** Server latency only: 6800 → 「6.8 s」, 320 → 「320 ms」. */
function formatLatency(ms: number): string {
  if (ms >= 1000) return `${(Math.round((ms / 1000) * 10) / 10).toFixed(1)} s`
  return `${Math.round(ms)} ms`
}

function formatRetry(seconds: number): string {
  const rounded = Math.round(seconds * 10) / 10
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1)
}

function shortChunkId(id: string): string {
  return id.length > 8 ? id.slice(0, 8) : id
}

function parseHits(result: unknown): { count: number | null; hits: SearchHit[] } {
  const body = asRecord(result)
  const raw = body && Array.isArray(body.results) ? body.results : []
  const hits = raw.map((item) => {
    const row = asRecord(item) ?? {}
    return {
      documentId: asString(row.document_id) ?? '',
      title: asString(row.title) ?? asString(row.raw_title) ?? '（无标题）',
      url: asString(row.url),
      date: asString(row.date),
      sourceType: asString(row.source_type),
      access: asString(row.access),
      chunkId: asString(row.chunk_id),
      chunkIndex: asNumber(row.chunk_index),
      snippet: typeof row.snippet === 'string' ? row.snippet : '',
      exactMatch: row.exact_match === true,
      snippetTruncated: row.snippet_truncated === true,
    }
  })
  return { count: body ? asNumber(body.count) : null, hits }
}

export function McpPlayground({ playground, ensureAuth, onAuthRequired, authed }: Props) {
  const [remoteTools, setRemoteTools] = useState<ToolsState>({ kind: 'loading' })
  const [trackedAuthed, setTrackedAuthed] = useState(authed)
  if (authed !== trackedAuthed) {
    setTrackedAuthed(authed)
    if (authed) setRemoteTools({ kind: 'loading' })
  }
  const toolsState: ToolsState = authed ? remoteTools : { kind: 'error', message: '需要登录' }
  const [query, setQuery] = useState('')
  const [mode, setMode] = useState<Mode>('balanced')
  const [topK, setTopK] = useState<TopK>(5)
  const [entries, setEntries] = useState<TimelineEntry[]>([])
  const [busy, setBusy] = useState(false)
  const abortRef = useRef<AbortController | null>(null)
  const busyRef = useRef(false)
  const stepRef = useRef(0)
  const idRef = useRef(0)

  useEffect(() => {
    if (!authed) return
    const controller = new AbortController()
    fetchMcpTools(controller.signal)
      .then((data) => setRemoteTools({ kind: 'ready', data }))
      .catch((error: unknown) => {
        if (controller.signal.aborted || isAbort(error)) return
        if (error instanceof AuthRequiredError) onAuthRequired()
        setRemoteTools({ kind: 'error', message: error instanceof Error ? error.message : '体验暂不可用' })
      })
    return () => controller.abort()
  }, [authed, onAuthRequired])

  useEffect(() => () => abortRef.current?.abort(), [])

  const available = toolsState.kind === 'ready' && toolsState.data.available
  const serviceDown = (toolsState.kind === 'ready' && !toolsState.data.available) || (toolsState.kind === 'error' && authed)
  const inputsDisabled = toolsState.kind === 'loading' || serviceDown || busy
  const modeHint = MODES.find((item) => item.id === mode)?.hint ?? ''

  const usedSearch = entries.some((entry) => entry.phase === 'done' && entry.tool === playground.searchTool && !entry.call?.is_error)
  const usedArticle = entries.some((entry) => entry.phase === 'done' && entry.tool === playground.articleTool && !entry.call?.is_error)
  const usedContext = entries.some((entry) => entry.phase === 'done' && entry.tool === playground.contextTool && !entry.call?.is_error)
  const contextClosed = playground.contextStatus === 'designing' || playground.contextStatus === 'planned'

  const callTool = async (tool: string, args: Record<string, unknown>) => {
    if (busyRef.current) return
    if (tool === playground.contextTool && contextClosed) return
    if (!ensureAuth()) return
    if (!available) return
    const controller = new AbortController()
    abortRef.current = controller
    busyRef.current = true
    setBusy(true)
    const id = ++idRef.current
    const step = ++stepRef.current
    setEntries((prev) => [...prev, { id, step, tool, phase: 'running' }])
    try {
      const call = await callMcpTool(tool, args, controller.signal)
      if (controller.signal.aborted) return
      setEntries((prev) => prev.map((entry) => (entry.id === id ? { ...entry, phase: 'done', call } : entry)))
    } catch (error) {
      if (controller.signal.aborted || isAbort(error)) return
      if (error instanceof AuthRequiredError) onAuthRequired()
      const message = error instanceof Error ? error.message : '调用失败'
      const retryAfter = error instanceof McpCallError ? error.retryAfter : undefined
      setEntries((prev) => prev.map((entry) => (entry.id === id ? { ...entry, phase: 'error', message, retryAfter } : entry)))
    } finally {
      if (abortRef.current === controller) {
        busyRef.current = false
        setBusy(false)
      }
    }
  }

  const search = (raw: string) => {
    const text = raw.trim()
    if (!text) return
    setQuery(text)
    void callTool(playground.searchTool, { query: text, mode, top_k: topK })
  }

  const readArticle = (documentId: string, offset: number) => {
    void callTool(playground.articleTool, { document_id: documentId, offset, max_chars: ARTICLE_PAGE_CHARS })
  }

  const clear = () => {
    const current = abortRef.current
    abortRef.current = null
    busyRef.current = false
    stepRef.current = 0
    current?.abort()
    setEntries([])
    setBusy(false)
  }

  const toolNames = toolsState.kind === 'ready' ? toolsState.data.tools.map((tool) => tool.name).filter(Boolean) : []

  return (
    <Card className="min-w-0 gap-0 overflow-hidden py-0 shadow-xs" data-mcp-playground>
      <div className="flex min-w-0 flex-col gap-3 border-b bg-zinc-50/60 p-3">
        <div className="flex min-w-0 flex-col gap-2">
          <div className="flex min-w-0 flex-wrap items-center gap-1.5">
            <span className="min-w-0 text-[13px] font-medium wrap-break-word text-zinc-900">{playground.server}</span>
            <StatusPill state={toolsState} />
          </div>
          {toolNames.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {toolNames.map((name) => (
                <span key={name} className="max-w-full truncate rounded-md bg-zinc-100 px-1.5 py-0.5 font-mono text-[11px] text-zinc-700">
                  {name}
                </span>
              ))}
            </div>
          )}
          {toolsState.kind === 'ready' && toolsState.data.degraded && (
            <p className="text-[11px] text-zinc-500">工具列表暂时来自本地回退（上游 tools/list 失败），调用仍走服务端。</p>
          )}
        </div>

        <form
          className="flex min-w-0 flex-wrap gap-2"
          onSubmit={(event) => {
            event.preventDefault()
            search(query)
          }}
        >
          <div className="relative min-w-[10rem] flex-1">
            <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-zinc-400" aria-hidden="true" />
            <Input
              value={query}
              onChange={(event) => setQuery(event.target.value.slice(0, MAX_QUERY))}
              placeholder="检索知识库，例如 AI 会取代哪些工作"
              aria-label="检索词"
              className="bg-white pr-10 pl-8 text-[13px]"
              maxLength={MAX_QUERY}
              disabled={inputsDisabled}
            />
            <Kbd className="absolute top-1/2 right-1.5 -translate-y-1/2">
              <CornerDownLeft className="size-3" />
            </Kbd>
          </div>
          <Button type="submit" size="sm" className="shrink-0" disabled={inputsDisabled || !query.trim()}>
            {busy ? <Spinner /> : <Search />}
            搜索
          </Button>
        </form>

        <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
          <p className="text-[11px] text-zinc-500">{modeHint}</p>
          <span className="font-mono text-[10px] text-zinc-400 tabular-nums">
            {query.length}/{MAX_QUERY}
          </span>
        </div>

        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <div role="radiogroup" aria-label="检索模式" className="inline-flex flex-wrap rounded-md border bg-white p-0.5">
            {MODES.map((item) => (
              <button
                key={item.id}
                type="button"
                role="radio"
                aria-checked={mode === item.id}
                disabled={inputsDisabled}
                onClick={() => setMode(item.id)}
                className={cn(
                  'rounded-[5px] px-2 py-1 font-mono text-[11px] disabled:opacity-50',
                  mode === item.id ? 'bg-zinc-900 font-medium text-white' : 'text-zinc-500 hover:text-zinc-800',
                )}
              >
                {item.id}
              </button>
            ))}
          </div>
          <div role="radiogroup" aria-label="top_k" className="inline-flex items-center gap-1">
            <span className="font-mono text-[11px] text-zinc-400">top_k</span>
            {([3, 5] as const).map((value) => (
              <button
                key={value}
                type="button"
                role="radio"
                aria-checked={topK === value}
                disabled={inputsDisabled}
                onClick={() => setTopK(value)}
                className={cn(
                  'rounded-md border px-2 py-1 font-mono text-[11px] tabular-nums disabled:opacity-50',
                  topK === value ? 'border-zinc-900 bg-zinc-900 text-white' : 'border-zinc-200 bg-white text-zinc-600',
                )}
              >
                {value}
              </button>
            ))}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-[11px] text-zinc-500">例如</span>
          {playground.examples.map((example) => (
            <Button
              key={example}
              type="button"
              variant="outline"
              size="xs"
              className="max-w-full bg-white font-normal"
              disabled={inputsDisabled}
              onClick={() => search(example)}
            >
              {example}
            </Button>
          ))}
        </div>

        <p className="text-[11px] leading-relaxed text-zinc-400">
          公开体验仅检索免费文章；参数由服务端白名单 + 限幅（top_k ≤ 5、max_chars ≤ 3000），并按 IP 限流
        </p>
      </div>

      <div className="flex min-w-0 flex-col gap-3 p-3">
        {!available && toolsState.kind !== 'loading' && (
          <Empty className="gap-3 border border-dashed p-6">
            <EmptyHeader>
              <EmptyMedia variant="icon">
                <Search />
              </EmptyMedia>
              <EmptyTitle className="text-sm">
                {toolsState.kind === 'error'
                  ? toolsState.message
                  : toolsState.kind === 'ready' && toolsState.data.message
                    ? toolsState.data.message
                    : '体验暂不可用'}
              </EmptyTitle>
              {authed && <EmptyDescription className="text-xs">检索入口已关闭，输入框停用。</EmptyDescription>}
              {!authed && <EmptyDescription className="text-xs">登录后即可调用。点「搜索」会打开登录。</EmptyDescription>}
            </EmptyHeader>
          </Empty>
        )}

        {available && (
          <>
            <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">
              <ProgressLegend
                usedSearch={usedSearch}
                usedArticle={usedArticle}
                usedContext={usedContext}
                contextClosed={contextClosed}
                contextStatus={playground.contextStatus}
              />
              <Button type="button" variant="ghost" size="xs" onClick={clear} disabled={entries.length === 0 && !busy}>
                清空
              </Button>
            </div>
            {entries.length === 0 ? (
              <p className="text-[11px] text-zinc-400">搜索后，每次调用会按顺序出现在下面。Snippet → 全文分页；相邻上下文仍是设计中。</p>
            ) : (
              <ol className="flex min-w-0 flex-col gap-2.5 border-l border-zinc-200 pl-3" aria-live="polite">
                {entries.map((entry) => (
                  <TimelineCard
                    key={entry.id}
                    entry={entry}
                    playground={playground}
                    busy={busy}
                    contextClosed={contextClosed}
                    onReadArticle={readArticle}
                  />
                ))}
              </ol>
            )}
          </>
        )}

        {toolsState.kind === 'loading' && (
          <div className="flex items-center gap-2 text-xs text-zinc-500" role="status">
            <Spinner className="size-3.5" />
            正在连接知识库 MCP…
          </div>
        )}
      </div>
    </Card>
  )
}

function StatusPill({ state }: { state: ToolsState }) {
  if (state.kind === 'loading') {
    return (
      <Badge variant="outline" className="font-normal">
        <Spinner className="size-3" />
        连接中
      </Badge>
    )
  }
  if (state.kind === 'error') {
    return (
      <Badge variant="destructive" className="max-w-full font-normal whitespace-normal">
        {state.message}
      </Badge>
    )
  }
  if (!state.data.available) {
    return (
      <Badge variant="destructive" className="font-normal">
        体验暂不可用
      </Badge>
    )
  }
  return (
    <>
      <Badge variant="secondary" className="font-normal">
        已连接 · {state.data.tools.length} 个工具
      </Badge>
      {state.data.mock && (
        <Badge variant="outline" className="font-normal">
          示例数据
        </Badge>
      )}
    </>
  )
}

function ProgressLegend({
  usedSearch,
  usedArticle,
  usedContext,
  contextClosed,
  contextStatus,
}: {
  usedSearch: boolean
  usedArticle: boolean
  usedContext: boolean
  contextClosed: boolean
  contextStatus?: ToolPlayground['contextStatus']
}) {
  return (
    <div className="flex min-w-0 flex-wrap items-center gap-1 text-[11px]" aria-label="渐进式加载">
      <LegendStep label="Snippet" note="搜索" active={usedSearch} />
      <span className="text-zinc-300" aria-hidden="true">
        →
      </span>
      {contextClosed ? (
        <span className="inline-flex items-center gap-1 rounded-full border border-amber-300 bg-amber-50 px-2 py-0.5 text-amber-800">
          Chunk Context
          <ToolStatusBadge status={contextStatus === 'planned' ? 'planned' : 'designing'} />
        </span>
      ) : (
        <LegendStep label="Chunk Context" note="相邻块" active={usedContext} />
      )}
      <span className="text-zinc-300" aria-hidden="true">
        →
      </span>
      <LegendStep label="Full Article" note="分页" active={usedArticle} />
    </div>
  )
}

function LegendStep({ label, note, active }: { label: string; note: string; active: boolean }) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full border px-2 py-0.5',
        active ? 'border-zinc-900 bg-zinc-900 text-white' : 'border-zinc-200 bg-white text-zinc-500',
      )}
    >
      {label}
      <span className={active ? 'text-zinc-300' : 'text-zinc-400'}>{note}</span>
    </span>
  )
}

function TimelineCard({
  entry,
  playground,
  busy,
  contextClosed,
  onReadArticle,
}: {
  entry: TimelineEntry
  playground: ToolPlayground
  busy: boolean
  contextClosed: boolean
  onReadArticle: (documentId: string, offset: number) => void
}) {
  const ref = useRef<HTMLLIElement>(null)
  useEffect(() => {
    ref.current?.scrollIntoView({ block: 'nearest' })
  }, [entry.phase])

  const failed = entry.phase === 'error' || entry.call?.is_error === true
  const latency = entry.call && typeof entry.call.latency_ms === 'number' ? entry.call.latency_ms : null

  return (
    <li ref={ref} className="min-w-0 rounded-lg border bg-white p-2.5" data-mcp-step={entry.step}>
      <div className="flex min-w-0 flex-wrap items-center gap-1.5">
        <span className="font-mono text-[11px] text-zinc-400 tabular-nums">{String(entry.step).padStart(2, '0')}</span>
        <span className="max-w-full truncate font-mono text-[12px] text-zinc-900">{entry.tool}</span>
        {entry.phase === 'running' && <Spinner className="size-3.5 text-zinc-500" />}
        {entry.phase !== 'running' && failed && (
          <Badge variant="destructive" className="font-normal">
            失败
          </Badge>
        )}
        {latency != null && entry.phase !== 'running' && (
          <Badge variant="outline" className="font-mono font-normal tabular-nums">
            {formatLatency(latency)}
          </Badge>
        )}
        {entry.call?.mock && (
          <Badge variant="outline" className="font-normal">
            示例数据
          </Badge>
        )}
        {(entry.call?.clamped ?? []).map((note) => (
          <Badge key={note} variant="secondary" className="max-w-full font-mono font-normal">
            <span className="truncate">{note}</span>
          </Badge>
        ))}
      </div>

      {entry.phase === 'running' && entry.tool === playground.searchTool && (
        <div className="mt-2 flex flex-col gap-2" role="status">
          <p className="text-[11px] text-zinc-500">正在调用 {playground.searchTool}（向量检索约 5–9 s）</p>
          {[0, 1, 2].map((i) => (
            <div key={i} className="flex flex-col gap-1.5 rounded-md border p-2">
              <Skeleton className="h-3 w-40" />
              <Skeleton className="h-3 w-full" />
              <Skeleton className="h-3 w-2/3" />
            </div>
          ))}
        </div>
      )}
      {entry.phase === 'running' && entry.tool !== playground.searchTool && (
        <p className="mt-2 flex items-center gap-1.5 text-[11px] text-zinc-500" role="status">
          <Spinner className="size-3" />
          正在调用 {entry.tool}
        </p>
      )}

      {entry.phase === 'error' && (
        <p className="mt-2 text-[13px] leading-relaxed text-red-700" role="alert">
          {entry.message}
          {entry.retryAfter != null && <span className="mt-0.5 block font-mono text-[11px]">retry_after: {formatRetry(entry.retryAfter)} s</span>}
        </p>
      )}

      {entry.call && (
        <div className="mt-2 flex min-w-0 flex-col gap-2">
          <JsonBlock title="请求" value={entry.call.arguments} defaultOpen />
          <JsonBlock title="原始响应" value={entry.call.result} />
          {entry.call.is_error && (
            <p className="text-[13px] text-red-700" role="alert">
              {entry.call.error_text || '工具调用失败'}
            </p>
          )}
          {!entry.call.is_error && entry.tool === playground.searchTool && (
            <SearchResult
              result={entry.call.result}
              playground={playground}
              busy={busy}
              contextClosed={contextClosed}
              onReadArticle={onReadArticle}
            />
          )}
          {!entry.call.is_error && entry.tool === playground.articleTool && (
            <ArticleResult result={entry.call.result} arguments={entry.call.arguments} busy={busy} onReadArticle={onReadArticle} />
          )}
        </div>
      )}
    </li>
  )
}

function JsonBlock({ title, value, defaultOpen = false }: { title: string; value: unknown; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <Collapsible open={open} onOpenChange={setOpen} className="min-w-0">
      <CollapsibleTrigger className="inline-flex items-center gap-1 text-[11px] text-zinc-500 hover:text-zinc-800">
        <ChevronRight className={cn('size-3 transition-transform', open && 'rotate-90')} aria-hidden="true" />
        {title}
      </CollapsibleTrigger>
      <CollapsibleContent className="mt-1 min-w-0">
        <pre className="max-h-48 max-w-full overflow-auto rounded-md border bg-zinc-50 p-2 font-mono text-[11px] leading-relaxed text-zinc-700">
          {JSON.stringify(value ?? null, null, 2)}
        </pre>
      </CollapsibleContent>
    </Collapsible>
  )
}

function SearchResult({
  result,
  playground,
  busy,
  contextClosed,
  onReadArticle,
}: {
  result: unknown
  playground: ToolPlayground
  busy: boolean
  contextClosed: boolean
  onReadArticle: (documentId: string, offset: number) => void
}) {
  const { count, hits } = parseHits(result)
  const shown = count ?? hits.length
  return (
    <div className="flex min-w-0 flex-col gap-2">
      <p className="text-[11px] text-zinc-500">{shown} 条</p>
      {hits.length === 0 ? (
        <p className="text-[13px] text-zinc-500">没有命中</p>
      ) : (
        <ol className="flex min-w-0 flex-col gap-2">
          {hits.map((hit, index) => (
            <SearchHitRow
              key={`${hit.documentId}-${hit.chunkId ?? index}`}
              hit={hit}
              rank={index + 1}
              playground={playground}
              busy={busy}
              contextClosed={contextClosed}
              onReadArticle={onReadArticle}
            />
          ))}
        </ol>
      )}
    </div>
  )
}

function SearchHitRow({
  hit,
  rank,
  playground,
  busy,
  contextClosed,
  onReadArticle,
}: {
  hit: SearchHit
  rank: number
  playground: ToolPlayground
  busy: boolean
  contextClosed: boolean
  onReadArticle: (documentId: string, offset: number) => void
}) {
  const [open, setOpen] = useState(false)
  const meta = [
    hit.documentId,
    hit.chunkIndex != null ? `chunk #${hit.chunkIndex}` : null,
    hit.chunkId ? shortChunkId(hit.chunkId) : null,
  ]
    .filter(Boolean)
    .join(' · ')
  const canRead = Boolean(hit.documentId)

  return (
    <li className="min-w-0 rounded-md border p-2">
      <div className="flex min-w-0 flex-wrap items-baseline gap-x-2 gap-y-1">
        <span className="font-mono text-[11px] text-zinc-400 tabular-nums">{rank}</span>
        {hit.url ? (
          <a
            href={hit.url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex min-w-0 items-baseline gap-1 text-[13px] font-medium wrap-break-word text-zinc-900 underline-offset-2 hover:underline"
          >
            {hit.title}
            <ExternalLink className="size-3 shrink-0 translate-y-px text-zinc-400" aria-hidden="true" />
          </a>
        ) : (
          <span className="min-w-0 text-[13px] font-medium wrap-break-word text-zinc-900">{hit.title}</span>
        )}
        {hit.date && <span className="text-[11px] text-zinc-400 tabular-nums">{hit.date}</span>}
        {hit.sourceType && (
          <Badge variant="outline" className="font-normal">
            {hit.sourceType}
          </Badge>
        )}
        {hit.access && (
          <Badge variant="secondary" className="font-normal">
            {hit.access}
          </Badge>
        )}
        {hit.exactMatch && (
          <Badge variant="outline" className="font-mono font-normal">
            exact_match
          </Badge>
        )}
      </div>
      {meta && (
        <p className="mt-1 font-mono text-[10.5px] break-all text-zinc-400" title={hit.chunkId ?? undefined}>
          {meta}
        </p>
      )}
      {hit.snippet && (
        <button type="button" className="mt-1 block w-full text-left" onClick={() => setOpen((value) => !value)} aria-expanded={open}>
          <span className={cn('text-[13px] leading-relaxed wrap-break-word text-zinc-700', !open && 'line-clamp-4')}>{hit.snippet}</span>
        </button>
      )}
      {hit.snippetTruncated && <p className="mt-0.5 text-[10.5px] text-zinc-400">片段已截断</p>}
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        <Button type="button" size="xs" variant="outline" disabled={!canRead || busy} onClick={() => canRead && onReadArticle(hit.documentId, 0)}>
          读取原文（分页）
        </Button>
        {contextClosed ? (
          <Tooltip>
            <TooltipTrigger asChild>
              <span className="inline-flex items-center gap-1" tabIndex={0}>
                <Button type="button" size="xs" variant="outline" disabled className="pointer-events-none">
                  相邻上下文
                </Button>
                <ToolStatusBadge status={playground.contextStatus === 'planned' ? 'planned' : 'designing'} />
              </span>
            </TooltipTrigger>
            <TooltipContent sideOffset={4}>
              {playground.contextTool}：{playground.contextStatus === 'planned' ? '规划中' : '设计中'}，尚未在本站开放
            </TooltipContent>
          </Tooltip>
        ) : (
          <Button type="button" size="xs" variant="outline" disabled>
            相邻上下文
          </Button>
        )}
      </div>
    </li>
  )
}

function ArticleResult({
  result,
  arguments: args,
  busy,
  onReadArticle,
}: {
  result: unknown
  arguments: Record<string, unknown>
  busy: boolean
  onReadArticle: (documentId: string, offset: number) => void
}) {
  const body = asRecord(result)
  const content = typeof body?.content === 'string' ? body.content : ''
  const offset = asNumber(body?.offset) ?? asNumber(args.offset) ?? 0
  const total = asNumber(body?.total_chars)
  const end = offset + content.length
  const hasNext = Boolean(body && 'next_offset' in body)
  const nextRaw = hasNext ? body?.next_offset : undefined
  const next = typeof nextRaw === 'number' ? nextRaw : null
  const documentId = asString(body?.document_id) ?? asString(args.document_id)
  const title = asString(body?.title)
  const percent = total != null && total > 0 ? Math.min(100, (end / total) * 100) : null
  const nextLine = !hasNext
    ? 'next_offset: （响应未提供，不能自行推算）'
    : next != null
      ? `next_offset: ${next}`
      : nextRaw === null
        ? 'next_offset: null（已到末尾）'
        : 'next_offset: （无法识别）'

  return (
    <div className="flex min-w-0 flex-col gap-2">
      {title && <p className="text-[13px] font-medium wrap-break-word text-zinc-900">{title}</p>}
      <div className="flex min-w-0 flex-col gap-1">
        <p className="font-mono text-[11px] break-all text-zinc-600 tabular-nums">
          {offset} → {end}
          {total != null ? ` / ${total}` : ''}
        </p>
        {percent != null && <Progress value={percent} className="h-1" aria-label={`已读 ${end}${total != null ? ` / ${total}` : ''}`} />}
      </div>
      <div className="max-h-72 overflow-auto rounded-md border bg-zinc-50 p-2 text-[13px] leading-relaxed wrap-break-word whitespace-pre-wrap text-zinc-800">
        {content || '（本页没有正文）'}
      </div>
      <p className="font-mono text-[11px] break-all text-zinc-500">{nextLine}</p>
      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" size="xs" variant="secondary" disabled={busy || next == null || !documentId} onClick={() => documentId != null && next != null && onReadArticle(documentId, next)}>
          下一页
        </Button>
        <span className="text-[11px] text-zinc-400">下一页始终使用服务端返回的 next_offset</span>
      </div>
    </div>
  )
}
