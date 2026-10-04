/**
 * Inline citations in chat answers.
 *
 * The backend numbers retrieved chunks [1]..[n] in the order they are later sent as `sources`
 * in the done event, so a marker [n] in the answer refers to sources[n - 1].
 */
import type { Element, ElementContent, Root, RootContent, Text } from 'hast'

import type { Resume, Source } from '@/lib/api'

/** [1] · [1,2] · [1，2] · [1、2] (at most two digits per number). */
const MARKER_SRC = String.raw`\[(\d{1,2}(?:\s*[,，、]\s*\d{1,2})*)\]`
/** Sentence ends. A "." only counts before whitespace/end so "Node.js" and "3.5" stay intact. */
const BOUNDARY_SRC = String.raw`[。！？；!?;]|\.(?=\s|$)`
const TOKEN = new RegExp(`${MARKER_SRC}|(${BOUNDARY_SRC})`, 'g')
const MARKER_GLOBAL = new RegExp(String.raw`\s?${MARKER_SRC}`, 'g')
/** A marker still being streamed at the very end: "[", "[1", "[1,", "[1, 2". */
const PARTIAL_TAIL = /\[\d{0,2}(?:\s*[,，、]\s*\d{0,2})*$/

/** Drop an unfinished trailing marker so streaming never flashes "[1". */
export const stripPartialMarker = (text: string) => text.replace(PARTIAL_TAIL, '')

/** Remove all markers (copying an answer, or sending it back as chat history). */
export const stripCitations = (text: string) => text.replace(MARKER_GLOBAL, '')

/**
 * Valid, de-duplicated citation numbers inside one marker. `count` = number of sources;
 * null means "not known yet" (streaming before the server said how many chunks it found).
 */
export function parseCitationNumbers(inner: string, count: number | null): number[] {
  const max = count ?? 20
  const out: number[] = []
  for (const part of inner.split(/[,，、]/)) {
    const n = Number(part.trim())
    if (Number.isInteger(n) && n >= 1 && n <= max && !out.includes(n)) out.push(n)
  }
  return out
}

/**
 * Safety net for over-citing: sentences that only say something is missing from the resume
 * ("简历里没有写到…", "未说明…", "资料不足") never get markers. Deliberately narrow.
 */
const MISSING_INFO = /(没有|未|并未|没)(具体|明确)?(写到|写明|提到|提及|说明|提供|列出|涉及|量化)|资料(不足|有限)|无法(确认|判断)/
export const isMissingInfoSentence = (sentence: string) => MISSING_INFO.test(sentence)

const HEADING = new Set(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])

/** Block-level tags end a sentence and are processed recursively; their contents never merge with siblings. */
const BLOCK = new Set(['p', 'li', 'ul', 'ol', 'blockquote', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'table', 'thead', 'tbody', 'tr', 'td', 'th', 'hr', 'div'])
const SKIP = new Set(['pre', 'code'])

const text = (value: string): Text => ({ type: 'text', value })
const textOf = (nodes: (RootContent | ElementContent)[]): string =>
  nodes.map((n) => (n.type === 'text' ? n.value : n.type === 'element' ? textOf(n.children) : '')).join('')

/** Consecutive markers stay together on one line. */
const markerGroup = (children: Element[]): Element => ({ type: 'element', tagName: 'span', properties: { className: ['cite-markers'] }, children })

function markerNode(n: number, sentence: string): Element {
  return { type: 'element', tagName: 'sup', properties: { dataCiteRef: String(n), dataSentence: sentence }, children: [text(`[${n}]`)] }
}

/** Replace markers inside an inline element (e.g. **bold[1]**) and return the numbers found. */
function convertInline(el: Element, count: number | null): number[] {
  const found: number[] = []
  const next: ElementContent[] = []
  for (const child of el.children) {
    if (child.type === 'text') {
      let last = 0
      for (const m of child.value.matchAll(new RegExp(MARKER_SRC, 'g'))) {
        if (m.index > last) next.push(text(child.value.slice(last, m.index)))
        last = m.index + m[0].length
        for (const n of parseCitationNumbers(m[1], count)) {
          found.push(n)
          next.push(markerNode(n, textOf(el.children)))
        }
      }
      if (last < child.value.length) next.push(text(child.value.slice(last)))
    } else if (child.type === 'element' && !SKIP.has(child.tagName)) {
      found.push(...convertInline(child, count))
      next.push(child)
    } else {
      next.push(child)
    }
  }
  el.children = next
  return found
}

function processContainer(node: Root | Element, count: number | null) {
  const out: (RootContent | ElementContent)[] = []
  let buffer: ElementContent[] = []
  let pendingEnd = false // buffer ends with sentence punctuation; a marker may still follow it
  let lastSentence: Element | null = null // the sentence the latest marker belongs to
  let lastGroup: Element | null = null // ...and the marker group rendered after it

  const flush = () => {
    out.push(...buffer)
    buffer = []
    pendingEnd = false
    lastSentence = null
    lastGroup = null
  }

  const cite = (nums: number[]) => {
    if (!nums.length) return // invalid / out of range: drop the marker
    if (isMissingInfoSentence(textOf(buffer))) return // "简历里没有写到…[2]": drop
    if (!buffer.some((n) => textOf([n]).trim())) {
      // "[1][2]" or a marker right after another one: extend the previous sentence.
      out.push(...buffer)
      buffer = []
      if (lastSentence && lastGroup) {
        const prev = String(lastSentence.properties.dataCite).split(',').map(Number)
        const added = nums.filter((n) => !prev.includes(n))
        lastSentence.properties.dataCite = [...prev, ...added].join(',')
        const sentence = textOf(lastSentence.children)
        lastGroup.children.push(...added.map((n) => markerNode(n, sentence)))
      }
      return
    }
    // Keep leading whitespace outside the underline.
    const first = buffer[0]
    if (first.type === 'text' && /^\s/.test(first.value)) {
      const trimmed = first.value.trimStart()
      out.push(text(first.value.slice(0, first.value.length - trimmed.length)))
      if (trimmed) buffer[0] = text(trimmed)
      else buffer.shift()
    }
    const sentence: Element = { type: 'element', tagName: 'span', properties: { dataCite: nums.join(',') }, children: buffer }
    const sentenceText = textOf(buffer)
    const group = markerGroup(nums.map((n) => markerNode(n, sentenceText)))
    out.push(sentence, group)
    buffer = []
    pendingEnd = false
    lastSentence = sentence
    lastGroup = group
  }

  for (const child of node.children) {
    if (child.type === 'element' && SKIP.has(child.tagName)) {
      if (pendingEnd) flush()
      buffer.push(child)
    } else if (child.type === 'element' && (BLOCK.has(child.tagName) || child.tagName === 'br')) {
      flush()
      // Headings never carry citations (count 0 drops every marker inside).
      if (BLOCK.has(child.tagName)) processContainer(child, HEADING.has(child.tagName) ? 0 : count)
      out.push(child)
    } else if (child.type === 'element') {
      if (pendingEnd) flush()
      const nums = convertInline(child, count)
      buffer.push(child)
      if (nums.length) {
        const sentence: Element = { type: 'element', tagName: 'span', properties: { dataCite: nums.join(',') }, children: buffer }
        out.push(sentence)
        buffer = []
        lastSentence = sentence
        lastGroup = null
      }
    } else if (child.type === 'text') {
      const value = child.value
      let last = 0
      const pushPlain = (s: string) => {
        if (!s) return
        if (pendingEnd && s.trim()) flush()
        else if (s.trim()) {
          lastSentence = null
          lastGroup = null
        }
        buffer.push(text(s))
      }
      for (const m of value.matchAll(TOKEN)) {
        pushPlain(value.slice(last, m.index))
        last = m.index + m[0].length
        if (m[1] !== undefined) {
          cite(parseCitationNumbers(m[1], count))
        } else {
          if (pendingEnd) flush() // "。。" — keep consecutive punctuation plain
          buffer.push(text(m[0]))
          pendingEnd = true
        }
      }
      pushPlain(value.slice(last))
    } else {
      buffer.push(child as ElementContent)
    }
  }
  flush()
  node.children = out as typeof node.children
}

/**
 * rehype plugin: turn "sentence[1]" into `<span data-cite="1">sentence</span><sup data-cite-ref="1">[1]</sup>`.
 * Out-of-range / invalid numbers are dropped; code blocks are left alone.
 */
export function rehypeCitations(options: { count: number | null }) {
  return (tree: Root) => processContainer(tree, options.count)
}

// ---------------------------------------------------------------------------
// Source display helpers (shared by the 参考来源 list and the marker hover card)

export function sourceName(s: Source) {
  const m = s.metadata ?? {}
  const src = String(m.source ?? '')
  if (src === 'cv') {
    const page = m.page_label ?? (typeof m.page === 'number' ? m.page + 1 : undefined)
    return page ? `简历 PDF · 第 ${page} 页` : '简历 PDF'
  }
  if (src === 'about_me') return '关于我'
  return src || '资料'
}

/** Plain-text preview: drop markdown markers so "## 项目 ###" reads cleanly. */
export const snippet = (value: string) =>
  value
    .replace(/[#*`>|]+/g, ' ')
    .replace(/^\s*-\s+/gm, '')
    .replace(/\s+/g, ' ')
    .trim()

// ---------------------------------------------------------------------------
// Chunk → left-column resume entry

const norm = (s: string) => s.replace(/\s+/g, '').toLowerCase()

const bigrams = (v: string) => {
  const out = new Set<string>()
  for (let i = 0; i < v.length - 1; i++) out.add(v.slice(i, i + 2))
  return out
}

type Candidate = { id: string; e: Resume['internships'][number] }

const allEntries = (resume: Resume): Candidate[] =>
  (['internships', 'projects', 'education'] as const).flatMap((kind) => resume[kind].map((e, i) => ({ id: e.id ?? `${kind}-${i}`, e })))

const entryKeys = (e: Candidate['e']) =>
  [...new Set([e.title, e.title.split(/\s+[-·]\s+/)[0], e.organization, e.organization.replace(/(科技)?有限公司$/, '')].map(norm))].filter((k) => k.length >= 2)

/** How strongly the cited sentence points at an entry: names it mentions, tags, wording shared with its highlights. */
function sentenceScore(e: Candidate['e'], s: string, sGrams: Set<string>) {
  const body = bigrams(norm([e.title, e.organization, ...e.highlights, ...e.tags].join('')))
  let shared = 0
  for (const g of sGrams) if (body.has(g)) shared++
  const overlap = sGrams.size ? shared / sGrams.size : 0
  return entryKeys(e).filter((k) => s.includes(k)).length * 10 + e.tags.filter((t) => s.includes(norm(t))).length + overlap * 10
}

/**
 * Which sidebar card (data-resume-id) a cited chunk is about.
 *
 * `ids` = the server's `resume_entry_ids` for the chunk (from the full chunk text, ordered by how
 * much of the chunk each entry covers). One id → that card. Several → the cited sentence picks;
 * if it doesn't clearly favour one, the server's first id wins. Without ids (older backend) fall
 * back to matching names in the (truncated) chunk text, and stay silent when ambiguous.
 */
export function matchResumeEntry(resume: Resume | undefined, chunk: string, sentence: string, ids?: string[]): string | null {
  if (!resume) return null
  const s = norm(sentence)
  const sGrams = bigrams(s)
  const entries = allEntries(resume)

  if (ids) {
    const known = ids.filter((id) => entries.some((c) => c.id === id))
    if (known.length <= 1) return known[0] ?? null
    const scored = known.map((id) => ({ id, score: sentenceScore(entries.find((c) => c.id === id)!.e, s, sGrams) }))
    const best = [...scored].sort((a, b) => b.score - a.score)
    return best[0].score >= 2 && best[0].score - best[1].score >= 1.5 ? best[0].id : known[0]
  }

  if (!chunk) return null
  const c = norm(chunk)
  const scored = entries
    .filter(({ e }) => entryKeys(e).some((k) => c.includes(k)))
    .map(({ id, e }) => ({ id, score: sentenceScore(e, s, sGrams) }))
  if (!scored.length) return null
  if (scored.length === 1) return scored[0].id
  scored.sort((a, b) => b.score - a.score)
  return scored[0].score >= 2 && scored[0].score - scored[1].score >= 1.5 ? scored[0].id : null
}

// ---------------------------------------------------------------------------
// Scroll + flash without disturbing other scroll containers

function scrollParent(el: HTMLElement): HTMLElement | null {
  for (let p = el.parentElement; p; p = p.parentElement) {
    const oy = getComputedStyle(p).overflowY
    if ((oy === 'auto' || oy === 'scroll') && p.scrollHeight > p.clientHeight) return p
  }
  return null
}

/** Scroll only the nearest scrollable ancestor so `el` is (comfortably) in view. */
export function scrollIntoNearest(el: HTMLElement) {
  const parent = scrollParent(el)
  if (!parent) return
  const pr = parent.getBoundingClientRect()
  const r = el.getBoundingClientRect()
  const margin = 12
  let delta = 0
  if (r.top < pr.top + margin) delta = r.top - pr.top - margin
  else if (r.bottom > pr.bottom - margin) delta = Math.min(r.bottom - pr.bottom + margin, r.top - pr.top - margin)
  if (delta) parent.scrollTo({ top: parent.scrollTop + delta, behavior: 'smooth' })
}

/** Brief amber highlight that fades back to the element's own style. */
export function flash(el: HTMLElement) {
  el.animate(
    [
      { offset: 0, backgroundColor: 'rgb(254 243 199)', boxShadow: '0 0 0 2px rgb(251 191 36 / 0.7)' },
      { offset: 0.55, backgroundColor: 'rgb(254 243 199)', boxShadow: '0 0 0 2px rgb(251 191 36 / 0.7)' },
    ],
    { duration: 2000, easing: 'ease-out' },
  )
}

/** Highlight a sidebar entry if it is on screen (on mobile the closed 简历 drawer is left alone). */
export function flashResumeEntry(id: string) {
  const el = document.querySelector<HTMLElement>(`[data-resume-id="${id}"]`)
  if (!el || el.getClientRects().length === 0) return false
  scrollIntoNearest(el)
  flash(el)
  return true
}
