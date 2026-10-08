import { ChevronRight, MessageSquare } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { tools } from '@/data/tools'

type Props = {
  /** Open the 「工具」 tab at this tool's detail. */
  onOpen: (id: string) => void
  /** Prefill the chat input with the tool's question (never sends). */
  onAsk: (question: string) => void
}

/** Sidebar quick-nav: one compact row per tool. The row opens the detail; 「问 AI」 prefills the chat. */
export function ToolsNav({ onOpen, onAsk }: Props) {
  if (!tools.length) return null
  return (
    <ul className="flex flex-col gap-1.5" aria-label="工具导航">
      {tools.map((tool) => {
        const Icon = tool.icon
        return (
          <li
            key={tool.id}
            data-tool-id={tool.id}
            className="group/tool flex items-center gap-1 rounded-lg border border-zinc-200 bg-white pr-1.5 transition-colors hover:border-zinc-300 hover:bg-zinc-50/80"
          >
            <button
              type="button"
              onClick={() => onOpen(tool.id)}
              className="flex min-w-0 flex-1 items-center gap-2.5 rounded-l-lg py-2 pl-2.5 text-left outline-none focus-visible:ring-2 focus-visible:ring-zinc-950/20"
              aria-label={`查看工具：${tool.name}`}
              title={tool.subtitle}
            >
              <span className="flex size-7 shrink-0 items-center justify-center rounded-md bg-zinc-900 text-white">
                <Icon className="size-3.5" aria-hidden="true" />
              </span>
              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-1.5">
                  <span className="truncate text-[13px] font-semibold text-zinc-900">{tool.short}</span>
                  <span className="shrink-0 rounded border border-zinc-200 bg-zinc-50 px-1 font-mono text-[10px] leading-4 text-zinc-600">{tool.navTag}</span>
                </span>
                <span className="block truncate text-[11px] text-zinc-500">{tool.subtitle}</span>
              </span>
              <ChevronRight className="size-3.5 shrink-0 text-zinc-300 transition-transform group-hover/tool:translate-x-0.5 group-hover/tool:text-zinc-500" aria-hidden="true" />
            </button>
            <Button
              type="button"
              variant="outline"
              size="xs"
              className="h-6 shrink-0 gap-1 rounded-md px-1.5 text-[11px] font-medium text-zinc-600 group-hover/tool:border-zinc-300 group-hover/tool:text-zinc-900"
              aria-label={`问 AI：${tool.ask}`}
              title={tool.ask}
              onClick={() => onAsk(tool.ask)}
            >
              <MessageSquare className="size-3" aria-hidden="true" />
              问 AI
            </Button>
          </li>
        )
      })}
    </ul>
  )
}
