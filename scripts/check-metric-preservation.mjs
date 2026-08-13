import fs from 'node:fs'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..')
const inventory = fs.readFileSync(path.join(root, 'docs/METRIC_INVENTORY.md'), 'utf8')
const modelSource = fs.readFileSync(path.join(root, 'src/lib/portfolioMetricModel.js'), 'utf8')
const signalMetrics = JSON.parse(fs.readFileSync(path.join(root, 'public/data/validation/signal_metrics.json'), 'utf8'))
const signalIds = new Set((signalMetrics.metrics || []).map((row) => row.id))

const rows = [...inventory.matchAll(/^\| ([a-z0-9_]+) \| ([^|]+) \| ([^|]+) \| ([^|]+) \|/gm)]
  .map((match) => ({ id: match[1], name: match[2].trim(), calculation: match[3].trim(), render: match[4].trim() }))
  .filter((row) => !['id', 'site', 'surface', 'candidate'].includes(row.id))

function filesBelow(directory) {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const target = path.join(directory, entry.name)
    return entry.isDirectory() ? filesBelow(target) : [target]
  })
}

const sourceFiles = filesBelow(path.join(root, 'src'))
const sourceByBasename = new Map(sourceFiles.map((file) => [path.basename(file), file]))
const literal = (id) => modelSource.includes(`'${id}'`) || modelSource.includes(`id: \`${id}\``)

const missing = []
const evidence = []
for (const row of rows) {
  if (signalIds.has(row.id)) {
    evidence.push({ id: row.id, route: 'Algorithm → SignalMetricsPanel', evidence: 'published signal registry' })
    continue
  }
  if (literal(row.id)) {
    evidence.push({ id: row.id, route: 'Overview / All Metrics / Historical', evidence: 'portfolio metric model' })
    continue
  }
  const renderFiles = [...row.render.matchAll(/([A-Za-z][A-Za-z0-9]+\.(?:jsx|js))/g)]
    .map((match) => match[1])
    .filter((name) => sourceByBasename.has(name))
  const wasOnlyCalculated = /calculated(?![^|]*(?:supporting text|methodology))/i.test(row.render)
    && !renderFiles.length
  if (renderFiles.length && !wasOnlyCalculated) {
    evidence.push({ id: row.id, route: renderFiles.join(', '), evidence: 'preserved render route' })
    continue
  }
  missing.push(row)
}

const duplicateIds = rows.filter((row, index) => rows.findIndex((candidate) => candidate.id === row.id) !== index)
if (duplicateIds.length || missing.length) {
  if (duplicateIds.length) process.stderr.write(`Duplicate inventory IDs: ${duplicateIds.map((row) => row.id).join(', ')}\n`)
  if (missing.length) process.stderr.write(`Unreachable inventory metrics:\n${missing.map((row) => `- ${row.id}: ${row.name}`).join('\n')}\n`)
  process.exitCode = 1
} else {
  process.stdout.write(`Metric preservation gate passed: ${rows.length} / ${rows.length} pre-existing canonical metrics remain reachable.\n`)
  process.stdout.write(`Portfolio workspace/model: ${evidence.filter((row) => row.evidence === 'portfolio metric model').length}; signal registry: ${evidence.filter((row) => row.evidence === 'published signal registry').length}; preserved specialist routes: ${evidence.filter((row) => row.evidence === 'preserved render route').length}.\n`)
}
