import { Maximize2 } from 'lucide-react'
import { useEffect, useState } from 'react'

import { DiagramZoomDialog } from '@/components/projects/DiagramZoom'

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
 *
 * Clicking (or Enter / Space) opens the wide variant in a zoomable dialog.
 */
export function DiagramSvg({ id, label, className }: { id: string; label: string; className?: string }) {
  const [svgs, setSvgs] = useState<Svgs | null>(null)
  const [error, setError] = useState(false)
  const [zoomOpen, setZoomOpen] = useState(false)

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

  const zoomable = !!svgs && !error
  const open = () => zoomable && setZoomOpen(true)
  return (
    <>
      <div
        className={cn('mermaid-diagram group/diagram @container relative w-full', zoomable && 'cursor-zoom-in', className)}
        role={zoomable ? 'button' : 'img'}
        tabIndex={zoomable ? 0 : undefined}
        aria-label={zoomable ? `${label}（点击放大）` : label}
        onClick={open}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            open()
          }
        }}
        data-diagram-id={id}
      >
        {error ? (
          <p className="py-8 text-center text-xs text-zinc-500">流程图加载失败，可展开下方「各步骤详情」查看。</p>
        ) : svgs ? (
          <>
            <span
              className="pointer-events-none absolute top-0 right-0 z-10 flex items-center gap-1 rounded-md border bg-white/90 px-1.5 py-0.5 text-[11px] text-zinc-500 shadow-xs transition-colors group-hover/diagram:border-zinc-300 group-hover/diagram:text-zinc-900 group-focus-visible/diagram:text-zinc-900"
              aria-hidden="true"
              data-zoom-hint
            >
              <Maximize2 className="size-3" />
              点击放大
            </span>
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
      {svgs && (
        <DiagramZoomDialog
          open={zoomOpen}
          onOpenChange={setZoomOpen}
          title={label}
          // Own id prefix: the inline copy may be display:none, and its <style>/<marker> ids would clash.
          svg={svgs.wide.replaceAll(`dg-${id}-wide`, `dg-${id}-zoom`)}
        />
      )}
    </>
  )
}
