import { useCallback, useEffect, useMemo, useRef, useState, type Ref } from 'react'
import { ArrowUpRight, Blocks, Check, ChevronRight, Copy, FileText } from 'lucide-react'

import { Markdown } from '@/components/Markdown'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Skeleton } from '@/components/ui/skeleton'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import type { Resume, Source } from '@/lib/api'
import { CitationContext, type CitationContextValue } from '@/lib/citation-context'
import { flash, flashResumeEntry, flashToolEntry, matchResumeEntry, scrollIntoNearest, snippet, sourceName, stripCitations } from '@/lib/citations'
import { cn } from '@/lib/utils'

/** waiting → (retrieving|generating) → streaming → done | error */
export type AssistantPhase = 'retrieving' | 'generating' | 'streaming' | 'done' | 'error'

export type AssistantMsg = {
  id: number
  role: 'assistant'
  text: string
  phase: AssistantPhase
  /** Did the backend send real stage events? If not, the status line advances on a timer. */
  realStages?: boolean
  sourceCount?: number
  sources?: Source[]
  startedAt?: number
}

// Time-based fallback when the backend sends no status events (older servers).
const FALLBACK_GENERATING_AFTER_MS = 7000

function useElapsed(active: boolean, startedAt?: number) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!active) return
    const t = window.setInterval(() => setNow(Date.now()), 500)
    return () => window.clearInterval(t)
  }, [active])
  return startedAt ? Math.max(0, Math.floor((now - startedAt) / 1000)) : 0
}

function statusText(msg: AssistantMsg, elapsed: number) {
  let stage = msg.phase
  if (!msg.realStages && stage === 'retrieving' && elapsed * 1000 >= FALLBACK_GENERATING_AFTER_MS) stage = 'generating'
  if (stage === 'retrieving') return '正在检索简历…'
  if (msg.sourceCount) return `已找到 ${msg.sourceCount} 段资料，正在组织回答…`
  return '正在组织回答…'
}

/** Copy with a fallback for non-secure origins (e.g. http://<LAN-IP>:5173) where navigator.clipboard is missing. */
async function copyText(text: string) {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch {
    /* fall through */
  }
  const ta = document.createElement('textarea')
  ta.value = text
  ta.setAttribute('readonly', '')
  ta.style.position = 'fixed'
  ta.style.opacity = '0'
  document.body.appendChild(ta)
  ta.select()
  let ok = false
  try {
    ok = document.execCommand('copy')
  } catch {
    ok = false
  }
  ta.remove()
  return ok
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  const [open, setOpen] = useState(false)
  const timer = useRef<number | undefined>(undefined)
  useEffect(() => () => window.clearTimeout(timer.current), [])

  const onCopy = async () => {
    const ok = await copyText(text)
    if (!ok) return
    setCopied(true)
    setOpen(true)
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => {
      setCopied(false)
      setOpen(false)
    }, 1500)
  }

  return (
    <Tooltip open={open || undefined} onOpenChange={(o) => !copied && setOpen(o)}>
      <TooltipTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="icon-xs"
          className="text-zinc-500 hover:text-zinc-900"
          aria-label={copied ? '已复制' : '复制回答'}
          data-copy-button
          onClick={onCopy}
        >
          {copied ? <Check /> : <Copy />}
        </Button>
      </TooltipTrigger>
      <TooltipContent side="bottom">{copied ? '已复制' : '复制'}</TooltipContent>
    </Tooltip>
  )
}

type SourcesProps = {
  sources: Source[]
  open: boolean
  onOpenChange: (open: boolean) => void
  /** 1-based numbers of the chunks the visitor just jumped to (shown unclamped). */
  active: number[]
  listRef: Ref<HTMLOListElement>
  onOpenTool?: (id: string) => void
}

function Sources({ sources, open, onOpenChange, active, listRef, onOpenTool }: SourcesProps) {
  return (
    <Collapsible open={open} onOpenChange={onOpenChange} className="min-w-0 flex-1 text-xs">
      <CollapsibleTrigger asChild>
        <Button type="button" variant="ghost" size="xs" className="text-zinc-500 hover:text-zinc-900" data-sources-toggle>
          <ChevronRight className={cn('transition-transform', open && 'rotate-90')} />
          参考来源（{sources.length}）
        </Button>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <ol ref={listRef} className="mt-1.5 space-y-1.5" data-sources-list>
          {sources.map((s, i) => {
            const isActive = active.includes(i + 1)
            const toolId = s.tool_ids?.[0]
            const SourceIcon = s.metadata?.source === 'tool' ? Blocks : FileText
            return (
              <li
                key={i}
                data-source-index={i + 1}
                data-resume-ids={s.resume_entry_ids?.join(',')}
                data-tool-ids={s.tool_ids?.join(',') || undefined}
                className={cn('rounded-lg border bg-white px-3 py-2 transition-colors', isActive ? 'border-zinc-400' : 'border-zinc-200')}
              >
                <div className="flex items-center gap-1.5 font-medium text-zinc-700">
                  <span className="rounded bg-zinc-100 px-1 text-[10px] leading-4 font-semibold text-zinc-600 tabular-nums ring-1 ring-zinc-200">
                    {i + 1}
                  </span>
                  <SourceIcon className="size-3.5 text-zinc-400" aria-hidden="true" />
                  <span className="min-w-0 truncate">{sourceName(s)}</span>
                  {toolId && onOpenTool && (
                    <button
                      type="button"
                      data-open-tool={toolId}
                      onClick={() => onOpenTool(toolId)}
                      className="ml-auto inline-flex shrink-0 items-center gap-0.5 rounded px-1 text-[11px] font-normal text-zinc-500 underline-offset-2 hover:text-zinc-900 hover:underline"
                    >
                      在工具页查看
                      <ArrowUpRight className="size-3" aria-hidden="true" />
                    </button>
                  )}
                </div>
                {s.content && (
                  <p className={cn('mt-1 leading-relaxed text-zinc-500', !isActive && 'line-clamp-2')}>{snippet(s.content)}</p>
                )}
              </li>
            )
          })}
        </ol>
      </CollapsibleContent>
    </Collapsible>
  )
}

type Props = {
  msg: AssistantMsg
  avatarUrl: string
  name: string
  /** Sidebar resume entries; a cited chunk that is about one of them highlights it too. */
  resume?: Resume
  /** Open a tool's detail in the 工具 tab (「在工具页查看」 on tool sources). */
  onOpenTool?: (id: string) => void
}

export function AssistantMessage({ msg, avatarUrl, name, resume, onOpenTool }: Props) {
  const waiting = msg.phase === 'retrieving' || msg.phase === 'generating'
  const elapsed = useElapsed(waiting, msg.startedAt)
  const finished = msg.phase === 'done' && !!msg.text

  const [sourcesOpen, setSourcesOpen] = useState(false)
  const [jump, setJump] = useState<{ nums: number[]; at: number } | null>(null)
  const listRef = useRef<HTMLOListElement>(null)
  const sources = msg.sources
  // Until the done event the server has only told us how many chunks it found (status event).
  const citeCount = sources ? sources.length : (msg.sourceCount ?? null)

  const activate = useCallback(
    (nums: number[], sentence: string) => {
      if (!sources?.length) return
      setSourcesOpen(true)
      setJump({ nums, at: Date.now() })
      // Highlight the first sidebar card the cited chunks point at: a resume entry, else a 工具 row.
      for (const n of nums) {
        const src = sources[n - 1]
        const id = matchResumeEntry(resume, src?.content ?? '', sentence, src?.resume_entry_ids)
        if (id) {
          flashResumeEntry(id)
          break
        }
        const toolId = src?.tool_ids?.[0]
        if (toolId && flashToolEntry(toolId)) break
      }
    },
    [sources, resume],
  )

  // After the panel has opened, bring the first cited chunk into view and flash every cited one.
  useEffect(() => {
    if (!jump) return
    const raf = requestAnimationFrame(() => {
      const items = jump.nums
        .map((n) => listRef.current?.querySelector<HTMLElement>(`[data-source-index="${n}"]`))
        .filter((el): el is HTMLElement => !!el)
      if (items[0]) scrollIntoNearest(items[0])
      items.forEach(flash)
    })
    return () => cancelAnimationFrame(raf)
  }, [jump])

  const citeCtx = useMemo<CitationContextValue>(
    () => ({ ready: msg.phase === 'done' && !!sources?.length, sources: sources ?? [], activate }),
    [msg.phase, sources, activate],
  )

  return (
    <div className="flex max-w-[95%] items-start gap-2.5 md:max-w-[88%]" data-role="assistant" data-phase={msg.phase}>
      <Avatar className="mt-0.5 size-8">
        <AvatarImage src={avatarUrl} alt={name} />
        <AvatarFallback>{name.slice(0, 1)}</AvatarFallback>
      </Avatar>
      <div className="min-w-0 flex-1">
        <div className="mb-1 text-xs font-medium text-zinc-500">{name} 的简历助手</div>
        <div className="w-fit max-w-full rounded-2xl rounded-tl-sm bg-zinc-100 px-4 py-3 text-zinc-900" data-bubble>
          {waiting ? (
            <div className="w-72 max-w-full sm:w-80" aria-live="polite">
              <div className="flex items-center gap-2 text-sm text-zinc-500" data-status>
                <span className="inline-flex items-center gap-1" aria-hidden="true">
                  <span className="typing-dot" />
                  <span className="typing-dot" />
                  <span className="typing-dot" />
                </span>
                <span className="min-w-0 truncate">{statusText(msg, elapsed)}</span>
                <span className="ml-auto shrink-0 text-xs tabular-nums text-zinc-400">{elapsed}s</span>
              </div>
              <div className="mt-3 space-y-2" aria-hidden="true">
                <Skeleton className="h-3 w-full bg-zinc-200" />
                <Skeleton className="h-3 w-[85%] bg-zinc-200" />
                <Skeleton className="h-3 w-[60%] bg-zinc-200" />
              </div>
            </div>
          ) : msg.phase === 'error' ? (
            <p className="text-sm text-red-600">{msg.text}</p>
          ) : (
            <CitationContext value={citeCtx}>
              <Markdown text={msg.text} streaming={msg.phase === 'streaming'} citations={{ count: citeCount }} />
            </CitationContext>
          )}
        </div>
        {finished && (
          <div className="mt-1 flex flex-wrap items-start gap-1">
            <CopyButton text={stripCitations(msg.text)} />
            {sources && sources.length > 0 && (
              <Sources sources={sources} open={sourcesOpen} onOpenChange={setSourcesOpen} active={jump?.nums ?? []} listRef={listRef} onOpenTool={onOpenTool} />
            )}
          </div>
        )}
      </div>
    </div>
  )
}
