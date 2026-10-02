import { useState } from 'react'
import { ChevronLeft } from 'lucide-react'

import { ProjectDetail } from '@/components/projects/ProjectDetail'
import { ProjectList } from '@/components/projects/ProjectList'
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import { projects } from '@/data/projects'

type Props = { model: string; ensureAuth: () => boolean; onAuthRequired: () => void }

export function ProjectsPanel({ model, ensureAuth, onAuthRequired }: Props) {
  const [slug, setSlug] = useState<string | null>(null)
  const project = projects.find((p) => p.slug === slug) ?? null

  return (
    <Card className="min-h-0 flex-1 gap-0 py-0 shadow-sm">
      <div className="flex shrink-0 items-center gap-2 border-b px-3 py-2.5 md:px-6 md:py-3">
        {project && (
          <Button variant="ghost" size="icon-sm" onClick={() => setSlug(null)} aria-label="返回项目列表">
            <ChevronLeft />
          </Button>
        )}
        <div className="min-w-0 flex-1">
          <Breadcrumb>
            <BreadcrumbList>
              <BreadcrumbItem>
                {project ? (
                  <BreadcrumbLink asChild>
                    <button type="button" onClick={() => setSlug(null)}>
                      我的项目
                    </button>
                  </BreadcrumbLink>
                ) : (
                  <BreadcrumbPage className="text-base font-semibold tracking-tight">我的项目</BreadcrumbPage>
                )}
              </BreadcrumbItem>
              {project && (
                <>
                  <BreadcrumbSeparator />
                  <BreadcrumbItem>
                    <BreadcrumbPage className="font-medium">{project.name}</BreadcrumbPage>
                  </BreadcrumbItem>
                </>
              )}
            </BreadcrumbList>
          </Breadcrumb>
          {!project && <p className="text-sm text-zinc-500">做过的项目，点开看架构、指标与在线演示。</p>}
        </div>
      </div>
      {/* key: reset scroll position when switching between list and detail */}
      <ScrollArea key={slug ?? 'list'} className="min-h-0 flex-1">
        {project ? (
          <ProjectDetail project={project} model={model} ensureAuth={ensureAuth} onAuthRequired={onAuthRequired} />
        ) : (
          <ProjectList projects={projects} onOpen={setSlug} />
        )}
      </ScrollArea>
    </Card>
  )
}
