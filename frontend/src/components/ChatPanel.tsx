import { useCallback, useEffect, useImperativeHandle, useRef, useState, type FormEvent, type KeyboardEvent, type Ref } from 'react'
import { MessageSquare } from 'lucide-react'

import { AssistantMessage, type AssistantMsg } from '@/components/AssistantMessage'
import { Markdown } from '@/components/Markdown'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import { AuthRequiredError, streamChat, type ChatTurn, type Profile } from '@/lib/api'
import { stripCitations } from '@/lib/citations'
import type { ModelOption } from '@/lib/models'

type UserMsg = { id: number; role: 'user'; text: string }
type Message = UserMsg | AssistantMsg

type Props = {
  profile: Profile
  model: string
  /** Switcher options from GET /models; null while loading. */
  models: ModelOption[] | null
  onModelChange: (model: string) => void
  /** Returns false (and opens the login dialog) when auth is enabled and the visitor is not logged in. */
  ensureAuth: () => boolean
  onAuthRequired: () => void
  /** Imperative handle so other parts of the page can prefill the input. */
  ref?: Ref<ChatPanelHandle>
}

export type ChatPanelHandle = {
  /** Put a question in the input (focused, cursor at end). Never sends — the visitor presses 发送. */
  prefill: (text: string) => void
}

let nextId = 1
const HISTORY_TURNS = 6

/** Recent completed Q&A pairs (notices, errors and in-flight answers are skipped). */
function buildHistory(messages: Message[]): ChatTurn[] {
  const turns: ChatTurn[] = []
  for (let i = 0; i < messages.length - 1; i++) {
    const q = messages[i]
    const a = messages[i + 1]
    if (q.role === 'user' && a.role === 'assistant' && a.phase === 'done' && a.sources !== undefined && a.text) {
      turns.push({ role: 'user', content: q.text }, { role: 'assistant', content: stripCitations(a.text) })
    }
  }
  return turns.slice(-HISTORY_TURNS)
}

export function ChatPanel({ profile, model, models, onModelChange, ensureAuth, onAuthRequired, ref }: Props) {
  const { max_query_length: maxLen, rate_limit_ms: rateLimitMs } = profile.limits
  const [messages, setMessages] = useState<Message[]>([])
  const messagesRef = useRef<Message[]>([])
  useEffect(() => {
    messagesRef.current = messages
  }, [messages])
  const [query, setQuery] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [rateLimited, setRateLimited] = useState(false)

  const lastRequestRef = useRef(0)
  const abortRef = useRef<AbortController | null>(null)
  const scrollRootRef = useRef<HTMLDivElement>(null)
  const rateTimerRef = useRef<number | undefined>(undefined)
  const formRef = useRef<HTMLFormElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  /** Fill the input with a question and focus it with the cursor at the end — does not send. */
  const fillInput = useCallback((text: string) => {
    setQuery(text)
    // Wait a frame so the (possibly just re-shown) chat tab is visible and the value is committed.
    requestAnimationFrame(() => {
      const el = inputRef.current
      if (!el) return
      el.focus({ preventScroll: true })
      el.setSelectionRange(el.value.length, el.value.length)
      el.scrollTop = el.scrollHeight
    })
  }, [])

  useImperativeHandle(ref, () => ({ prefill: fillInput }), [fillInput])

  const isEmpty = messages.length === 0

  // Keep the newest message in view while streaming.
  useEffect(() => {
    const viewport = scrollRootRef.current?.querySelector<HTMLElement>('[data-slot="scroll-area-viewport"]')
    if (viewport) viewport.scrollTop = viewport.scrollHeight
  }, [messages])

  useEffect(() => () => window.clearTimeout(rateTimerRef.current), [])

  const appendUser = (text: string) => setMessages((prev) => [...prev, { id: nextId++, role: 'user', text }])
  /** Assistant bubble; `phase: 'done'` for plain notices (validation, login). */
  const appendAssistant = (init: Omit<AssistantMsg, 'id' | 'role'>) => {
    const id = nextId++
    setMessages((prev) => [...prev, { id, role: 'assistant', ...init }])
    return id
  }
  const patchAssistant = (id: number, patch: Partial<AssistantMsg>) =>
    setMessages((prev) => prev.map((m) => (m.id === id && m.role === 'assistant' ? { ...m, ...patch } : m)))

  const showRateLimit = () => {
    setRateLimited(true)
    window.clearTimeout(rateTimerRef.current)
    rateTimerRef.current = window.setTimeout(() => setRateLimited(false), 3000)
  }

  const send = useCallback(
    async (raw: string) => {
      const text = raw.trim()
      if (!text) {
        appendAssistant({ text: '问题不能为空', phase: 'done' })
        return
      }
      if (text.length > maxLen) {
        appendAssistant({ text: `问题过长，请控制在 ${maxLen} 字以内。`, phase: 'done' })
        return
      }
      const now = Date.now()
      if (now - lastRequestRef.current < rateLimitMs) {
        showRateLimit()
        return
      }
      if (submitting) return // one stream at a time
      lastRequestRef.current = now

      const history = buildHistory(messagesRef.current)
      setSubmitting(true)
      appendUser(text)
      setQuery('')
      if (!ensureAuth()) {
        appendAssistant({ text: '请先登录。', phase: 'done' })
        setSubmitting(false)
        return
      }

      // Show the assistant bubble immediately with a progressing status line + skeleton.
      const bubbleId = appendAssistant({ text: '', phase: 'retrieving', startedAt: Date.now() })
      const controller = new AbortController()
      abortRef.current = controller
      let full = ''

      try {
        await streamChat(text, model, {
          signal: controller.signal,
          onStatus: (stage, info) => {
            if (controller.signal.aborted || full) return
            patchAssistant(bubbleId, { phase: stage, realStages: true, sourceCount: info.source_count })
          },
          onToken: (chunk) => {
            if (controller.signal.aborted) return
            full += chunk
            patchAssistant(bubbleId, { text: full, phase: 'streaming' })
          },
          onDone: (sources) => {
            if (controller.signal.aborted) return
            patchAssistant(bubbleId, { text: full || '暂无回答', phase: 'done', sources })
          },
          onError: (message) => {
            if (controller.signal.aborted) return
            patchAssistant(bubbleId, { text: message, phase: 'error' })
          },
        }, history)
      } catch (error) {
        if (controller.signal.aborted) return
        console.error('Query error:', error)
        let message = error instanceof Error && error.message ? error.message : '出错了，请重试。'
        if (error instanceof AuthRequiredError) {
          message = '请先登录。'
          onAuthRequired()
        }
        patchAssistant(bubbleId, { text: message, phase: 'error' })
      } finally {
        if (abortRef.current === controller) {
          abortRef.current = null
          setSubmitting(false)
        }
      }
    },
    [submitting, maxLen, rateLimitMs, model, ensureAuth, onAuthRequired],
  )

  const clear = () => {
    abortRef.current?.abort()
    abortRef.current = null
    setSubmitting(false)
    setMessages([])
  }

  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    void send(query)
  }

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    // Enter sends, Shift+Enter inserts a newline; ignore Enter while an IME is composing.
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      formRef.current?.requestSubmit() // goes through native `required` validation like the legacy page
    }
  }

  return (
    <Card className="min-h-0 flex-1 gap-0 py-0 shadow-sm">
      <div className="flex shrink-0 items-center justify-between gap-3 border-b px-4 py-3 md:px-6">
        <div className="flex min-w-0 items-center gap-2">
          <h2 className="text-base font-semibold tracking-tight">对话</h2>
          <Badge variant="outline" className="rounded-md text-zinc-600">仅基于简历回答</Badge>
        </div>
        <Button type="button" variant="ghost" size="sm" className="text-zinc-500" onClick={clear}>
          清空记录
        </Button>
      </div>

      {isEmpty ? (
        <div className="flex min-h-0 flex-1 overflow-y-auto px-4 py-5 md:px-6" role="log" aria-live="polite" aria-label="对话记录">
          <div className="m-auto flex flex-col items-center gap-4 py-6 text-center">
            <div className="flex size-11 items-center justify-center rounded-full border border-zinc-200 bg-zinc-50 text-zinc-500" aria-hidden="true">
              <MessageSquare className="size-5" />
            </div>
            <p className="max-w-md text-sm text-zinc-500">{profile.welcome}</p>
            <SuggestedQuestions profile={profile} onPick={fillInput} />
          </div>
        </div>
      ) : (
        <ScrollArea ref={scrollRootRef} className="min-h-0 flex-1">
          <div className="flex flex-col gap-5 px-4 py-5 md:px-6" role="log" aria-live="polite" aria-label="对话记录">
            {messages.map((m) =>
              m.role === 'user' ? (
                <div
                  key={m.id}
                  data-role="user"
                  className="ml-auto w-fit max-w-[85%] rounded-2xl rounded-br-sm bg-zinc-900 px-4 py-2.5 text-zinc-50 shadow-sm"
                >
                  <Markdown text={m.text} className="[&_strong]:text-zinc-50 [&_a]:text-zinc-50" />
                </div>
              ) : (
                <AssistantMessage key={m.id} msg={m} avatarUrl={profile.avatar_url} name={profile.name} resume={profile.resume} />
              ),
            )}
          </div>
        </ScrollArea>
      )}

      <div className="shrink-0 rounded-b-xl border-t bg-zinc-50/60 p-3 md:p-4">
        <form ref={formRef} onSubmit={onSubmit}>
          <label htmlFor="chat-query" className="sr-only">输入问题</label>
          <div className="rounded-xl border border-zinc-200 bg-white shadow-sm transition focus-within:border-zinc-400 focus-within:ring-2 focus-within:ring-zinc-950/10">
            <Textarea
              id="chat-query"
              ref={inputRef}
              rows={2}
              value={query}
              maxLength={maxLen}
              required
              placeholder={profile.input_placeholder}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={onKeyDown}
              className="max-h-40 min-h-[60px] resize-none rounded-b-none border-0 bg-transparent px-3.5 pt-3 pb-1 shadow-none focus-visible:ring-0 md:text-sm dark:bg-transparent"
            />
            <div className="flex items-center justify-between gap-2 px-2.5 pt-1 pb-2.5">
              <Select value={model} onValueChange={onModelChange} disabled={!models?.length}>
                <SelectTrigger size="sm" className="h-8 text-xs font-medium text-zinc-700" aria-label="选择对话模型">
                  <SelectValue placeholder={models ? '默认模型' : '加载中…'} />
                </SelectTrigger>
                <SelectContent>
                  {(models ?? []).map((m) => (
                    <SelectItem key={m.id} value={m.id} className="text-xs">
                      {m.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Button type="submit" size="sm" className="min-w-[4.5rem] px-4" disabled={submitting}>
                {submitting ? '生成中…' : '发送'}
              </Button>
            </div>
          </div>
        </form>
        <p className="mt-2 hidden px-1 text-xs text-zinc-400 sm:block">Enter 发送，Shift+Enter 换行。最多 {maxLen} 字。</p>
        {rateLimited && (
          <div className="mt-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800" role="alert">
            发送太频繁，请稍后再试。
          </div>
        )}
      </div>
    </Card>
  )
}

const CHIP = 'h-auto min-h-8 rounded-full px-3 py-1.5 text-left font-normal whitespace-normal text-zinc-700'

/** Empty-chat suggestions: category tabs when the backend sends groups, flat chips otherwise. Clicking fills the input. */
function SuggestedQuestions({ profile, onPick }: { profile: Profile; onPick: (q: string) => void }) {
  const groups = profile.suggested_question_groups ?? []
  const chip = (q: { label: string; question: string }) => (
    <Button key={q.label} type="button" variant="outline" size="sm" className={CHIP} data-q={q.question} title={q.question} onClick={() => onPick(q.question)}>
      {q.label}
    </Button>
  )
  if (!groups.length) {
    return <div className="flex max-w-xl flex-wrap justify-center gap-2">{profile.suggested_questions.map(chip)}</div>
  }
  return (
    <Tabs defaultValue={groups[0].id} className="w-full max-w-xl items-center gap-3" data-question-groups>
      <TabsList aria-label="推荐问题分类">
        {groups.map((g) => (
          <TabsTrigger key={g.id} value={g.id} className="px-3 text-[13px]">
            {g.label}
          </TabsTrigger>
        ))}
      </TabsList>
      {groups.map((g) => (
        <TabsContent key={g.id} value={g.id} className="mt-0 flex min-h-[5.5rem] flex-wrap content-start justify-center gap-2">
          {g.questions.map(chip)}
        </TabsContent>
      ))}
      <p className="text-xs text-zinc-400">点击问题会填入输入框，可修改后再发送</p>
    </Tabs>
  )
}
