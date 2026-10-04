import { use, type KeyboardEvent, type ReactNode } from 'react'
import { FileText } from 'lucide-react'

import { HoverCard, HoverCardContent, HoverCardTrigger } from '@/components/ui/hover-card'
import { CitationContext } from '@/lib/citation-context'
import { snippet, sourceName } from '@/lib/citations'
import { cn } from '@/lib/utils'

const nums = (raw: unknown) =>
  String(raw ?? '')
    .split(',')
    .map(Number)
    .filter((n) => Number.isInteger(n) && n > 0)

const onEnterOrSpace = (fn: () => void) => (e: KeyboardEvent) => {
  if (e.key === 'Enter' || e.key === ' ') {
    e.preventDefault()
    fn()
  }
}

/** A cited sentence: dashed underline once sources are in; clicking jumps to its source(s). */
export function CiteSentence({ cite, children }: { cite: unknown; children: ReactNode }) {
  const ctx = use(CitationContext)
  const list = nums(cite)
  if (!ctx?.ready || !list.length) return <span data-cite-pending>{children}</span>
  const go = (el: HTMLElement) => ctx.activate(list, el.textContent ?? '')
  return (
    <span
      role="button"
      tabIndex={0}
      data-cite={list.join(',')}
      className="cite-sentence"
      title="查看引用来源"
      onClick={(e) => go(e.currentTarget)}
      onKeyDown={(e) => onEnterOrSpace(() => go(e.currentTarget as HTMLElement))(e)}
    >
      {children}
    </span>
  )
}

/** Superscript [n]: pending (grey) while streaming, then a button with a hover card preview. */
export function CiteMarker({ refNum, sentence }: { refNum: unknown; sentence: unknown }) {
  const ctx = use(CitationContext)
  const n = Number(refNum)
  const source = ctx?.sources[n - 1]
  if (!ctx?.ready || !source) {
    return <sup className="cite-marker cite-pending" aria-hidden="true">[{n}]</sup>
  }
  return (
    <sup className="cite-marker">
      <HoverCard openDelay={120} closeDelay={80}>
        <HoverCardTrigger asChild>
          <button
            type="button"
            data-cite-ref={n}
            aria-label={`来源 ${n}：${sourceName(source)}`}
            onClick={() => ctx.activate([n], String(sentence ?? ''))}
          >
            [{n}]
          </button>
        </HoverCardTrigger>
        <HoverCardContent side="top" align="start" className="w-80 p-3 text-xs" data-cite-card>
          <div className="flex items-center gap-1.5 font-medium text-zinc-800">
            <span className="rounded bg-zinc-900 px-1 text-[10px] leading-4 font-semibold text-zinc-50 tabular-nums">{n}</span>
            <FileText className="size-3.5 text-zinc-400" aria-hidden="true" />
            {sourceName(source)}
          </div>
          <p className={cn('mt-1.5 line-clamp-6 leading-relaxed text-zinc-600')}>{snippet(source.content ?? '') || '（无预览）'}</p>
          <p className="mt-2 text-[11px] text-zinc-400">点击定位到参考来源</p>
        </HoverCardContent>
      </HoverCard>
    </sup>
  )
}
