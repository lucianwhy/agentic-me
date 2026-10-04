import type { Element, ElementContent, Root } from 'hast'
import ReactMarkdown, { type Components, type Options } from 'react-markdown'
import remarkBreaks from 'remark-breaks'

import { CiteMarker, CiteSentence } from '@/components/Citations'
import { rehypeCitations, stripPartialMarker } from '@/lib/citations'
import { cn } from '@/lib/utils'

/** Legacy answers sometimes contain literal "\n" sequences; turn them into real newlines. */
const normalize = (raw: string) =>
  String(raw ?? '')
    .replace(/\\n/g, '\n')
    // "**标签：**正文": CommonMark won't close bold when full-width punctuation precedes the closing
    // ** and a CJK character follows, so the asterisks would show. Move the punctuation outside.
    .replace(/\*\*([^*\n]+?)([：:，,；;、])\*\*(?=\S)/g, '**$1**$2')

/** rehype plugin: append a caret <span> right after the last text node (works inside nested lists, bold, etc.). */
function rehypeCaret() {
  return (tree: Root) => {
    let parent: Element | Root = tree
    // Walk down the last child chain to the deepest last element that holds content.
    for (;;) {
      const kids: Root['children'] = parent.children.filter((c) => !(c.type === 'text' && !c.value.trim()))
      const last: Root['children'][number] | undefined = kids[kids.length - 1]
      if (!last || last.type !== 'element' || last.tagName === 'br') break
      parent = last
    }
    const caret: ElementContent = { type: 'element', tagName: 'span', properties: { className: ['md-caret'], ariaHidden: 'true' }, children: [] }
    ;(parent.children as ElementContent[]).push(caret)
  }
}

const components: Components = {
  // Citation nodes produced by rehypeCitations (other spans/sups render as usual).
  span: ({ node: _node, ...props }) => {
    const cite = (props as Record<string, unknown>)['data-cite']
    return cite !== undefined ? <CiteSentence cite={cite}>{props.children}</CiteSentence> : <span {...props} />
  },
  sup: ({ node: _node, ...props }) => {
    const p = props as Record<string, unknown>
    return p['data-cite-ref'] !== undefined ? <CiteMarker refNum={p['data-cite-ref']} sentence={p['data-sentence']} /> : <sup {...props} />
  },
  p: ({ children }) => <p className="my-2 first:mt-0 last:mb-0">{children}</p>,
  ul: ({ children }) => <ul className="my-2 ml-5 list-disc space-y-1 marker:text-zinc-400 first:mt-0 last:mb-0">{children}</ul>,
  ol: ({ children }) => <ol className="my-2 ml-5 list-decimal space-y-1 marker:text-zinc-400 first:mt-0 last:mb-0">{children}</ol>,
  li: ({ children }) => <li className="pl-0.5 [&>ol]:my-1 [&>ul]:my-1">{children}</li>,
  strong: ({ children }) => <strong className="font-semibold text-zinc-950">{children}</strong>,
  em: ({ children }) => <em className="italic">{children}</em>,
  h1: ({ children }) => <h3 className="mt-4 mb-2 border-b border-zinc-200 pb-1 text-base font-semibold tracking-tight first:mt-0">{children}</h3>,
  h2: ({ children }) => <h3 className="mt-4 mb-2 border-b border-zinc-200 pb-1 text-base font-semibold tracking-tight first:mt-0">{children}</h3>,
  h3: ({ children }) => <h4 className="mt-3 mb-1.5 text-sm font-semibold first:mt-0">{children}</h4>,
  h4: ({ children }) => <h4 className="mt-3 mb-1.5 text-sm font-semibold first:mt-0">{children}</h4>,
  blockquote: ({ children }) => <blockquote className="my-2 border-l-2 border-zinc-300 pl-3 text-zinc-600">{children}</blockquote>,
  hr: () => <hr className="my-3 border-zinc-200" />,
  a: ({ children, href }) => (
    <a href={href} target="_blank" rel="noopener noreferrer" className="font-medium text-zinc-950 underline decoration-zinc-400 underline-offset-4 hover:decoration-zinc-900">
      {children}
    </a>
  ),
  pre: ({ children }) => (
    <pre className="my-2 overflow-x-auto rounded-lg border border-zinc-200 bg-white p-3 font-mono text-[0.8rem] leading-relaxed [&>code]:bg-transparent [&>code]:p-0">
      {children}
    </pre>
  ),
  code: ({ children }) => <code className="rounded bg-zinc-200/70 px-1 py-0.5 font-mono text-[0.85em]">{children}</code>,
  table: ({ children }) => (
    <div className="my-2 overflow-x-auto">
      <table className="w-full border-collapse text-left text-[0.85em]">{children}</table>
    </div>
  ),
  th: ({ children }) => <th className="border-b border-zinc-300 px-2 py-1 font-semibold">{children}</th>,
  td: ({ children }) => <td className="border-b border-zinc-200 px-2 py-1 align-top">{children}</td>,
}

type Citations = {
  /** Number of sources the markers may point at; null = not known yet (streaming). */
  count: number | null
}

/**
 * Light markdown (headings, lists, bold, code, links, quotes) with single newlines kept as line breaks.
 * Raw HTML is not rendered. `streaming` shows a blinking caret after the last block.
 * With `citations`, "sentence[1]" renders as an underlined sentence plus a superscript marker.
 */
export function Markdown({
  text,
  className,
  streaming = false,
  citations,
}: {
  text: string
  className?: string
  streaming?: boolean
  /** Enable inline [n] citation rendering (assistant answers). */
  citations?: Citations
}) {
  let body = normalize(text)
  if (citations && streaming) body = stripPartialMarker(body)
  const rehypePlugins: NonNullable<Options['rehypePlugins']> = []
  if (citations) rehypePlugins.push([rehypeCitations, { count: citations.count }])
  if (streaming) rehypePlugins.push(rehypeCaret)
  return (
    <div className={cn('text-sm leading-7 break-words', streaming && 'md-streaming', className)}>
      <ReactMarkdown remarkPlugins={[remarkBreaks]} rehypePlugins={rehypePlugins} components={components}>
        {body}
      </ReactMarkdown>
    </div>
  )
}
