/** Fingerprint of everything that affects the prerendered diagram SVGs. */
import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'

import { diagramSources, mermaidConfig } from '../src/data/diagram-sources.ts'

/** Bump when render-diagrams.ts changes how SVGs are produced or post-processed. */
export const RENDERER_VERSION = 1

export function mermaidVersion(): string {
  try {
    const url = new URL('../node_modules/mermaid/package.json', import.meta.url)
    return JSON.parse(readFileSync(url, 'utf8')).version as string
  } catch {
    return 'unknown'
  }
}

export function diagramHash(version = mermaidVersion()): string {
  const payload = JSON.stringify({ diagramSources, mermaidConfig, version, RENDERER_VERSION })
  return createHash('sha256').update(payload).digest('hex').slice(0, 16)
}
