import { ArrowRight, ChevronLeft, PackagePlus } from 'lucide-react'

import { ToolDetail } from '@/components/tools/ToolDetail'
import { Badge } from '@/components/ui/badge'
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
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty'
import { Item, ItemActions, ItemContent, ItemDescription, ItemFooter, ItemMedia, ItemTitle } from '@/components/ui/item'
import { ScrollArea } from '@/components/ui/scroll-area'
import { tools, type Tool } from '@/data/tools'

type Props = {
  /** Open tool (null = list). Controlled by App so the sidebar quick-nav can open a tool. */
  toolId: string | null
  onSelect: (id: string | null) => void
  /** Prefill the chat input (switches to 对话; never sends). */
  onAsk: (question: string) => void
  ensureAuth: () => boolean
  onAuthRequired: () => void
  /** False while invite-code auth is on and the visitor has no session. */
  authed: boolean
}

export function ToolsPanel({ toolId, onSelect, onAsk, ensureAuth, onAuthRequired, authed }: Props) {
  const tool = tools.find((t) => t.id === toolId) ?? null

  return (
    <Card className="min-h-0 flex-1 gap-0 py-0 shadow-sm" data-tools-panel>
      <div className="flex shrink-0 items-center gap-2 border-b px-3 py-2.5 md:px-6 md:py-3">
        {tool && (
          <Button variant="ghost" size="icon-sm" onClick={() => onSelect(null)} aria-label="返回工具列表">
            <ChevronLeft />
          </Button>
        )}
        <div className="min-w-0 flex-1">
          <Breadcrumb>
            <BreadcrumbList>
              <BreadcrumbItem>
                {tool ? (
                  <BreadcrumbLink asChild>
                    <button type="button" onClick={() => onSelect(null)}>
                      工具
                    </button>
                  </BreadcrumbLink>
                ) : (
                  <BreadcrumbPage className="text-base font-semibold tracking-tight">工具</BreadcrumbPage>
                )}
              </BreadcrumbItem>
              {tool && (
                <>
                  <BreadcrumbSeparator />
                  <BreadcrumbItem>
                    <BreadcrumbPage className="font-medium">{tool.name}</BreadcrumbPage>
                  </BreadcrumbItem>
                </>
              )}
            </BreadcrumbList>
          </Breadcrumb>
          {!tool && <p className="text-sm text-zinc-500">我自己做的工具：解决什么问题、架构、遇到的问题和学到的东西。</p>}
        </div>
      </div>
      {/* key: every open starts at the top of that tool's detail */}
      <ScrollArea key={tool?.id ?? 'list'} className="min-h-0 flex-1">
        {tool ? (
          <ToolDetail tool={tool} onAsk={onAsk} ensureAuth={ensureAuth} onAuthRequired={onAuthRequired} authed={authed} />
        ) : (
          <ToolList onOpen={onSelect} />
        )}
      </ScrollArea>
    </Card>
  )
}

function ToolList({ onOpen }: { onOpen: (id: string) => void }) {
  return (
    <div className="grid gap-3 p-3 sm:grid-cols-2 md:p-6 xl:grid-cols-3" role="list" aria-label="工具列表">
      {tools.map((tool) => (
        <ToolCard key={tool.id} tool={tool} onOpen={onOpen} />
      ))}
      <Empty className="min-h-48 border border-dashed bg-zinc-50/40" role="listitem">
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <PackagePlus />
          </EmptyMedia>
          <EmptyTitle className="text-sm">更多工具整理中</EmptyTitle>
          <EmptyDescription className="text-xs">MCP、IDE 相关的其他工具会陆续补充。</EmptyDescription>
        </EmptyHeader>
      </Empty>
    </div>
  )
}

function ToolCard({ tool, onOpen }: { tool: Tool; onOpen: (id: string) => void }) {
  const Icon = tool.icon
  return (
    <div role="listitem" className="flex">
      <Item variant="outline" asChild className="h-full items-start bg-white shadow-xs hover:border-zinc-300 hover:shadow-sm">
        <button type="button" onClick={() => onOpen(tool.id)} className="text-left" aria-label={`查看工具 ${tool.name}`}>
          <ItemMedia className="size-10 rounded-lg bg-zinc-900 text-white">
            <Icon className="size-5" />
          </ItemMedia>
          <ItemContent>
            <ItemTitle className="text-base">{tool.name}</ItemTitle>
            <ItemDescription>{tool.navSubtitle}</ItemDescription>
          </ItemContent>
          <ItemActions className="self-center">
            <ArrowRight className="size-4 text-zinc-400 transition-transform group-hover/item:translate-x-0.5" />
          </ItemActions>
          <ItemFooter className="flex-col items-stretch gap-3">
            <p className="line-clamp-3 text-xs leading-relaxed text-zinc-500">{tool.oneLiner}</p>
            <div className="flex flex-wrap gap-1">
              {tool.keywords.map((k) => (
                <Badge key={k.label} variant="secondary" className="font-normal">
                  {k.label}
                </Badge>
              ))}
            </div>
          </ItemFooter>
        </button>
      </Item>
    </div>
  )
}
