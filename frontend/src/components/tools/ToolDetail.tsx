import { ArrowRight, Check, ListTree, MessageSquare, Quote, X } from 'lucide-react'
import type { ReactNode } from 'react'

import { DiagramSvg } from '@/components/projects/DiagramSvg'
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { HoverCard, HoverCardContent, HoverCardTrigger } from '@/components/ui/hover-card'
import { Separator } from '@/components/ui/separator'
import type { Lesson, Tool } from '@/data/tools'
import { cn } from '@/lib/utils'

type Props = { tool: Tool; onAsk: (question: string) => void }

const CIRCLED = ['①', '②', '③', '④', '⑤', '⑥', '⑦', '⑧', '⑨']

export function ToolDetail({ tool, onAsk }: Props) {
  return (
    <div className="flex flex-col gap-8 p-3 pb-10 md:p-6 md:pb-12" data-tool-detail={tool.id}>
      <Hero tool={tool} onAsk={onAsk} />
      <Section id="architecture" title="架构" description="离线建库，检索服务和 MCP 工具部署在 Cloudflare，Agent 按需逐层调用。">
        <Architecture tool={tool} />
      </Section>
      <Section id="compare" title="优化前 vs 优化后" description="从「能调通」到「适合被模型稳定调用」，每一项都对应一次具体的改动。">
        <Compare tool={tool} />
      </Section>
      <Section id="lessons" title="踩坑与经验" description="六条我在这次优化里总结下来、以后做任何 Agent 系统都会复用的经验。">
        <div className="grid gap-3 lg:grid-cols-2" data-lessons>
          {tool.lessons.map((lesson, i) => (
            <LessonCard key={lesson.title} lesson={lesson} index={i} />
          ))}
        </div>
      </Section>
      <Takeaway tool={tool} onAsk={onAsk} />
    </div>
  )
}

function Section({ id, title, description, children }: { id: string; title: string; description?: string; children: ReactNode }) {
  return (
    <section aria-labelledby={`tool-${id}`} className="flex flex-col gap-3" data-tool-section={id}>
      <div>
        <h3 id={`tool-${id}`} className="text-sm font-semibold tracking-tight text-zinc-900">
          {title}
        </h3>
        {description && <p className="mt-0.5 text-xs text-zinc-500 sm:text-sm">{description}</p>}
      </div>
      {children}
    </section>
  )
}

/* ------------------------------------------------------------------ Hero */

function Hero({ tool, onAsk }: Props) {
  const Icon = tool.icon
  return (
    <Card className="relative gap-0 overflow-hidden py-0 shadow-xs">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_1px_1px,var(--color-zinc-200)_1px,transparent_0)] [background-size:16px_16px] [mask-image:linear-gradient(to_bottom,black,transparent_70%)]"
      />
      <div className="relative flex flex-col gap-5 p-4 md:flex-row md:items-start md:justify-between md:p-6">
        <div className="flex min-w-0 gap-4">
          <div className="flex size-12 shrink-0 items-center justify-center rounded-xl bg-zinc-900 text-white shadow-sm md:size-14">
            <Icon className="size-6 md:size-7" />
          </div>
          <div className="min-w-0">
            <h2 className="text-xl font-semibold tracking-tight md:text-2xl">{tool.name}</h2>
            <p className="mt-1 text-sm font-medium text-zinc-700 md:text-base">{tool.subtitle}</p>
            <div className="mt-2.5 flex flex-wrap gap-1.5">
              {tool.tags.map((t) => (
                <Badge key={t} variant="outline" className="bg-white font-normal">
                  {t}
                </Badge>
              ))}
            </div>
            <p className="mt-3 max-w-2xl text-sm leading-relaxed text-zinc-600">{tool.summary}</p>
          </div>
        </div>
        <Button size="sm" variant="outline" className="shrink-0 self-start bg-white" onClick={() => onAsk(tool.ask)} title={tool.ask}>
          <MessageSquare className="size-3.5" aria-hidden="true" />
          问 AI
        </Button>
      </div>
      <Separator />
      <div className="relative flex flex-col gap-3 bg-zinc-50/50 p-4 md:px-6">
        <div className="flex flex-col gap-1.5 sm:flex-row sm:items-center sm:gap-3" data-tool-value>
          <span className="text-xs font-medium text-zinc-500">最大的价值</span>
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="rounded-md border border-dashed border-zinc-300 bg-white px-2 py-0.5 text-zinc-500 line-through decoration-zinc-300">{tool.value.from}</span>
            <ArrowRight className="size-4 text-zinc-400" aria-hidden="true" />
            <span className="rounded-md bg-zinc-900 px-2 py-0.5 font-medium text-zinc-50">{tool.value.to}</span>
          </div>
        </div>
      </div>
    </Card>
  )
}

/* ---------------------------------------------------------- Architecture */

function Architecture({ tool }: { tool: Tool }) {
  return (
    <Card className="gap-0 overflow-hidden py-0 shadow-xs">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b bg-zinc-50/60 px-3 py-2.5 sm:px-4">
        <span className="text-sm font-medium">分层架构</span>
        <span className="hidden text-[11px] text-zinc-400 sm:inline">Mermaid · 构建时预渲染</span>
      </div>
      <div className="flex flex-col gap-2 px-3 pt-3 pb-2 sm:px-4">
        <p className="text-xs leading-relaxed text-zinc-500">{tool.diagram.caption}</p>
        <div className="-mx-3 overflow-x-auto px-3 sm:-mx-4 sm:px-4">
          <DiagramSvg id={tool.diagram.id} label={`${tool.name} 架构图`} className="min-w-[320px]" />
        </div>
      </div>
      <Separator />
      <Accordion type="single" collapsible className="px-3 sm:px-4">
        <AccordionItem value="layers" className="border-b-0">
          <AccordionTrigger className="py-3 hover:no-underline">
            <span className="flex items-center gap-2 text-sm font-medium">
              <ListTree className="size-4 text-zinc-500" />
              各层职责
              <Badge variant="secondary" className="font-normal tabular-nums">
                {tool.layers.length} 层
              </Badge>
            </span>
          </AccordionTrigger>
          <AccordionContent>
            <ol className="flex flex-col gap-1.5">
              {tool.layers.map((l, i) => (
                <li key={l.name} className="flex items-start gap-3 rounded-lg border bg-white px-3 py-2">
                  <span className="mt-0.5 font-mono text-[10px] text-zinc-400">{String(i + 1).padStart(2, '0')}</span>
                  <span className="w-20 shrink-0 text-xs font-medium text-zinc-800">{l.name}</span>
                  <span className="min-w-0 text-xs text-zinc-600">{l.detail}</span>
                </li>
              ))}
            </ol>
          </AccordionContent>
        </AccordionItem>
      </Accordion>
    </Card>
  )
}

/* --------------------------------------------------------------- Compare */

function Compare({ tool }: { tool: Tool }) {
  return (
    <Card className="gap-0 overflow-hidden py-0 shadow-xs" data-compare>
      <div className="hidden grid-cols-[6.5rem_1fr_1fr] border-b bg-zinc-50/60 text-xs font-medium text-zinc-500 sm:grid">
        <div className="px-4 py-2">维度</div>
        <div className="flex items-center gap-1.5 border-l px-4 py-2">
          <X className="size-3.5 text-zinc-400" aria-hidden="true" />
          优化前
        </div>
        <div className="flex items-center gap-1.5 border-l px-4 py-2 text-zinc-900">
          <Check className="size-3.5" aria-hidden="true" />
          优化后
        </div>
      </div>
      <ul className="divide-y">
        {tool.compare.map((row) => (
          <li key={row.aspect} className="grid gap-1.5 px-3 py-3 sm:grid-cols-[6.5rem_1fr_1fr] sm:gap-0 sm:p-0">
            <div className="text-xs font-medium text-zinc-800 sm:px-4 sm:py-3">{row.aspect}</div>
            <div className="flex gap-1.5 text-xs leading-relaxed text-zinc-500 sm:border-l sm:px-4 sm:py-3">
              <X className="mt-0.5 size-3.5 shrink-0 text-zinc-300 sm:hidden" aria-label="优化前" />
              <span>{row.before}</span>
            </div>
            <div className="flex gap-1.5 text-xs leading-relaxed text-zinc-800 sm:border-l sm:bg-zinc-50/40 sm:px-4 sm:py-3">
              <Check className="mt-0.5 size-3.5 shrink-0 text-zinc-900 sm:hidden" aria-label="优化后" />
              <span>{row.after}</span>
            </div>
          </li>
        ))}
      </ul>
    </Card>
  )
}

/* --------------------------------------------------------------- Lessons */

function LessonCard({ lesson, index }: { lesson: Lesson; index: number }) {
  const Icon = lesson.icon
  return (
    <Card className="gap-3 px-4 py-4 shadow-xs" data-lesson={index + 1}>
      <div className="flex items-start gap-3">
        <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-zinc-900 text-white">
          <Icon className="size-4" />
        </div>
        <div className="min-w-0">
          <h4 className="text-sm leading-snug font-semibold">
            <span className="mr-1 text-zinc-400">{CIRCLED[index] ?? index + 1}</span>
            {lesson.title}
          </h4>
          <p className="mt-1 text-xs leading-relaxed text-zinc-500">{lesson.thesis}</p>
        </div>
      </div>
      {lesson.ladder && <Ladder steps={lesson.ladder} />}
      <ul className="flex flex-col gap-1.5">
        {lesson.points.map((p) => (
          <li key={p} className="relative pl-3 text-xs leading-relaxed text-zinc-700 before:absolute before:top-[0.6em] before:left-0 before:size-1 before:rounded-full before:bg-zinc-300">
            {p}
          </li>
        ))}
      </ul>
      {lesson.terms && (
        <div className="flex flex-col gap-1.5">
          <span className="text-[11px] text-zinc-400">关键对象（悬停查看定义）</span>
          <div className="flex flex-wrap gap-1">
            {lesson.terms.map((t) => (
              <HoverCard key={t.term} openDelay={120} closeDelay={60}>
                <HoverCardTrigger asChild>
                  <button type="button" className="rounded-md outline-none focus-visible:ring-2 focus-visible:ring-ring/50">
                    <Badge variant="outline" className="cursor-help bg-white font-mono text-[11px] font-normal">
                      {t.term}
                    </Badge>
                  </button>
                </HoverCardTrigger>
                <HoverCardContent side="top" className="w-60 p-3 text-xs">
                  <div className="font-mono font-medium text-zinc-900">{t.term}</div>
                  <p className="mt-1 leading-relaxed text-zinc-600">{t.definition}</p>
                </HoverCardContent>
              </HoverCard>
            ))}
          </div>
        </div>
      )}
      {lesson.chips && (
        <div className="mt-auto flex flex-wrap gap-1 pt-1">
          {lesson.chips.map((c) => (
            <Badge key={c} variant="secondary" className="font-mono text-[10.5px] font-normal">
              {c}
            </Badge>
          ))}
        </div>
      )}
    </Card>
  )
}

/** Soft → hard constraints, drawn as a ladder that darkens step by step. */
function Ladder({ steps }: { steps: NonNullable<Lesson['ladder']> }) {
  const shades = ['bg-white text-zinc-600', 'bg-zinc-100 text-zinc-700', 'bg-zinc-700 text-zinc-50', 'bg-zinc-900 text-zinc-50']
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between text-[10px] text-zinc-400">
        <span>软约束</span>
        <span>硬约束</span>
      </div>
      <ol className="grid grid-cols-2 gap-1 sm:grid-cols-4" aria-label="约束逐级加硬">
        {steps.map((s, i) => (
          <li key={s.label} className={cn('rounded-md border px-2 py-1.5', shades[Math.min(i, shades.length - 1)])}>
            <div className="text-[11px] font-medium">{s.label}</div>
            <div className="text-[10.5px] leading-snug opacity-80">{s.note}</div>
          </li>
        ))}
      </ol>
    </div>
  )
}

/* -------------------------------------------------------------- Takeaway */

function Takeaway({ tool, onAsk }: Props) {
  return (
    <section aria-label="总结" className="flex flex-col gap-3" data-tool-section="takeaway">
      <figure className="relative overflow-hidden rounded-xl bg-zinc-900 px-5 py-6 text-zinc-50 shadow-sm md:px-8 md:py-7" data-takeaway>
        <Quote className="absolute top-4 right-5 size-10 text-zinc-700" aria-hidden="true" />
        <blockquote className="relative max-w-3xl text-base leading-relaxed font-medium md:text-lg">「{tool.takeaway}」</blockquote>
        <figcaption className="relative mt-3 text-xs text-zinc-400">— 做完 {tool.name} 之后，我给自己的工程直觉</figcaption>
      </figure>
      <div className="flex flex-col gap-2 rounded-xl border bg-white p-3 sm:flex-row sm:items-center sm:gap-3" data-ask-row>
        <span className="flex shrink-0 items-center gap-1.5 text-xs font-medium text-zinc-500">
          <MessageSquare className="size-3.5" aria-hidden="true" />
          可以问我
        </span>
        <div className="flex flex-wrap gap-1.5">
          {tool.questions.map((q) => (
            <Button key={q} type="button" variant="outline" size="xs" className="h-auto min-h-6 py-1 text-left text-[11.5px] font-normal whitespace-normal text-zinc-700" onClick={() => onAsk(q)}>
              {q}
            </Button>
          ))}
        </div>
      </div>
    </section>
  )
}
