import { useState, type FormEvent } from 'react'

import { Markdown } from '@/components/Markdown'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Textarea } from '@/components/ui/textarea'
import { analyzeJobMatch, type Profile } from '@/lib/api'

type State = { kind: 'idle' } | { kind: 'loading' } | { kind: 'done'; analysis: string } | { kind: 'error'; message: string }

export function JobMatchPanel({ profile, ensureAuth }: { profile: Profile; ensureAuth: () => boolean }) {
  const { max_job_text_length: maxLen, min_job_text_length: minLen } = profile.limits
  const [text, setText] = useState('')
  const [state, setState] = useState<State>({ kind: 'idle' })

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault()
    const jd = text.trim()
    if (jd.length < minLen) {
      setState({ kind: 'error', message: `请至少提供 ${minLen} 字的职位描述。` })
      return
    }
    if (!ensureAuth()) {
      setState({ kind: 'error', message: '需要登录' })
      return
    }
    setState({ kind: 'loading' })
    try {
      const data = await analyzeJobMatch(jd)
      setState({ kind: 'done', analysis: data.analysis || '暂无分析结果' })
    } catch (error) {
      console.error('Job matching error:', error)
      setState({ kind: 'error', message: (error instanceof Error && error.message) || '分析失败，请重试。' })
    }
  }

  return (
    <Card className="min-h-0 flex-1 gap-0 py-0 shadow-sm">
      <div className="shrink-0 border-b px-4 py-3 md:px-6">
        <h2 className="text-base font-semibold tracking-tight">岗位匹配</h2>
        <p className="text-sm text-zinc-500">粘贴职位描述，评估与 {profile.name} 的匹配度。</p>
      </div>
      <ScrollArea className="min-h-0 flex-1">
        <div className="px-4 py-5 md:px-6">
          <form onSubmit={onSubmit}>
            <Label htmlFor="job-text" className="mb-1.5">职位描述</Label>
            <Textarea
              id="job-text"
              rows={6}
              value={text}
              maxLength={maxLen}
              required
              placeholder={`把 JD 粘贴到这里（至少 ${minLen} 字）...`}
              onChange={(e) => setText(e.target.value)}
              className="min-h-32 resize-y [field-sizing:fixed] md:text-sm"
            />
            <Button type="submit" className="mt-3 px-4" disabled={state.kind === 'loading'}>
              {state.kind === 'loading' ? '分析中…' : '开始匹配'}
            </Button>
          </form>

          {state.kind !== 'idle' && (
            <div className="mt-5 rounded-lg border border-zinc-200 bg-zinc-50 p-4 text-sm" role="region" aria-label="匹配结果" aria-live="polite">
              {state.kind === 'loading' && <div className="py-4 text-center text-zinc-500">正在分析匹配度，大约需要十几秒。</div>}
              {state.kind === 'error' && (
                <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-red-700">{state.message}</div>
              )}
              {state.kind === 'done' && (
                <>
                  <div className="mb-3 rounded-lg bg-zinc-900 p-3 text-zinc-50">
                    <h3 className="text-base font-bold">岗位匹配评估</h3>
                  </div>
                  <Markdown text={state.analysis} />
                </>
              )}
            </div>
          )}
        </div>
      </ScrollArea>
    </Card>
  )
}
