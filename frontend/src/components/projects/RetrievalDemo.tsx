import { ChevronDown, CornerDownLeft, FileText, Search, Sparkles, UserRound } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { Markdown } from '@/components/Markdown'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import { Input } from '@/components/ui/input'
import { Item, ItemContent, ItemDescription, ItemMedia, ItemTitle } from '@/components/ui/item'
import { Kbd } from '@/components/ui/kbd'
import { Progress } from '@/components/ui/progress'
import { Skeleton } from '@/components/ui/skeleton'
import { Spinner } from '@/components/ui/spinner'
import { AuthRequiredError, retrieveChunks, streamChat, type RetrievedChunk, type RetrieveResult } from '@/lib/api'
import { cn } from '@/lib/utils'

const MAX_QUERY = 200 // demo input cap; the server also enforces config.max_query_length

type RetrieveState =
  | { kind: 'idle' }
  | { kind: 'loading'; query: string }
  | { kind: 'done'; result: RetrieveResult }
  | { kind: 'error'; message: string }

type AnswerState =
  | { kind: 'idle' }
  | { kind: 'loading'; text: string }
  | { kind: 'done'; text: string; ms: number }
  | { kind: 'error'; message: string }

type Props = { samples: string[]; model: string; ensureAuth: () => boolean; onAuthRequired: () => void }

export function RetrievalDemo({ samples, model, ensureAuth, onAuthRequired }: Props) {
  const [query, setQuery] = useState('')
  const [state, setState] = useState<RetrieveState>({ kind: 'idle' })
  const [answer, setAnswer] = useState<AnswerState>({ kind: 'idle' })
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => () => abortRef.current?.abort(), [])

  const run = async (raw: string) => {
    const text = raw.trim()
    if (!text || state.kind === 'loading') return
    if (!ensureAuth()) return
    abortRef.current?.abort()
    setQuery(text)
    setAnswer({ kind: 'idle' })
    setState({ kind: 'loading', query: text })
    try {
      setState({ kind: 'done', result: await retrieveChunks(text) })
    } catch (error) {
      if (error instanceof AuthRequiredError) onAuthRequired()
      setState({ kind: 'error', message: error instanceof Error ? error.message : '检索失败，请稍后重试' })
    }
  }

  const generate = async (text: string) => {
    if (!ensureAuth()) return
    const controller = new AbortController()
    abortRef.current = controller
    const started = performance.now()
    let full = ''
    setAnswer({ kind: 'loading', text: '' })
    try {
      await streamChat(text, model, {
        signal: controller.signal,
        onToken: (chunk) => {
          full += chunk
          setAnswer({ kind: 'loading', text: full })
        },
        onDone: () => setAnswer({ kind: 'done', text: full || '暂无回答', ms: performance.now() - started }),
      })
    } catch (error) {
      if (controller.signal.aborted) return
      if (error instanceof AuthRequiredError) onAuthRequired()
      setAnswer({ kind: 'error', message: error instanceof Error ? error.message : '生成回答失败' })
    }
  }

  const busy = state.kind === 'loading'

  return (
    <Card className="gap-0 overflow-hidden py-0 shadow-xs">
      <div className="flex flex-col gap-3 border-b bg-zinc-50/60 p-3 sm:p-4">
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            void run(query)
          }}
        >
          <div className="relative min-w-0 flex-1">
            <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-zinc-400" aria-hidden="true" />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value.slice(0, MAX_QUERY))}
              placeholder="问一个关于我的问题…"
              aria-label="检索演示问题"
              className="bg-white pr-10 pl-8"
              maxLength={MAX_QUERY}
            />
            <Kbd className="absolute top-1/2 right-2 hidden -translate-y-1/2 sm:inline-flex">
              <CornerDownLeft className="size-3" />
            </Kbd>
          </div>
          <Button type="submit" disabled={busy || !query.trim()}>
            {busy ? <Spinner /> : <Search />}
            检索
          </Button>
        </form>
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-xs text-zinc-500">试试：</span>
          {samples.map((q) => (
            <Button key={q} type="button" variant="outline" size="xs" className="bg-white font-normal" disabled={busy} onClick={() => void run(q)}>
              {q}
            </Button>
          ))}
        </div>
      </div>

      <div className="p-3 sm:p-4" aria-live="polite">
        {state.kind === 'idle' && (
          <Empty className="gap-3 p-6 md:p-8">
            <EmptyHeader>
              <EmptyMedia variant="icon">
                <Search />
              </EmptyMedia>
              <EmptyTitle className="text-sm">选一个问题，看看检索命中了什么</EmptyTitle>
              <EmptyDescription className="text-xs">
                问题会被向量化后在 Chroma 中检索 Top-4 片段，并显示与问题的余弦相似度。整个过程约 1 秒，不调用大模型。
              </EmptyDescription>
            </EmptyHeader>
          </Empty>
        )}

        {state.kind === 'loading' && (
          <div className="flex flex-col gap-2" role="status" aria-label="正在检索">
            <div className="flex items-center gap-2 text-xs text-zinc-500">
              <Spinner className="size-3.5" />
              正在向量化「{state.query}」并检索…
            </div>
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="flex gap-3 rounded-md border p-3">
                <Skeleton className="size-7 rounded-md" />
                <div className="flex flex-1 flex-col gap-2">
                  <Skeleton className="h-3 w-32" />
                  <Skeleton className="h-3 w-full" />
                  <Skeleton className="h-3 w-2/3" />
                </div>
              </div>
            ))}
          </div>
        )}

        {state.kind === 'error' && (
          <div className="rounded-md border border-dashed p-4 text-center text-sm text-zinc-600" role="alert">
            {state.message}
          </div>
        )}

        {state.kind === 'done' && (
          <div className="flex flex-col gap-3">
            <div className="flex flex-wrap items-center gap-1.5 text-xs">
              <Badge variant="default">
                Top-{state.result.chunks.length} / 共 {state.result.total_chunks} 段
              </Badge>
              <Badge variant="outline" className="font-mono font-normal tabular-nums">
                Embedding {Math.round(state.result.embed_ms)} ms
              </Badge>
              <Badge variant="outline" className="font-mono font-normal tabular-nums">
                Chroma {Math.round(state.result.search_ms)} ms
              </Badge>
              <Badge variant="outline" className="font-mono font-normal tabular-nums">
                {state.result.embedding_dims} 维
              </Badge>
              <span className="ml-auto hidden text-zinc-400 sm:inline">相似度 = 问题与片段向量的余弦相似度（原始值）</span>
            </div>
            <ol className="flex flex-col gap-2" aria-label="检索结果">
              {state.result.chunks.map((chunk) => (
                <li key={chunk.rank}>
                  <ChunkItem chunk={chunk} />
                </li>
              ))}
            </ol>
            <AnswerBlock state={answer} onGenerate={() => void generate(state.result.query)} />
          </div>
        )}
      </div>
    </Card>
  )
}

function ChunkItem({ chunk }: { chunk: RetrievedChunk }) {
  const [open, setOpen] = useState(false)
  const SourceIcon = chunk.source === 'about_me' ? UserRound : FileText
  const sim = chunk.similarity
  return (
    <Item variant="outline" size="sm" className={cn('items-start bg-white', chunk.rank === 1 && 'border-zinc-400')}>
      <ItemMedia className="size-7 rounded-md border bg-zinc-50 font-mono text-xs text-zinc-600">{chunk.rank}</ItemMedia>
      <ItemContent className="min-w-0">
        <ItemTitle className="flex-wrap text-xs">
          <span className="inline-flex items-center gap-1">
            <SourceIcon className="size-3.5 text-zinc-500" />
            {chunk.source_label}
          </span>
          {chunk.page != null && <Badge variant="secondary" className="font-normal">第 {chunk.page} 页</Badge>}
          <span className="font-normal text-zinc-400 tabular-nums">{chunk.chars} 字</span>
        </ItemTitle>
        <ItemDescription className={cn('text-xs whitespace-pre-line text-zinc-600', open ? 'line-clamp-none' : 'line-clamp-3')}>
          {chunk.content}
        </ItemDescription>
        {chunk.content.length > 120 && (
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            className="inline-flex items-center gap-0.5 self-start text-[11px] text-zinc-500 hover:text-zinc-900"
            aria-expanded={open}
          >
            {open ? '收起' : '展开全文'}
            <ChevronDown className={cn('size-3 transition-transform', open && 'rotate-180')} />
          </button>
        )}
      </ItemContent>
      {sim != null && (
        <div className="flex w-full flex-col gap-1 sm:w-28 sm:shrink-0 sm:items-end">
          <div className="flex w-full items-baseline justify-between gap-1 sm:justify-end">
            <span className="text-[11px] text-zinc-400 sm:hidden">相似度</span>
            <span className="font-mono text-sm font-semibold tabular-nums">{sim.toFixed(3)}</span>
          </div>
          <Progress value={Math.max(0, Math.min(1, sim)) * 100} aria-label={`余弦相似度 ${sim.toFixed(3)}`} className="w-full" />
        </div>
      )}
    </Item>
  )
}

function AnswerBlock({ state, onGenerate }: { state: AnswerState; onGenerate: () => void }) {
  if (state.kind === 'idle') {
    return (
      <div className="flex flex-col items-start justify-between gap-2 rounded-lg border border-dashed p-3 sm:flex-row sm:items-center">
        <p className="text-xs text-zinc-500">
          检索完成。真实对话会先结合上下文改写问题再检索，命中片段可能略有不同；生成回答约需 13–20 秒。
        </p>
        <Button type="button" size="sm" variant="secondary" onClick={onGenerate} className="shrink-0">
          <Sparkles />
          让模型回答
        </Button>
      </div>
    )
  }
  if (state.kind === 'error') {
    return (
      <div className="rounded-lg border border-dashed p-3 text-xs text-zinc-600" role="alert">
        {state.message}
      </div>
    )
  }
  return (
    <div className="rounded-lg border bg-zinc-50/60 p-3">
      <div className="mb-2 flex items-center gap-2 text-xs text-zinc-500">
        <Sparkles className="size-3.5" />
        模型回答
        {state.kind === 'loading' && (
          <span className="inline-flex items-center gap-1">
            <Spinner className="size-3" />
            {state.text ? '生成中…' : '改写查询并检索中…'}
          </span>
        )}
        {state.kind === 'done' && <span className="font-mono tabular-nums">{(state.ms / 1000).toFixed(1)} s</span>}
      </div>
      {state.text ? (
        <Markdown text={state.text} streaming={state.kind === 'loading'} className="text-sm" />
      ) : (
        <div className="flex flex-col gap-2">
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-4/5" />
        </div>
      )}
    </div>
  )
}
