import { ArrowRight, FolderPlus } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import { Item, ItemActions, ItemContent, ItemDescription, ItemFooter, ItemHeader, ItemMedia, ItemTitle } from '@/components/ui/item'
import type { Project } from '@/data/projects'
import { StatusBadge } from '@/components/projects/StatusBadge'

export function ProjectList({ projects, onOpen }: { projects: Project[]; onOpen: (slug: string) => void }) {
  return (
    <div className="grid gap-3 p-3 sm:grid-cols-2 md:p-6 xl:grid-cols-3" role="list" aria-label="项目列表">
      {projects.map((project) => {
        const Icon = project.icon
        const featured = project.metrics.filter((m) => m.featured)
        const headline = (featured.length ? featured : project.metrics).slice(0, 3)
        return (
          <div key={project.slug} role="listitem" className="flex">
          <Item variant="outline" asChild className="h-full items-start bg-white shadow-xs hover:border-zinc-300 hover:shadow-sm">
            <button type="button" onClick={() => onOpen(project.slug)} className="text-left" aria-label={`查看项目 ${project.name}`}>
              <ItemHeader>
                <div className="flex flex-wrap items-center gap-1.5">
                  {project.statuses.map((s) => (
                    <StatusBadge key={s.label} status={s} />
                  ))}
                </div>
                <span className="text-xs text-zinc-400 tabular-nums">{project.period}</span>
              </ItemHeader>
              <ItemMedia className="size-10 rounded-lg bg-zinc-900 text-white">
                <Icon className="size-5" />
              </ItemMedia>
              <ItemContent>
                <ItemTitle className="text-base">{project.name}</ItemTitle>
                <ItemDescription className="line-clamp-3">{project.tagline}</ItemDescription>
              </ItemContent>
              <ItemActions className="self-center">
                <ArrowRight className="size-4 text-zinc-400 transition-transform group-hover/item:translate-x-0.5" />
              </ItemActions>
              <ItemFooter className="flex-col items-stretch gap-3">
                <div className="grid grid-cols-3 divide-x rounded-md border bg-zinc-50/60">
                  {headline.map((m) => (
                    <div key={m.label} className="px-2.5 py-2">
                      <div className="text-sm font-semibold whitespace-nowrap tabular-nums">
                        {m.value}
                        {m.unit && <span className="ml-0.5 text-xs font-normal text-zinc-500">{m.unit}</span>}
                      </div>
                      <div className="truncate text-[11px] text-zinc-500">{m.short ?? m.label}</div>
                    </div>
                  ))}
                </div>
                <div className="flex flex-wrap gap-1">
                  {project.stack.slice(0, 6).map((t) => (
                    <Badge key={t.name} variant="secondary" className="font-normal">
                      {t.name}
                    </Badge>
                  ))}
                  {project.stack.length > 6 && (
                    <Badge variant="outline" className="font-normal text-zinc-500">
                      +{project.stack.length - 6}
                    </Badge>
                  )}
                </div>
              </ItemFooter>
            </button>
          </Item>
          </div>
        )
      })}

      <Empty className="min-h-56 border border-dashed bg-zinc-50/40" role="listitem">
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <FolderPlus />
          </EmptyMedia>
          <EmptyTitle className="text-sm">更多项目整理中</EmptyTitle>
          <EmptyDescription className="text-xs">其他项目的介绍正在补充，可以先在「对话」里直接提问。</EmptyDescription>
        </EmptyHeader>
      </Empty>
    </div>
  )
}
