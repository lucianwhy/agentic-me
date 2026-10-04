import type { ReactNode } from 'react'
import { Briefcase, ExternalLink, FolderGit2, GraduationCap, MessageSquare, Wrench, type LucideIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import type { Resume, ResumeEntry } from '@/lib/api'
import { cn } from '@/lib/utils'

type AskFn = (question: string) => void

// Emphasise the quantified bits ("4 类", "7-Agent", "100+", "400+") without touching e.g. "CET-6".
const METRIC = /((?<![A-Za-z-])\d+(?:\+|-Agent)?(?:\s?类)?)/g

function Highlight({ text }: { text: string }) {
  const parts = text.split(METRIC)
  return (
    <>
      {parts.map((p, i) =>
        i % 2 === 1 ? (
          <strong key={i} className="font-semibold text-zinc-900 tabular-nums">
            {p}
          </strong>
        ) : (
          p
        ),
      )}
    </>
  )
}

function Section({ icon: Icon, title, count, children }: { icon: LucideIcon; title: string; count?: number; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-2" aria-label={title}>
      <h2 className="flex items-center gap-1.5 text-xs font-semibold tracking-wide text-zinc-500">
        <Icon className="size-3.5" aria-hidden="true" />
        {title}
        {count !== undefined && <span className="font-normal text-zinc-400 tabular-nums">{count}</span>}
      </h2>
      {children}
    </section>
  )
}

function EntryCard({ id, entry, onAsk }: { id: string; entry: ResumeEntry; onAsk: AskFn }) {
  const subtitle = [entry.organization, entry.role].filter(Boolean).join(' · ')
  return (
    <article
      data-resume-entry
      data-resume-id={id}
      className="group/entry relative cursor-pointer rounded-lg border border-zinc-200 bg-white p-3 transition-colors hover:border-zinc-300 hover:bg-zinc-50/80"
      onClick={() => onAsk(entry.ask)}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="text-[13px] leading-snug font-semibold text-zinc-900">{entry.title}</h3>
          {subtitle && <p className="mt-0.5 text-xs leading-snug text-zinc-600">{subtitle}</p>}
        </div>
        <Button
          type="button"
          variant="outline"
          size="xs"
          className="h-6 shrink-0 gap-1 rounded-md px-1.5 text-[11px] font-medium text-zinc-600 group-hover/entry:border-zinc-300 group-hover/entry:text-zinc-900"
          aria-label={`问 AI：${entry.ask}`}
          title={entry.ask}
          onClick={(e) => {
            e.stopPropagation()
            onAsk(entry.ask)
          }}
        >
          <MessageSquare className="size-3" aria-hidden="true" />
          问 AI
        </Button>
      </div>
      {entry.dates && <p className="mt-1 text-[11px] text-zinc-400 tabular-nums">{entry.dates}</p>}
      {entry.highlights.length > 0 && (
        <ul className="mt-2 flex flex-col gap-1">
          {entry.highlights.map((h) => (
            <li key={h} className="relative pl-3 text-xs leading-relaxed text-zinc-600 before:absolute before:top-[0.6em] before:left-0 before:size-1 before:rounded-full before:bg-zinc-300">
              <Highlight text={h} />
            </li>
          ))}
        </ul>
      )}
      {(entry.tags.length > 0 || entry.link_label) && (
        <div className="mt-2 flex flex-wrap items-center gap-1">
          {entry.tags.map((t) => (
            <span key={t} className="rounded border border-zinc-200 bg-zinc-50 px-1.5 py-px text-[10.5px] text-zinc-600">
              {t}
            </span>
          ))}
          {entry.link_label &&
            (entry.link ? (
              <a
                href={entry.link}
                target="_blank"
                rel="noopener noreferrer"
                onClick={(e) => e.stopPropagation()}
                className="inline-flex items-center gap-0.5 px-1 text-[11px] text-zinc-500 underline-offset-2 hover:text-zinc-900 hover:underline"
              >
                {entry.link_label}
                <ExternalLink className="size-3" aria-hidden="true" />
              </a>
            ) : (
              <span className="px-1 text-[11px] text-zinc-500">{entry.link_label}</span>
            ))}
        </div>
      )}
    </article>
  )
}

/** Structured resume (实习 / 项目 / 技能 / 教育). Every entry can prefill a tailored question in the chat. */
export function ResumeSections({ resume, onAsk, className }: { resume: Resume; onAsk: AskFn; className?: string }) {
  const { internships, projects, skills, education } = resume
  return (
    <div className={cn('flex flex-col gap-5', className)} data-resume>
      {internships.length > 0 && (
        <Section icon={Briefcase} title="实习经历" count={internships.length}>
          {internships.map((e, i) => (
            <EntryCard key={e.organization + e.title} id={e.id ?? `internships-${i}`} entry={e} onAsk={onAsk} />
          ))}
        </Section>
      )}
      {projects.length > 0 && (
        <Section icon={FolderGit2} title="项目经历" count={projects.length}>
          {projects.map((e, i) => (
            <EntryCard key={e.title} id={e.id ?? `projects-${i}`} entry={e} onAsk={onAsk} />
          ))}
        </Section>
      )}
      {skills.length > 0 && (
        <Section icon={Wrench} title="技能">
          <div className="flex flex-col gap-2.5 rounded-lg border border-zinc-200 bg-white p-3">
            {skills.map((g) => (
              <div key={g.name}>
                <p className="mb-1 text-[11px] font-medium text-zinc-500">{g.name}</p>
                <ul className="flex flex-wrap gap-1">
                  {g.items.map((s) => (
                    <li key={s.name}>
                      <button
                        type="button"
                        data-skill
                        title={s.ask}
                        aria-label={`问 AI：${s.ask}`}
                        onClick={() => onAsk(s.ask)}
                        className="group/skill inline-flex items-center gap-1 rounded-md border border-zinc-200 bg-zinc-50 px-1.5 py-0.5 text-[11.5px] font-medium text-zinc-700 transition-colors hover:border-zinc-900 hover:bg-zinc-900 hover:text-zinc-50 focus-visible:ring-2 focus-visible:ring-zinc-950/20 focus-visible:outline-none"
                      >
                        {s.name}
                        <MessageSquare className="hidden size-2.5 group-hover/skill:inline" aria-hidden="true" />
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
            <p className="text-[11px] text-zinc-400">点击技能，问 AI 它在哪些项目里用过</p>
          </div>
        </Section>
      )}
      {education.length > 0 && (
        <Section icon={GraduationCap} title="教育">
          {education.map((e, i) => (
            <EntryCard key={e.organization + e.title} id={e.id ?? `education-${i}`} entry={e} onAsk={onAsk} />
          ))}
        </Section>
      )}
    </div>
  )
}
