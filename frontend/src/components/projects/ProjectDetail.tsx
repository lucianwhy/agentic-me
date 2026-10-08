import { ArrowDown, ArrowRight, ExternalLink, Info, ListTree, Workflow } from 'lucide-react'
import { Fragment } from 'react'

import { GithubIcon } from '@/components/projects/GithubIcon'
import { DiagramSvg } from '@/components/projects/DiagramSvg'
import { RetrievalDemo } from '@/components/projects/RetrievalDemo'
import { StatusBadge } from '@/components/projects/StatusBadge'
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { HoverCard, HoverCardContent, HoverCardTrigger } from '@/components/ui/hover-card'
import { Kbd } from '@/components/ui/kbd'
import { Separator } from '@/components/ui/separator'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { groupIcon, type Feature, type PipelineStep, type Project, type TechItem } from '@/data/projects'
import { cn } from '@/lib/utils'

type Props = { project: Project; model: string; ensureAuth: () => boolean; onAuthRequired: () => void }

export function ProjectDetail({ project, model, ensureAuth, onAuthRequired }: Props) {
  return (
    <div className="flex flex-col gap-8 p-3 pb-10 md:p-6 md:pb-12">
      <Hero project={project} />
      <Section id="metrics" title="关键指标" description="全部来自代码配置、向量库查询或实测；悬停可查看来源。">
        <Metrics project={project} />
      </Section>
      <Section id="pipeline" title="架构与 RAG 流程" description="离线把资料切块、向量化入库；提问时用原问题检索最相关的片段，交给模型带引用回答。">
        <Architecture project={project} />
      </Section>
      {project.demo && (
        <Section id="demo" title="看看它是怎么回答的" description="输入问题，实时查看检索阶段命中了哪些资料片段（不调用大模型）。">
          <RetrievalDemo samples={project.demo.sampleQuestions} model={model} ensureAuth={ensureAuth} onAuthRequired={onAuthRequired} />
        </Section>
      )}
      <Section id="features" title="功能亮点">
        <Bento features={project.features} />
      </Section>
      <Section id="infra" title="部署与运维">
        <Infra project={project} />
      </Section>
    </div>
  )
}

function Section({ id, title, description, children }: { id: string; title: string; description?: string; children: React.ReactNode }) {
  return (
    <section aria-labelledby={`project-${id}`} className="flex flex-col gap-3">
      <div>
        <h3 id={`project-${id}`} className="text-sm font-semibold tracking-tight text-zinc-900">
          {title}
        </h3>
        {description && <p className="mt-0.5 text-xs text-zinc-500 sm:text-sm">{description}</p>}
      </div>
      {children}
    </section>
  )
}

/* ------------------------------------------------------------------ Hero */

function Hero({ project }: { project: Project }) {
  const Icon = project.icon
  const groups = Array.from(new Set(project.stack.map((t) => t.group)))
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
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
              <h2 className="text-xl font-semibold tracking-tight md:text-2xl">{project.name}</h2>
            </div>
            <p className="mt-1 text-sm font-medium text-zinc-700 md:text-base">{project.tagline}</p>
            <p className="mt-2 max-w-2xl text-sm leading-relaxed text-zinc-500">{project.summary}</p>
            <div className="mt-3 flex flex-wrap items-center gap-1.5">
              {project.statuses.map((s) => (
                <StatusBadge key={s.label} status={s} />
              ))}
              <Badge variant="outline" className="font-normal text-zinc-500">
                {project.period}
              </Badge>
              <Badge variant="outline" className="font-normal text-zinc-500">
                {project.role}
              </Badge>
            </div>
          </div>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2 md:flex-col md:items-stretch">
          {project.links.map((link) =>
            link.kind === 'github' ? (
              <Button key={link.href} variant="outline" size="sm" asChild>
                <a href={link.href} target="_blank" rel="noreferrer">
                  <GithubIcon className="size-4" />
                  {link.label}
                  <ExternalLink className="size-3 text-zinc-400" />
                </a>
              </Button>
            ) : (
              <Button key={link.href} size="sm" asChild>
                <a href={link.href} target="_blank" rel="noreferrer" className="font-mono">
                  <ExternalLink className="size-3.5" />
                  {link.label}
                </a>
              </Button>
            ),
          )}
        </div>
      </div>
      <Separator />
      <div className="relative grid gap-x-6 gap-y-3 bg-zinc-50/50 p-4 sm:grid-cols-2 md:px-6">
        {groups.map((group) => {
          const GroupIcon = groupIcon[group]
          return (
            <div key={group} className="flex items-start gap-3">
              <div className="flex w-20 shrink-0 items-center gap-1.5 pt-0.5 text-xs text-zinc-500">
                <GroupIcon className="size-3.5" />
                {group}
              </div>
              <div className="flex flex-wrap gap-1">
                {project.stack
                  .filter((t) => t.group === group)
                  .map((t) => (
                    <TechBadge key={t.name} tech={t} />
                  ))}
              </div>
            </div>
          )
        })}
      </div>
    </Card>
  )
}

function TechBadge({ tech }: { tech: TechItem }) {
  return (
    <HoverCard openDelay={150} closeDelay={50}>
      <HoverCardTrigger asChild>
        <button type="button" className="rounded-4xl outline-none focus-visible:ring-2 focus-visible:ring-ring/50">
          <Badge variant="outline" className="cursor-default bg-white font-normal">
            {tech.name}
          </Badge>
        </button>
      </HoverCardTrigger>
      <HoverCardContent className="w-64 text-sm" side="top">
        <div className="font-medium">{tech.name}</div>
        <p className="mt-1 text-xs text-zinc-500">{tech.role}</p>
      </HoverCardContent>
    </HoverCard>
  )
}

/* --------------------------------------------------------------- Metrics */

function Metrics({ project }: { project: Project }) {
  return (
    <div className="grid grid-cols-2 gap-2 sm:gap-3 lg:grid-cols-4">
      {project.metrics.map((m) => (
        <Card key={m.label} className="gap-1 px-3 py-3 shadow-xs sm:px-4">
          <div className="flex items-center justify-between gap-1">
            <span className="truncate text-xs text-zinc-500">{m.label}</span>
            <Tooltip>
              <TooltipTrigger asChild>
                <button type="button" className="shrink-0 rounded text-zinc-300 hover:text-zinc-500" aria-label={`${m.label}数据来源：${m.source}`}>
                  <Info className="size-3.5" />
                </button>
              </TooltipTrigger>
              <TooltipContent side="top" className="max-w-60">
                来源：{m.source}
              </TooltipContent>
            </Tooltip>
          </div>
          <div className="text-2xl font-semibold tracking-tight tabular-nums">
            {m.value}
            {m.unit && <span className="ml-1 text-sm font-normal text-zinc-500">{m.unit}</span>}
          </div>
          <div className="line-clamp-2 text-[11px] leading-snug text-zinc-500 sm:text-xs">{m.hint}</div>
        </Card>
      ))}
    </div>
  )
}

/* ---------------------------------------------------------- Architecture */

function Architecture({ project }: { project: Project }) {
  const diagrams = project.diagrams ?? []
  const steps = (
    <Accordion type="single" collapsible className="px-3 sm:px-4">
      <AccordionItem value="steps" className="border-b-0">
        <AccordionTrigger className="py-3 hover:no-underline">
          <span className="flex items-center gap-2 text-sm font-medium">
            <ListTree className="size-4 text-zinc-500" />
            各步骤详情
            <Badge variant="secondary" className="font-normal tabular-nums">
              {project.pipeline.length} 步
            </Badge>
          </span>
        </AccordionTrigger>
        <AccordionContent>
          <Pipeline steps={project.pipeline} />
        </AccordionContent>
      </AccordionItem>
    </Accordion>
  )
  if (!diagrams.length) return <Pipeline steps={project.pipeline} />
  return (
    <Card className="gap-0 overflow-hidden py-0 shadow-xs">
      <Tabs defaultValue={diagrams[0].id} className="gap-0">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b bg-zinc-50/60 px-3 py-2.5 sm:px-4">
          <TabsList aria-label="架构图">
            {diagrams.map((d) => (
              <TabsTrigger key={d.id} value={d.id} className="px-3 text-xs sm:text-sm">
                {d.label}
              </TabsTrigger>
            ))}
          </TabsList>
          <span className="hidden text-[11px] text-zinc-400 sm:inline">Mermaid · 构建时预渲染</span>
        </div>
        {diagrams.map((d) => (
          <TabsContent key={d.id} value={d.id} className="mt-0 flex flex-col gap-2 px-3 pt-3 pb-2 sm:px-4">
            <p className="text-xs leading-relaxed text-zinc-500">{d.caption}</p>
            <div className="-mx-3 overflow-x-auto px-3 sm:-mx-4 sm:px-4">
              <DiagramSvg id={d.id} label={`${project.name} ${d.label}`} className="min-w-[320px]" />
            </div>
          </TabsContent>
        ))}
      </Tabs>
      <Separator />
      {steps}
    </Card>
  )
}

/* -------------------------------------------------------------- Pipeline */

const PHASES: Record<PipelineStep['phase'], { label: string; note: string }> = {
  build: { label: '离线建库', note: '向量库为空时自动构建；已存在则直接加载' },
  query: { label: '在线问答', note: '每次提问执行；查询用同一 Embedding 模型向量化' },
}

function Pipeline({ steps }: { steps: PipelineStep[] }) {
  const phases = (['build', 'query'] as const).map((phase) => ({ phase, steps: steps.filter((s) => s.phase === phase) }))
  let n = 0
  return (
    <div className="flex flex-col gap-4">
      {phases.map(({ phase, steps: group }, gi) => (
        <Fragment key={phase}>
          {gi > 0 && (
            <div className="flex items-center gap-2 pl-1 text-xs text-zinc-400" aria-hidden="true">
              <ArrowDown className="size-3.5" />
              <span>Chroma 向量库 → 按相似度检索</span>
            </div>
          )}
          <div className="rounded-xl border border-dashed bg-zinc-50/50 p-2.5 sm:p-3">
            <div className="mb-2.5 flex flex-wrap items-center gap-2 px-0.5">
              <Badge variant={phase === 'build' ? 'secondary' : 'default'} className="gap-1">
                <Workflow className="size-3" />
                {PHASES[phase].label}
              </Badge>
              <span className="text-xs text-zinc-500">{PHASES[phase].note}</span>
            </div>
            <ol className="flex flex-col md:flex-row md:items-stretch">
              {group.map((step, i) => {
                n += 1
                return (
                  <Fragment key={step.title}>
                    {i > 0 && <Connector />}
                    <li className="md:min-w-0 md:flex-1">
                      <StepCard step={step} index={n} />
                    </li>
                  </Fragment>
                )
              })}
            </ol>
          </div>
        </Fragment>
      ))}
    </div>
  )
}

function Connector() {
  return (
    <li aria-hidden="true" className="flex shrink-0 items-center justify-center py-1 text-zinc-300 md:w-6 md:py-0">
      <ArrowDown className="size-4 md:hidden" />
      <ArrowRight className="hidden size-4 md:block" />
    </li>
  )
}

function StepCard({ step, index }: { step: PipelineStep; index: number }) {
  const Icon = step.icon
  return (
    <Card className="h-full gap-2 px-3 py-3 shadow-xs">
      <div className="flex items-center gap-2.5">
        <div className="flex size-8 shrink-0 items-center justify-center rounded-lg border bg-zinc-50 text-zinc-700">
          <Icon className="size-4" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline gap-1.5">
            <span className="font-mono text-[10px] text-zinc-400">{String(index).padStart(2, '0')}</span>
            <span className="truncate text-sm font-medium">{step.title}</span>
          </div>
          <div className="truncate text-[11px] text-zinc-500">{step.subtitle}</div>
        </div>
      </div>
      <p className="text-xs leading-relaxed text-zinc-600">{step.description}</p>
      <code className="mt-auto self-start truncate rounded bg-zinc-100 px-1.5 py-0.5 font-mono text-[10px] text-zinc-600 max-w-full">
        {step.code}
      </code>
    </Card>
  )
}

/* ----------------------------------------------------------------- Bento */

function Bento({ features }: { features: Feature[] }) {
  return (
    <div className="grid grid-flow-dense gap-2 sm:grid-cols-2 sm:gap-3 lg:grid-cols-4">
      {features.map((f) => (
        <FeatureCard key={f.title} feature={f} />
      ))}
    </div>
  )
}

function FeatureCard({ feature }: { feature: Feature }) {
  const Icon = feature.icon
  const wide = feature.size === 'wide'
  const tall = feature.size === 'tall'
  return (
    <Card className={cn('gap-3 px-4 py-4 shadow-xs', wide && 'sm:col-span-2', tall && 'lg:row-span-2')}>
      <CardHeader className="gap-1.5 px-0">
        <div className="mb-1 flex size-8 items-center justify-center rounded-lg bg-zinc-900 text-white">
          <Icon className="size-4" />
        </div>
        <CardTitle className="text-sm">{feature.title}</CardTitle>
        <CardDescription className="text-xs leading-relaxed">{feature.description}</CardDescription>
      </CardHeader>
      {(wide || tall || feature.tags) && (
        <CardContent className="mt-auto px-0">
          {feature.title === 'SSE 流式输出' ? (
            <SseIllustration />
          ) : feature.title === '实时检索状态' ? (
            <StatusIllustration />
          ) : tall ? (
            <SourcesIllustration />
          ) : (
            <div className="flex flex-wrap gap-1">
              {feature.tags?.map((t) => (
                <Badge key={t} variant="secondary" className="font-mono text-[10px] font-normal">
                  {t}
                </Badge>
              ))}
            </div>
          )}
        </CardContent>
      )}
    </Card>
  )
}

/** Event sequence actually emitted by POST /chat/stream. */
function SseIllustration() {
  const events = [
    { type: 'status', detail: 'retrieving' },
    { type: 'status', detail: 'generating' },
    { type: 'token', detail: '…' },
    { type: 'token', detail: '…' },
    { type: 'done', detail: 'sources' },
  ]
  return (
    <div className="flex flex-wrap items-center gap-1 rounded-lg border bg-zinc-50 p-2 font-mono text-[10px] text-zinc-600">
      {events.map((e, i) => (
        <Fragment key={i}>
          {i > 0 && <ArrowRight className="size-3 text-zinc-300" aria-hidden="true" />}
          <span className={cn('rounded border bg-white px-1.5 py-0.5', e.type === 'done' && 'border-zinc-900 bg-zinc-900 text-white')}>
            {e.type}
            <span className={cn('ml-1', e.type === 'done' ? 'text-zinc-300' : 'text-zinc-400')}>{e.detail}</span>
          </span>
        </Fragment>
      ))}
    </div>
  )
}

/** Status lines the chat bubble actually shows while waiting (AssistantMessage.tsx). */
function StatusIllustration() {
  const steps = [
    { label: '正在检索简历…', stage: 'retrieving', done: true },
    { label: '已找到 4 段资料，正在组织回答…', stage: 'generating', done: true },
    { label: '逐字输出回答', stage: 'token', done: false },
  ]
  return (
    <ol className="flex flex-col gap-0 rounded-lg border bg-zinc-50 p-2.5" aria-hidden="true">
      {steps.map((s, i) => (
        <li key={s.stage} className="flex gap-2">
          <div className="flex flex-col items-center">
            <span className={cn('mt-0.5 size-2 rounded-full', s.done ? 'bg-zinc-900' : 'border border-zinc-400 bg-white')} />
            {i < steps.length - 1 && <span className="my-0.5 w-px flex-1 bg-zinc-300" />}
          </div>
          <div className="pb-2.5">
            <div className="text-[11px] text-zinc-700">{s.label}</div>
            <div className="font-mono text-[10px] text-zinc-400">{s.stage}</div>
          </div>
        </li>
      ))}
    </ol>
  )
}

/** Shape of the 参考来源 list under each answer (labels match the real UI). */
function SourcesIllustration() {
  const rows = [
    { label: '简历 PDF', page: '第 1 页', w: 'w-11/12' },
    { label: '简历 PDF', page: '第 2 页', w: 'w-3/4' },
    { label: '关于我', page: '', w: 'w-5/6' },
  ]
  return (
    <div className="flex flex-col gap-1.5 rounded-lg border bg-zinc-50 p-2" aria-hidden="true">
      <div className="text-[10px] font-medium text-zinc-500">参考来源 · {rows.length}</div>
      {rows.map((r, i) => (
        <div key={i} className="rounded-md border bg-white p-2">
          <div className="flex items-center gap-1.5 text-[10px] text-zinc-600">
            <span className="font-medium">{r.label}</span>
            {r.page && <span className="text-zinc-400">{r.page}</span>}
          </div>
          <div className={cn('mt-1.5 h-1.5 rounded bg-zinc-200', r.w)} />
          <div className="mt-1 h-1.5 w-1/2 rounded bg-zinc-100" />
        </div>
      ))}
    </div>
  )
}

/* ----------------------------------------------------------------- Infra */

function Infra({ project }: { project: Project }) {
  const hops = ['浏览器 · wanghaoyue.me', "Nginx · HTTPS（Let's Encrypt）", 'uvicorn · FastAPI', 'Chroma（本地）+ Embedding / LLM API']
  return (
    <div className="grid gap-3 lg:grid-cols-5">
      <Card className="gap-0 px-4 py-1 shadow-xs lg:col-span-3">
        <Accordion type="single" collapsible defaultValue={project.infra[0]?.title}>
          {project.infra.map((item) => {
            const Icon = item.icon
            return (
              <AccordionItem key={item.title} value={item.title}>
                <AccordionTrigger className="py-3 hover:no-underline">
                  <span className="flex items-center gap-3">
                    <span className="flex size-7 items-center justify-center rounded-md border bg-zinc-50 text-zinc-700">
                      <Icon className="size-3.5" />
                    </span>
                    <span className="flex flex-col items-start gap-0.5 sm:flex-row sm:items-center sm:gap-2">
                      <span className="text-sm font-medium">{item.title}</span>
                      <span className="text-xs font-normal text-zinc-500">{item.summary}</span>
                    </span>
                  </span>
                </AccordionTrigger>
                <AccordionContent>
                  <ul className="ml-10 flex list-disc flex-col gap-1 text-xs text-zinc-600 marker:text-zinc-300">
                    {item.points.map((p) => (
                      <li key={p}>{p}</li>
                    ))}
                  </ul>
                </AccordionContent>
              </AccordionItem>
            )
          })}
        </Accordion>
      </Card>
      <div className="flex flex-col gap-3 lg:col-span-2">
        <Card className="gap-2.5 px-4 py-4 shadow-xs">
          <div className="text-xs font-medium text-zinc-500">请求链路</div>
          <ol className="flex flex-col gap-1.5">
            {hops.map((hop, i) => (
              <li key={hop} className="flex items-center gap-2 text-xs">
                <span className="flex size-5 shrink-0 items-center justify-center rounded-full border bg-white font-mono text-[10px] text-zinc-500">
                  {i + 1}
                </span>
                <span className="rounded-md border bg-zinc-50 px-2 py-1 text-zinc-700">{hop}</span>
              </li>
            ))}
          </ol>
        </Card>
        <Card className="gap-2.5 px-4 py-4 shadow-xs">
          <div className="text-xs font-medium text-zinc-500">发布流程</div>
          <div className="flex flex-wrap items-center gap-1.5 text-xs text-zinc-600">
            <Kbd>git push</Kbd>
            <ArrowRight className="size-3 text-zinc-300" aria-hidden="true" />
            <span>服务器</span>
            <Kbd>git pull</Kbd>
            <ArrowRight className="size-3 text-zinc-300" aria-hidden="true" />
            <Kbd>systemctl restart</Kbd>
          </div>
          <p className="text-[11px] leading-relaxed text-zinc-500">前端构建产物随仓库提交，服务器只需 Python 环境；密钥保存在服务器本地 .env。</p>
        </Card>
      </div>
    </div>
  )
}
