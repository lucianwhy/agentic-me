import { createContext } from 'react'

import type { Source } from '@/lib/api'

export type CitationContextValue = {
  /** Sources have arrived (done event): markers are interactive. */
  ready: boolean
  sources: Source[]
  activate: (nums: number[], sentence: string) => void
}

/** Provided per assistant message; read by the citation sentence / marker components. */
export const CitationContext = createContext<CitationContextValue | null>(null)
