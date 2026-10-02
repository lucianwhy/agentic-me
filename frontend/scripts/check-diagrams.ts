/** prebuild: fail fast if src/generated/diagrams.ts is out of date (no browser or mermaid needed). */
import { diagramsHash } from '../src/generated/diagrams.ts'
import { diagramHash } from './diagram-hash.ts'

const expected = diagramHash()
if (diagramsHash !== expected) {
  console.error(
    `check-diagrams: src/generated/diagrams.ts is stale (have ${diagramsHash}, expected ${expected}).\n` +
      'Diagram sources, theme or the mermaid version changed. Run `npm run diagrams` and commit the result.',
  )
  process.exit(1)
}
console.log(`check-diagrams: prerendered diagrams up to date (${expected})`)
