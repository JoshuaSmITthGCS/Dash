import { spawnSync } from 'node:child_process'
import { readdir, readFile, stat, writeFile } from 'node:fs/promises'
import settings from '../pipeline/config/settings.json' with { type: 'json' }

const root = new URL('../', import.meta.url)
const auditRun = spawnSync('npm', ['audit', '--json'], {
  cwd: root,
  encoding: 'utf8',
})
if (!auditRun.stdout) throw new Error(auditRun.stderr || 'npm audit produced no JSON output')
const audit = JSON.parse(auditRun.stdout)
const lock = JSON.parse(await readFile(new URL('../package-lock.json', import.meta.url), 'utf8'))
const html = await readFile(new URL('../dist/index.html', import.meta.url), 'utf8')
const entryPath = html.match(/<script[^>]+src="([^"]+\.js)"/)?.[1]
if (!entryPath) throw new Error('Could not resolve the production entry chunk from dist/index.html')

const assetDirectory = new URL('../dist/assets/', import.meta.url)
const chunks = []
for (const name of await readdir(assetDirectory)) {
  if (!name.endsWith('.js')) continue
  const file = new URL(name, assetDirectory)
  chunks.push({ name, bytes: (await stat(file)).size })
}
chunks.sort((left, right) => right.bytes - left.bytes)
const entryName = entryPath.split('/').at(-1)
const main = chunks.find((chunk) => chunk.name === entryName)
const vulnerabilities = Object.values(audit.vulnerabilities || {})
const report = {
  generated_at: new Date().toISOString(),
  dependencies: {
    before: {
      high: settings.build.dependency_audit_baseline_high,
      total: settings.build.dependency_audit_baseline_total,
    },
    after: audit.metadata?.vulnerabilities,
    all_high_severity_resolved: !vulnerabilities.some((item) => item.severity === 'high'),
    resolved_transitives: {
      brace_expansion: lock.packages?.['node_modules/brace-expansion']?.version,
      undici: lock.packages?.['node_modules/undici']?.version,
    },
    remaining: vulnerabilities.map((item) => ({ name: item.name, severity: item.severity })),
  },
  bundle: {
    advisory_max_bytes: settings.build.chunk_advisory_max_bytes,
    baseline_main_chunk_bytes: settings.build.baseline_main_chunk_bytes,
    current_main_chunk: main,
    main_reduction_pct: main
      ? Number(((1 - main.bytes / settings.build.baseline_main_chunk_bytes) * 100).toFixed(2))
      : null,
    every_javascript_chunk_below_advisory: chunks.every((chunk) => chunk.bytes < settings.build.chunk_advisory_max_bytes),
    chunks,
  },
}

await writeFile(new URL('../pipeline/reports/hygiene_check.json', import.meta.url), `${JSON.stringify(report, null, 2)}\n`)
process.stdout.write(`${JSON.stringify(report, null, 2)}\n`)
if (!report.dependencies.all_high_severity_resolved || !report.bundle.every_javascript_chunk_below_advisory) {
  process.exitCode = 1
}
