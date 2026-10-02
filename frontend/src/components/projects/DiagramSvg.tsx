import { useEffect, useState } from 'react'

import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

type Svgs = { wide: string; narrow: string }

// The prerendered SVGs (~110 kB) live in their own chunk, loaded on first use.
let svgModule: Promise<typeof import('@/generated/diagrams')> | null = null
const loadSvgs = () => (svgModule ??= import('@/generated/diagrams'))

/**
 * Static architecture diagram: SVGs are prerendered from data/diagram-sources.ts at build
 * time (scripts/render-diagrams.ts), so no Mermaid runtime is shipped.
 *
 * Both variants are inlined; a CSS container query shows `wide` when this container is
 * ≥ 640px and `narrow` below it, so tab switches and resizes need no re-render.
 */
export function DiagramSvg({ id, label, className }: { id: string; label: string; className?: string }) {
  const [svgs, setSvgs] = useState<Svgs | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    let cancelled = false
    loadSvgs()
      .then((m) => {
        if (cancelled) return
        const found = m.diagramSvgs[id]
        if (found) setSvgs(found)
        else setError(true)
      })
      .catch((e: unknown) => {
        console.warn('Diagram load failed', e)
        if (!cancelled) setError(true)
      })
    return () => {
      cancelled = true
    }
  }, [id])

  return (
    <div className={cn('mermaid-diagram @container w-full', className)} role="img" aria-label={label}>
      {error ? (
        <p className="py-8 text-center text-xs text-zinc-500">流程图加载失败，可展开下方「各步骤详情」查看。</p>
      ) : svgs ? (
        <>
          <div data-variant="narrow" className="flex justify-center @min-[640px]:hidden" dangerouslySetInnerHTML={{ __html: svgs.narrow }} />
          <div data-variant="wide" className="hidden justify-center @min-[640px]:flex" dangerouslySetInnerHTML={{ __html: svgs.wide }} />
        </>
      ) : (
        <div className="flex flex-col gap-3 py-4" aria-label="流程图加载中" role="status">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-5/6" />
        </div>
      )}
    </div>
  )
}
