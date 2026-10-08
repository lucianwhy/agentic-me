import { ArrowRight, Check, Copy, ExternalLink, Lightbulb, MessageSquare, Quote, Timer, Wrench, X } from 'lucide-react'
import { Fragment, useEffect, useRef, useState, type ReactNode } from 'react'

import { DiagramSvg } from '@/components/projects/DiagramSvg'
import { GithubIcon } from '@/components/projects/GithubIcon'
import { ToolStatusBadge } from '@/components/tools/ToolStatusBadge'
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { HoverCard, HoverCardContent, HoverCardTrigger } from '@/components/ui/hover-card'
import { Separator } from '@/components/ui/separator'
import { STATUS_LABEL, type Capability, type ResumeBullet, type Tool, type ToolProblem } from '@/data/tools'
import { cn } from '@/lib/utils'

type Props = { tool: Tool; onAsk: (question: string) => void }

/**
 * The shared tool-page template: 解决什么问题 → 架构图 → 核心能力 → 简历亮点 →
 * 遇到的问题 → 我学到了什么 → 1 分钟讲清楚 → GitHub / Demo (only when a link exists) → 可以问我.
 * All content comes from tools.ts. Section numbers are assigned in order; absent optional
 * sections (简历亮点, GitHub / Demo) are skipped so the index stays consecutive.
 */
export function ToolDetail({ tool, onAsk }: Props) {
  const hasResume = Boolean(tool.resumeBullets?.length)
  const hasLinks = !!(tool.links?.github || tool.links?.demo)
  let n = 0
  const next = () => ++n
  return (
    <div className="flex flex-col gap-8 p-3 pb-10 md:p-6 md:pb-12" data-tool-detail={tool.id}>
      <Hero tool={tool} onAsk={onAsk} />
      <Section id="problem" index={next()} title="解决什么问题">
        <ProblemStatement tool={tool} />
      </Section>
      <Section id="architecture" index={next()} title="架构图" description="检索服务和 MCP 工具部署在 Cloudflare，Agent 通过 MCP Tool Router 按需调用。">
        <Architecture tool={tool} />
      </Section>
      <Section id="capabilities" index={next()} title="核心能力">
        <div className="grid gap-3 sm:grid-cols-2" data-capabilities>
          {tool.capabilities.map((c, i) => (
            <CapabilityCard key={c.title} capability={c} index={i} />
          ))}
        </div>
      </Section>
      {hasResume && tool.resumeBullets && (
        <Section id="resume" index={next()} title="简历亮点">
          <ResumeHighlights bullets={tool.resumeBullets} />
        </Section>
      )}
      <Section id="problems" index={next()} title="遇到的问题 → 原因 → 优化 → 学到什么" description="把它真正当作 Agent Tool 用起来以后，一个个踩到的坑。">
        <div className="grid gap-3 lg:grid-cols-2" data-problems>
          {tool.problems.map((p, i) => (
            <ProblemCard key={p.title} problem={p} index={i} />
          ))}
        </div>
      </Section>
      <Section id="learned" index={next()} title="我学到了什么">
        <Learned tool={tool} />
      </Section>
      <Section id="pitch" index={next()} title="1 分钟讲清楚">
        <Pitch tool={tool} />
      </Section>
      {hasLinks && (
        <Section id="links" index={next()} title="GitHub / Demo">
          <Links tool={tool} />
        </Section>
      )}
      <AskRow tool={tool} onAsk={onAsk} />
    </div>
  )
}

function Section({ id, index, title, description, children }: { id: string; index: number; title: string; description?: string; children: ReactNode }) {
  return (
    <section aria-labelledby={`tool-${id}`} className="flex flex-col gap-3" data-tool-section={id}>
      <div>
        <h3 id={`tool-${id}`} className="flex items-baseline gap-2 text-sm font-semibold tracking-tight text-zinc-900">
          <span className="font-mono text-[11px] font-normal text-zinc-400 tabular-nums">{String(index).padStart(2, '0')}</span>
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
            <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
              <h2 className="text-xl font-semibold tracking-tight md:text-2xl">{tool.name}</h2>
              {tool.nameEn && <span className="text-sm text-zinc-400">{tool.nameEn}</span>}
            </div>
            <p className="mt-2 max-w-2xl text-sm leading-relaxed font-medium text-zinc-800 md:text-[15px]" data-tool-oneliner>
              {tool.oneLiner}
            </p>
            <p className="mt-2 max-w-2xl text-sm leading-relaxed text-zinc-500">{tool.positioning}</p>
          </div>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2 md:flex-col md:items-stretch">
          <Button size="sm" variant="outline" className="bg-white" onClick={() => onAsk(tool.ask)} title={tool.ask}>
            <MessageSquare className="size-3.5" aria-hidden="true" />
            问 AI
          </Button>
          {tool.links?.github && (
            <Button size="sm" variant="outline" className="bg-white" asChild>
              <a href={tool.links.github} target="_blank" rel="noreferrer">
                <GithubIcon className="size-4" />
                GitHub
              </a>
            </Button>
          )}
          {tool.links?.demo && (
            <Button size="sm" asChild>
              <a href={tool.links.demo} target="_blank" rel="noreferrer">
                <ExternalLink className="size-3.5" />
                Demo
              </a>
            </Button>
          )}
        </div>
      </div>
      <Separator />
      <div className="relative grid grid-cols-1 gap-px bg-zinc-200/70 min-[390px]:grid-cols-2 lg:grid-cols-4" data-tool-keywords>
        {tool.keywords.map((k, i) => (
          <div key={k.label} className="flex min-w-0 flex-col gap-1.5 bg-zinc-50 px-3 py-2.5 sm:px-4 sm:py-3">
            <span className="flex w-fit max-w-full min-w-0 items-start gap-1.5 rounded-md border border-zinc-200 bg-white px-1.5 py-0.5">
              <span className="mt-px flex size-4 shrink-0 items-center justify-center rounded-[3px] bg-zinc-900 font-mono text-[9px] font-medium text-white tabular-nums">
                {i + 1}
              </span>
              <span className="min-w-0 text-[11.5px] leading-snug font-medium wrap-break-word text-zinc-900">{k.label}</span>
            </span>
            <span className="text-[11px] leading-snug text-zinc-500">{k.note}</span>
          </div>
        ))}
      </div>
    </Card>
  )
}

/* ------------------------------------------------------- 1. 解决什么问题 */

function ProblemStatement({ tool }: { tool: Tool }) {
  return (
    <Card className="gap-2 px-4 py-4 shadow-xs md:px-5">
      <p className="border-l-2 border-zinc-900 pl-3 text-sm leading-relaxed font-medium text-zinc-900">{tool.problem.oneLiner}</p>
      <p className="text-sm leading-relaxed text-zinc-600">{tool.problem.paragraph}</p>
      {tool.problem.dataSource && <p className="text-xs text-zinc-400">{tool.problem.dataSource}</p>}
    </Card>
  )
}

/* ------------------------------------------------------------ 2. 架构图 */

function Architecture({ tool }: { tool: Tool }) {
  return (
    <Card className="gap-0 overflow-hidden py-0 shadow-xs">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b bg-zinc-50/60 px-3 py-2.5 sm:px-4">
        <span className="text-sm font-medium">调用链路与分层</span>
        <span className="flex items-center gap-2 text-[11px] text-zinc-400">
          {tool.diagram.legend && (
            <span className="flex items-center gap-1.5" data-diagram-legend>
              <span className="inline-block h-3 w-5 rounded-sm border border-dashed border-zinc-400 bg-zinc-50" aria-hidden="true" />
              {tool.diagram.legend}
            </span>
          )}
          <span className="hidden sm:inline">· Mermaid 构建时预渲染</span>
        </span>
      </div>
      <div className="flex flex-col gap-2 px-3 pt-3 pb-3 sm:px-4">
        <p className="text-xs leading-relaxed text-zinc-500">{tool.diagram.caption}</p>
        <div className="-mx-3 overflow-x-auto px-3 sm:-mx-4 sm:px-4">
          <DiagramSvg id={tool.diagram.id} label={`${tool.name} 架构图`} className="min-w-[240px]" />
        </div>
      </div>
    </Card>
  )
}

/* ---------------------------------------------------------- clipboard */

/** navigator.clipboard on secure origins, with a textarea fallback when it is missing. */
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

function resumeBulletClipboard(b: ResumeBullet): string {
  const note = b.copyNote ?? (b.status && b.status !== 'done' ? STATUS_LABEL[b.status] : undefined)
  return `• ${b.text}${note ? `（${note}）` : ''}`
}

function useCopiedFlag(ms = 1500) {
  const [copied, setCopied] = useState(false)
  const timer = useRef<number | undefined>(undefined)
  useEffect(() => () => window.clearTimeout(timer.current), [])
  const mark = () => {
    setCopied(true)
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => setCopied(false), ms)
  }
  return [copied, mark] as const
}

/* ---------------------------------------------------------- 3. 核心能力 */

function CapabilityCard({ capability: c, index }: { capability: Capability; index: number }) {
  return (
    <Card className={cn('gap-2 px-4 py-4 shadow-xs', c.status && c.status !== 'done' && 'border-dashed')} data-capability={index + 1}>
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-baseline gap-2">
          <span className="font-mono text-lg font-semibold text-zinc-300 tabular-nums">{String(index + 1).padStart(2, '0')}</span>
          <h4 className="text-sm leading-snug font-semibold">{c.title}</h4>
        </div>
        <ToolStatusBadge status={c.status} className="mt-0.5" />
      </div>
      <p className="text-xs leading-relaxed text-zinc-600">{c.detail}</p>
      {c.statusNote && <p className="text-[11px] leading-relaxed text-amber-800/80">{c.statusNote}</p>}
      {c.chips && (
        <div className="mt-auto flex flex-wrap gap-1 pt-1">
          {c.chips.map((chip) => (
            <Badge key={chip} variant="secondary" className="font-mono text-[10.5px] font-normal">
              {chip}
            </Badge>
          ))}
        </div>
      )}
    </Card>
  )
}

/* ---------------------------------------------------------- 4. 简历亮点 */

function ResumeHighlights({ bullets }: { bullets: ResumeBullet[] }) {
  const [copied, mark] = useCopiedFlag()
  const allText = bullets.map(resumeBulletClipboard).join('\n')

  const onCopyAll = async () => {
    if (await copyText(allText)) mark()
  }

  return (
    <Card className="gap-0 overflow-hidden py-0 shadow-xs">
      <div className="flex items-center justify-between gap-2 border-b bg-zinc-50/60 px-3 py-1.5 sm:px-4 sm:py-2">
        <span className="min-w-0 truncate text-xs font-medium text-zinc-500">
          可直接贴进简历
          <span className="hidden sm:inline"> · 复制时自动标注设计中部分</span>
        </span>
        <Button type="button" size="xs" variant="outline" className="shrink-0 bg-white" data-copy-resume onClick={onCopyAll}>
          {copied ? <Check className="size-3" aria-hidden="true" /> : <Copy className="size-3" aria-hidden="true" />}
          {copied ? '已复制' : '复制全部'}
        </Button>
      </div>
      <ol className="divide-y" data-resume-bullets>
        {bullets.map((b, i) => (
          <ResumeBulletRow key={b.text} bullet={b} index={i} />
        ))}
      </ol>
    </Card>
  )
}

function ResumeBulletRow({ bullet: b, index }: { bullet: ResumeBullet; index: number }) {
  const [copied, mark] = useCopiedFlag()
  const onCopy = async () => {
    if (await copyText(resumeBulletClipboard(b))) mark()
  }
  return (
    <li className="group/rb relative flex gap-2.5 px-3 py-2.5 sm:gap-3 sm:px-4 sm:py-3.5">
      <span className="mt-px flex size-[18px] shrink-0 items-center justify-center rounded-md bg-zinc-100 font-mono text-[10.5px] font-medium text-zinc-600 tabular-nums sm:mt-0.5 sm:size-5 sm:text-[11px]">
        {index + 1}
      </span>
      <div className="min-w-0 flex-1 pr-0 md:pr-8">
        <p className="text-[13.5px] leading-relaxed text-zinc-800 sm:text-sm sm:leading-[1.7]">
          {b.text}
          {b.status && b.status !== 'done' && <ToolStatusBadge status={b.status} className="ml-1.5 align-middle" />}
        </p>
        {b.statusNote && <p className="mt-1 text-[11px] leading-relaxed text-amber-800/80">{b.statusNote}</p>}
      </div>
      <Button
        type="button"
        size="icon-xs"
        variant="ghost"
        className={cn(
          'absolute top-2.5 right-2 hidden text-zinc-400 hover:text-zinc-900 md:inline-flex',
          copied ? 'opacity-100' : 'opacity-0 group-hover/rb:opacity-100 focus-visible:opacity-100',
        )}
        aria-label={copied ? '已复制' : '复制这条'}
        onClick={onCopy}
      >
        {copied ? <Check /> : <Copy />}
      </Button>
    </li>
  )
}

/* ---------------------------------------------- 5. 问题 → 原因 → 优化 → 学到 */

const STEP_ROWS = [
  { key: 'cause', label: '原因', icon: X },
  { key: 'fix', label: '优化', icon: Wrench },
  { key: 'learned', label: '学到', icon: Lightbulb },
] as const

function ProblemCard({ problem: p, index }: { problem: ToolProblem; index: number }) {
  const Icon = p.icon
  return (
    <Card className={cn('gap-3 px-4 py-4 shadow-xs', p.schema && 'lg:col-span-2')} data-problem={index + 1}>
      <div className="flex items-start gap-3">
        <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-zinc-900 text-white">
          <Icon className="size-4" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="font-mono text-[11px] font-semibold text-zinc-400">P{index + 1}</span>
            <h4 className="text-sm leading-snug font-semibold">{p.title}</h4>
            <ToolStatusBadge status={p.status} />
          </div>
          {p.insight && (
            <Badge variant="outline" className="mt-1.5 bg-white font-mono text-[10.5px] font-normal text-zinc-700">
              {p.insight}
            </Badge>
          )}
          {p.statusNote && <p className="mt-1 text-[11px] text-amber-800/80">{p.statusNote}</p>}
        </div>
      </div>
      <dl className="flex flex-col gap-2">
        {STEP_ROWS.map(({ key, label, icon: RowIcon }) => (
          <div key={key} className="grid grid-cols-[3.25rem_1fr] gap-2 text-xs leading-relaxed">
            <dt className="flex items-center gap-1 self-start pt-px font-medium text-zinc-500">
              <RowIcon className="size-3 text-zinc-400" aria-hidden="true" />
              {label}
            </dt>
            <dd className={cn(key === 'learned' ? 'font-medium text-zinc-900' : 'text-zinc-700')}>{p[key]}</dd>
          </div>
        ))}
      </dl>
      {p.flow && <Flow items={p.flow} />}
      {p.roles && <Roles roles={p.roles} />}
      {p.ladder && <Ladder steps={p.ladder} />}
      {p.schema && <Schema schema={p.schema} />}
      {p.quote && (
        <blockquote className="flex gap-2 rounded-lg border-l-2 border-zinc-900 bg-zinc-50 px-3 py-2 text-xs leading-relaxed text-zinc-800">
          <Quote className="mt-0.5 size-3.5 shrink-0 text-zinc-400" aria-hidden="true" />
          {p.quote}
        </blockquote>
      )}
      {p.chips && (
        <div className="flex flex-wrap gap-1">
          {p.chips.map((c) => (
            <Badge key={c} variant="secondary" className="font-mono text-[10.5px] font-normal">
              {c}
            </Badge>
          ))}
        </div>
      )}
    </Card>
  )
}

function Flow({ items }: { items: NonNullable<ToolProblem['flow']> }) {
  return (
    <ol className="flex flex-wrap items-center gap-1 rounded-lg border bg-zinc-50 p-2" aria-label="逐级展开">
      {items.map((item, i) => (
        <Fragment key={item.label}>
          {i > 0 && <ArrowRight className="size-3 text-zinc-300" aria-hidden="true" />}
          <li
            className={cn(
              'flex items-center gap-1 rounded-md border bg-white px-1.5 py-0.5 font-mono text-[10.5px] text-zinc-700',
              item.status && item.status !== 'done' && 'border-dashed text-zinc-500',
            )}
          >
            {item.label}
            <ToolStatusBadge status={item.status} />
          </li>
        </Fragment>
      ))}
    </ol>
  )
}

function Roles({ roles }: { roles: NonNullable<ToolProblem['roles']> }) {
  return (
    <ul className="grid gap-1 sm:grid-cols-3">
      {roles.map((r) => (
        <li key={r.name} className={cn('rounded-md border bg-white px-2 py-1.5', r.status && r.status !== 'done' && 'border-dashed')}>
          <div className="flex flex-wrap items-center gap-1">
            <code className="font-mono text-[10.5px] text-zinc-900">{r.name}</code>
            <ToolStatusBadge status={r.status} />
          </div>
          <div className="text-[11px] text-zinc-500">= {r.role}</div>
        </li>
      ))}
    </ul>
  )
}

/** Soft → hard constraints, drawn as a ladder that darkens step by step. */
function Ladder({ steps }: { steps: NonNullable<ToolProblem['ladder']> }) {
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

function Schema({ schema }: { schema: NonNullable<ToolProblem['schema']> }) {
  const col = (title: string, items: string[], after: boolean) => (
    <div className={cn('flex flex-col gap-1.5 rounded-lg border p-2.5', after ? 'border-zinc-300 bg-white' : 'border-dashed bg-zinc-50')}>
      <span className={cn('flex items-center gap-1 text-[11px] font-medium', after ? 'text-zinc-900' : 'text-zinc-500')}>
        {after ? <Check className="size-3" aria-hidden="true" /> : <X className="size-3" aria-hidden="true" />}
        {title}
      </span>
      <div className="flex flex-wrap gap-1">
        {items.map((item) => (
          <code
            key={item}
            className={cn('rounded border px-1.5 py-0.5 font-mono text-[10.5px]', after ? 'border-zinc-200 bg-zinc-50 text-zinc-900' : 'border-zinc-200 bg-white text-zinc-400 line-through decoration-zinc-300')}
          >
            {item}
          </code>
        ))}
      </div>
    </div>
  )
  return (
    <div className="grid gap-2 sm:grid-cols-[1fr_auto_1fr] sm:items-stretch" data-schema>
      {col('优化前：底层参数全部暴露', schema.before, false)}
      <ArrowRight className="hidden size-4 self-center text-zinc-300 sm:block" aria-hidden="true" />
      {col('优化后：只留高层语义参数', schema.after, true)}
    </div>
  )
}

/* -------------------------------------------------------- 6. 我学到了什么 */

function Learned({ tool }: { tool: Tool }) {
  return (
    <div className="flex flex-col gap-3">
      <Card className="gap-0 overflow-hidden py-0 shadow-xs">
        <ul className="grid divide-y sm:grid-cols-2 sm:divide-y-0" data-learned>
          {tool.learned.map((l, i) => (
            <li key={l.keyword} className={cn('flex flex-col gap-0.5 px-4 py-3', i % 2 === 1 && 'sm:border-l', i >= 2 && 'sm:border-t')}>
              <HoverCard openDelay={150} closeDelay={60}>
                <HoverCardTrigger asChild>
                  <span className="w-fit cursor-default text-[12.5px] font-semibold text-zinc-900">{l.keyword}</span>
                </HoverCardTrigger>
                <HoverCardContent side="top" className="w-72 p-3 text-xs leading-relaxed text-zinc-600">
                  {tool.keywords.find((k) => k.label === l.keyword)?.note ?? l.keyword}
                </HoverCardContent>
              </HoverCard>
              <span className="text-xs leading-relaxed text-zinc-600">{l.text}</span>
            </li>
          ))}
        </ul>
      </Card>
      <figure className="relative overflow-hidden rounded-xl bg-zinc-900 px-5 py-6 text-zinc-50 shadow-sm md:px-8 md:py-7" data-takeaway>
        <Quote className="absolute top-4 right-5 size-10 text-zinc-700" aria-hidden="true" />
        <blockquote className="relative max-w-3xl text-base leading-relaxed font-medium md:text-lg">「{tool.takeaway}」</blockquote>
        <figcaption className="relative mt-3 text-xs text-zinc-400">— 做完 {tool.name} 之后，我给自己的工程直觉</figcaption>
      </figure>
    </div>
  )
}

/* ------------------------------------------------------- 7. 1 分钟讲清楚 */

function Pitch({ tool }: { tool: Tool }) {
  return (
    <Card className="gap-0 py-0 shadow-xs" data-pitch>
      <Accordion type="single" collapsible className="px-4">
        <AccordionItem value="pitch" className="border-b-0">
          <AccordionTrigger className="py-3 hover:no-underline">
            <span className="flex items-center gap-2 text-sm font-medium">
              <Timer className="size-4 text-zinc-500" aria-hidden="true" />
              面试时我会这样讲
              <Badge variant="secondary" className="font-normal">约 1 分钟</Badge>
            </span>
          </AccordionTrigger>
          <AccordionContent>
            <div className="flex flex-col gap-2.5 border-l-2 border-zinc-200 pl-3">
              {tool.pitch.map((para) => (
                <p key={para} className="text-sm leading-relaxed text-zinc-700">
                  {para}
                </p>
              ))}
            </div>
          </AccordionContent>
        </AccordionItem>
      </Accordion>
    </Card>
  )
}

/* ------------------------------------------------------ 8. GitHub / Demo */

function Links({ tool }: { tool: Tool }) {
  return (
    <div className="flex flex-wrap gap-2">
      {tool.links?.github && (
        <Button variant="outline" size="sm" asChild>
          <a href={tool.links.github} target="_blank" rel="noreferrer">
            <GithubIcon className="size-4" />
            {tool.links.github.replace(/^https?:\/\/(www\.)?/, '')}
          </a>
        </Button>
      )}
      {tool.links?.demo && (
        <Button size="sm" asChild>
          <a href={tool.links.demo} target="_blank" rel="noreferrer">
            <ExternalLink className="size-3.5" />
            在线 Demo
          </a>
        </Button>
      )}
    </div>
  )
}

/* ------------------------------------------------------------ 可以问我 */

function AskRow({ tool, onAsk }: Props) {
  return (
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
  )
}
