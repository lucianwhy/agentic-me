import { Maximize, Minus, Move, Plus } from 'lucide-react'
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'

const MIN_SCALE = 0.2
const MAX_SCALE = 6
const STEP = 1.25

type View = { x: number; y: number; s: number }
type Props = { open: boolean; onOpenChange: (open: boolean) => void; svg: string; title: string }

/**
 * Near-fullscreen (desktop) / fullscreen (mobile) viewer for a prerendered diagram.
 * Zoom: buttons, keyboard (+ / - / 0), wheel / trackpad pinch, two-finger pinch,
 * double-click; pan: drag. Plain CSS transforms, no extra dependency. Esc closes (Radix).
 */
export function DiagramZoomDialog({ open, onOpenChange, svg, title }: Props) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="flex h-[100dvh] max-h-none w-screen max-w-none flex-col gap-0 overflow-hidden rounded-none p-0 sm:h-[calc(100dvh-3rem)] sm:w-[calc(100vw-3rem)] sm:max-w-none sm:rounded-xl"
        data-diagram-zoom
      >
        <div className="flex items-center gap-2 border-b px-4 py-2.5 pr-14">
          <DialogTitle className="truncate text-sm font-medium">{title}</DialogTitle>
          <DialogDescription className="hidden text-xs text-zinc-400 sm:block">滚轮 / 双指缩放 · 拖动平移 · Esc 关闭</DialogDescription>
        </div>
        {open && <ZoomViewer svg={svg} />}
      </DialogContent>
    </Dialog>
  )
}

function ZoomViewer({ svg }: { svg: string }) {
  const viewportRef = useRef<HTMLDivElement>(null)
  const contentRef = useRef<HTMLDivElement>(null)
  const sizeRef = useRef({ w: 1, h: 1 })
  const [view, setView] = useState<View>({ x: 0, y: 0, s: 1 })
  const [dragging, setDragging] = useState(false)

  const fit = useCallback(() => {
    const vp = viewportRef.current
    if (!vp) return
    const { w, h } = sizeRef.current
    const pad = 24
    const toolbar = 64 // keep the bottom zoom controls clear of the fitted diagram
    const availH = vp.clientHeight - pad - toolbar
    const s = Math.min((vp.clientWidth - pad * 2) / w, availH / h, 2)
    setView({ s, x: (vp.clientWidth - w * s) / 2, y: pad / 2 + (availH - h * s) / 2 + pad / 2 })
  }, [])

  // Give the SVG its intrinsic (viewBox) size so the transform alone controls scale.
  useLayoutEffect(() => {
    const el = contentRef.current?.querySelector('svg')
    if (!el) return
    const vb = el.viewBox.baseVal
    const w = vb && vb.width ? vb.width : el.getBoundingClientRect().width || 800
    const h = vb && vb.height ? vb.height : el.getBoundingClientRect().height || 600
    sizeRef.current = { w, h }
    el.removeAttribute('width')
    el.removeAttribute('height')
    el.style.width = `${w}px`
    el.style.height = `${h}px`
    el.style.maxWidth = 'none'
    fit()
  }, [svg, fit])

  useEffect(() => {
    const vp = viewportRef.current
    if (!vp) return
    const ro = new ResizeObserver(() => fit())
    ro.observe(vp)
    return () => ro.disconnect()
  }, [fit])

  const zoomAt = useCallback((factor: number, px?: number, py?: number) => {
    const vp = viewportRef.current
    if (!vp) return
    const cx = px ?? vp.clientWidth / 2
    const cy = py ?? vp.clientHeight / 2
    setView((v) => {
      const s = Math.min(MAX_SCALE, Math.max(MIN_SCALE, v.s * factor))
      const k = s / v.s
      return { s, x: cx - (cx - v.x) * k, y: cy - (cy - v.y) * k }
    })
  }, [])

  // Wheel / trackpad pinch (ctrlKey wheel) — needs a non-passive listener to preventDefault.
  useEffect(() => {
    const vp = viewportRef.current
    if (!vp) return
    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      const r = vp.getBoundingClientRect()
      const delta = e.deltaMode === 1 ? e.deltaY * 16 : e.deltaY
      zoomAt(Math.exp(-delta * (e.ctrlKey ? 0.01 : 0.0015)), e.clientX - r.left, e.clientY - r.top)
    }
    vp.addEventListener('wheel', onWheel, { passive: false })
    return () => vp.removeEventListener('wheel', onWheel)
  }, [zoomAt])

  // Pointer drag (pan) and two-pointer pinch.
  const pointers = useRef(new Map<number, { x: number; y: number }>())
  const pinch = useRef<{ dist: number } | null>(null)
  const local = (e: React.PointerEvent) => {
    const r = viewportRef.current!.getBoundingClientRect()
    return { x: e.clientX - r.left, y: e.clientY - r.top }
  }
  const onPointerDown = (e: React.PointerEvent) => {
    if (e.button !== 0 && e.pointerType === 'mouse') return
    e.currentTarget.setPointerCapture(e.pointerId)
    pointers.current.set(e.pointerId, local(e))
    if (pointers.current.size === 2) {
      const [a, b] = [...pointers.current.values()]
      pinch.current = { dist: Math.hypot(a.x - b.x, a.y - b.y) }
    }
    setDragging(true)
  }
  const onPointerMove = (e: React.PointerEvent) => {
    const prev = pointers.current.get(e.pointerId)
    if (!prev) return
    const cur = local(e)
    pointers.current.set(e.pointerId, cur)
    if (pointers.current.size >= 2 && pinch.current) {
      const [a, b] = [...pointers.current.values()]
      const dist = Math.hypot(a.x - b.x, a.y - b.y)
      const mid = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }
      if (pinch.current.dist > 0) zoomAt(dist / pinch.current.dist, mid.x, mid.y)
      // keep the midpoint moving with the fingers
      setView((v) => ({ ...v, x: v.x + (cur.x - prev.x) / 2, y: v.y + (cur.y - prev.y) / 2 }))
      pinch.current.dist = dist
    } else {
      setView((v) => ({ ...v, x: v.x + cur.x - prev.x, y: v.y + cur.y - prev.y }))
    }
  }
  const onPointerUp = (e: React.PointerEvent) => {
    pointers.current.delete(e.pointerId)
    if (pointers.current.size < 2) pinch.current = null
    if (pointers.current.size === 0) setDragging(false)
  }

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === '+' || e.key === '=') zoomAt(STEP)
    else if (e.key === '-' || e.key === '_') zoomAt(1 / STEP)
    else if (e.key === '0') fit()
    else return
    e.preventDefault()
  }

  return (
    <div className="relative min-h-0 flex-1 bg-zinc-50/70" onKeyDown={onKeyDown}>
      <div
        ref={viewportRef}
        className={`absolute inset-0 touch-none overflow-hidden select-none ${dragging ? 'cursor-grabbing' : 'cursor-grab'}`}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        onDoubleClick={(e) => {
          const r = e.currentTarget.getBoundingClientRect()
          zoomAt(2, e.clientX - r.left, e.clientY - r.top)
        }}
        data-zoom-viewport
      >
        <div
          ref={contentRef}
          className="mermaid-diagram absolute top-0 left-0 origin-top-left will-change-transform"
          style={{ transform: `translate(${view.x}px, ${view.y}px) scale(${view.s})` }}
          data-zoom-scale={view.s.toFixed(3)}
          dangerouslySetInnerHTML={{ __html: svg }}
        />
      </div>
      <div className="absolute bottom-[max(1rem,env(safe-area-inset-bottom))] left-1/2 flex -translate-x-1/2 items-center gap-1 rounded-full border bg-white/95 p-1 shadow-md backdrop-blur">
        <Button type="button" size="icon-sm" variant="ghost" className="rounded-full" onClick={() => zoomAt(1 / STEP)} aria-label="缩小" data-zoom-out>
          <Minus />
        </Button>
        <span className="w-12 text-center font-mono text-xs text-zinc-600 tabular-nums" aria-live="polite">
          {Math.round(view.s * 100)}%
        </span>
        <Button type="button" size="icon-sm" variant="ghost" className="rounded-full" onClick={() => zoomAt(STEP)} aria-label="放大" data-zoom-in>
          <Plus />
        </Button>
        <span className="mx-0.5 h-4 w-px bg-zinc-200" aria-hidden="true" />
        <Button type="button" size="sm" variant="ghost" className="h-8 rounded-full px-2.5 text-xs" onClick={fit} aria-label="重置为适合窗口" data-zoom-reset>
          <Maximize className="size-3.5" />
          重置
        </Button>
      </div>
      <div className="pointer-events-none absolute top-3 left-3 flex items-center gap-1 rounded-md bg-white/80 px-2 py-1 text-[11px] text-zinc-500 sm:hidden">
        <Move className="size-3" aria-hidden="true" />
        双指缩放 · 拖动平移
      </div>
    </div>
  )
}
