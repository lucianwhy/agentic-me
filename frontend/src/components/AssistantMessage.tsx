import { useEffect, useRef, useState } from 'react'
import { Check, ChevronRight, Copy, FileText } from 'lucide-react'

import { Markdown } from '@/components/Markdown'
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Skeleton } from '@/components/ui/skeleton'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import type { Source } from '@/lib/api'
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

function sourceName(s: Source) {
  const m = s.metadata ?? {}
  const src = String(m.source ?? '')
  if (src === 'cv') {
    const page = m.page_label ?? (typeof m.page === 'number' ? m.page + 1 : undefined)
    return page ? `简历 PDF · 第 ${page} 页` : '简历 PDF'
  }
  if (src === 'about_me') return '关于我'
  return src || '资料'
}

/** Plain-text preview: drop markdown markers so "## 项目 ###" reads cleanly. */
const snippet = (text: string) =>
  text
    .replace(/[#*`>|]+/g, ' ')
    .replace(/^\s*-\s+/gm, '')
    .replace(/\s+/g, ' ')
    .trim()

function Sources({ sources }: { sources: Source[] }) {
  const [open, setOpen] = useState(false)
  return (
    <Collapsible open={open} onOpenChange={setOpen} className="min-w-0 flex-1 text-xs">
      <CollapsibleTrigger asChild>
        <Button type="button" variant="ghost" size="xs" className="text-zinc-500 hover:text-zinc-900" data-sources-toggle>
          <ChevronRight className={cn('transition-transform', open && 'rotate-90')} />
          参考来源（{sources.length}）
        </Button>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <ol className="mt-1.5 space-y-1.5" data-sources-list>
          {sources.map((s, i) => (
            <li key={i} className="rounded-lg border border-zinc-200 bg-white px-3 py-2">
              <div className="flex items-center gap-1.5 font-medium text-zinc-700">
                <FileText className="size-3.5 text-zinc-400" aria-hidden="true" />
                {sourceName(s)}
              </div>
              {s.content && (
                <p className="mt-1 line-clamp-2 leading-relaxed text-zinc-500">{snippet(s.content)}</p>
              )}
            </li>
          ))}
        </ol>
      </CollapsibleContent>
    </Collapsible>
  )
}

export function AssistantMessage({ msg, avatarUrl, name }: { msg: AssistantMsg; avatarUrl: string; name: string }) {
  const waiting = msg.phase === 'retrieving' || msg.phase === 'generating'
  const elapsed = useElapsed(waiting, msg.startedAt)
  const finished = msg.phase === 'done' && !!msg.text

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
            <Markdown text={msg.text} streaming={msg.phase === 'streaming'} />
          )}
        </div>
        {finished && (
          <div className="mt-1 flex flex-wrap items-start gap-1">
            <CopyButton text={msg.text} />
            {msg.sources && msg.sources.length > 0 && <Sources sources={msg.sources} />}
          </div>
        )}
      </div>
    </div>
  )
}
