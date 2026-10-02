import { useState } from 'react'

import { Markdown } from '@/components/Markdown'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import { generateSummary } from '@/lib/api'

type State = { kind: 'idle' } | { kind: 'loading' } | { kind: 'done'; text: string } | { kind: 'error'; message: string }

export function SummaryPanel({ ensureAuth }: { ensureAuth: () => boolean }) {
  const [state, setState] = useState<State>({ kind: 'idle' })

  const run = async () => {
    if (!ensureAuth()) {
      setState({ kind: 'error', message: '需要登录' })
      return
    }
    setState({ kind: 'loading' })
    try {
      const data = await generateSummary()
      setState({ kind: 'done', text: data.summary_md || data.message || '暂无摘要' })
    } catch (error) {
      console.error('Summary error:', error)
      setState({ kind: 'error', message: (error instanceof Error && error.message) || '无法生成摘要。' })
    }
  }

  return (
    <Card className="min-h-0 flex-1 gap-0 py-0 shadow-sm">
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-b px-4 py-3 md:px-6">
        <div className="min-w-0">
          <h2 className="text-base font-semibold tracking-tight">一键摘要</h2>
          <p className="text-sm text-zinc-500">生成一份可转发给招聘方的中文专业摘要。</p>
        </div>
        <Button type="button" onClick={run} disabled={state.kind === 'loading'}>
          生成摘要
        </Button>
      </div>
      <ScrollArea className="min-h-0 flex-1">
        <div className="px-4 py-5 text-sm leading-relaxed md:px-6" role="region" aria-label="摘要" aria-live="polite">
          {state.kind === 'idle' && <span className="text-zinc-400">点击「生成摘要」，大约需要十几秒。</span>}
          {state.kind === 'loading' && <span className="text-zinc-500">正在生成摘要…</span>}
          {state.kind === 'error' && <span>{state.message}</span>}
          {state.kind === 'done' && (
            <>
              <strong className="font-semibold">专业摘要</strong>
              <Markdown text={state.text} className="mt-1" />
            </>
          )}
        </div>
      </ScrollArea>
    </Card>
  )
}
