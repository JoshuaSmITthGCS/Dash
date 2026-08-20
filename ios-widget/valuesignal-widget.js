// Variables used by Scriptable.
// icon-color: green; icon-glyph: chart-line;
//
// ValueSignal home screen widget.
//
// Install:
//   1. Install "Scriptable" from the App Store (https://scriptable.app).
//   2. Open Scriptable, create a new script, paste this file's contents in.
//   3. Name it "ValueSignal" and set SITE_URL below to your deployment.
//   4. Long-press your home screen -> "+" -> Scriptable -> add a
//      small/medium/large widget -> long-press it -> Edit Widget ->
//      set "Script" to this script.
//
// The widget reads public/data/advisor.json, which this repo's pipeline
// publishes as a static file (no auth) and Netlify serves at SITE_URL.
// It shows the top research-score picks; tapping the widget opens the
// live dashboard. Falls back to the last successful fetch when offline.

const SITE_URL = "https://dash1212.netlify.app"
const DATA_URL = `${SITE_URL}/data/advisor.json`
const CACHE_PATH = FileManager.local().joinPath(
  FileManager.local().documentsDirectory(),
  "valuesignal-widget-cache.json"
)

// Simplified visual scale for the widget only — not the app's authoritative
// percentile tier system (see src/lib/scoreBands.js), just a quick eyeball cue.
const TIER_COLORS = [
  { min: 85, color: new Color("#1fae7c", "#3ddba0") },
  { min: 75, color: new Color("#2b6cc4", "#5b9be6") },
  { min: 65, color: new Color("#c58a1f", "#e0b24f") },
  { min: 0, color: new Color("#b83c37", "#e0655f") },
]

function colorForScore(score) {
  return (TIER_COLORS.find((t) => score >= t.min) ?? TIER_COLORS.at(-1)).color
}

async function fetchAdvisorData() {
  try {
    const req = new Request(DATA_URL)
    req.timeoutInterval = 15
    const data = await req.loadJSON()
    if (!Array.isArray(data.research)) throw new Error("malformed response")
    FileManager.local().writeString(CACHE_PATH, JSON.stringify(data))
    return { data, stale: false }
  } catch (err) {
    if (FileManager.local().fileExists(CACHE_PATH)) {
      const cached = JSON.parse(FileManager.local().readString(CACHE_PATH))
      return { data: cached, stale: true }
    }
    throw err
  }
}

function formatGeneratedAt(iso) {
  if (!iso) return ""
  const d = new Date(iso)
  const now = new Date()
  const sameDay = d.toDateString() === now.toDateString()
  const fmt = new DateFormatter()
  fmt.dateFormat = sameDay ? "HH:mm" : "MMM d, HH:mm"
  return fmt.string(d)
}

function addRow(container, pick, { compact } = {}) {
  const row = container.addStack()
  row.centerAlignContent()

  const tickerText = row.addText(pick.ticker)
  tickerText.font = Font.semiboldSystemFont(compact ? 13 : 15)
  tickerText.lineLimit = 1
  tickerText.minimumScaleFactor = 0.8

  if (!compact && pick.sector) {
    row.addSpacer(6)
    const sectorText = row.addText(pick.sector)
    sectorText.font = Font.systemFont(11)
    sectorText.textColor = Color.gray()
    sectorText.lineLimit = 1
  }

  row.addSpacer()

  const scoreText = row.addText(pick.score.toFixed(1))
  scoreText.font = Font.semiboldSystemFont(compact ? 13 : 15)
  scoreText.textColor = colorForScore(pick.score)
}

function buildWidget({ data, stale }, family) {
  const widget = new ListWidget()
  widget.url = SITE_URL
  widget.backgroundColor = new Color("#ffffff", "#111318")
  widget.setPadding(14, 14, 12, 14)

  const rowCounts = { small: 3, medium: 5, large: 10 }
  const rowCount = rowCounts[family] ?? 5
  const picks = (data.research ?? []).slice(0, rowCount)

  const header = widget.addStack()
  header.centerAlignContent()
  const title = header.addText("ValueSignal")
  title.font = Font.boldSystemFont(14)
  header.addSpacer()
  if (stale) {
    const staleDot = header.addText("●")
    staleDot.font = Font.systemFont(10)
    staleDot.textColor = Color.orange()
  }

  widget.addSpacer(8)

  const list = widget.addStack()
  list.layoutVertically()
  picks.forEach((pick, i) => {
    if (i > 0) list.addSpacer(family === "small" ? 4 : 6)
    addRow(list, pick, { compact: family === "small" })
  })

  if (picks.length === 0) {
    const empty = list.addText("No data")
    empty.font = Font.systemFont(13)
    empty.textColor = Color.gray()
  }

  widget.addSpacer()

  const footer = widget.addText(
    stale
      ? `cached · ${formatGeneratedAt(data.generated_at)}`
      : formatGeneratedAt(data.generated_at)
  )
  footer.font = Font.systemFont(10)
  footer.textColor = Color.gray()

  widget.refreshAfterDate = new Date(Date.now() + 60 * 60 * 1000)
  return widget
}

async function run() {
  const family = config.widgetFamily ?? "medium"
  let widget

  try {
    const result = await fetchAdvisorData()
    widget = buildWidget(result, family)
  } catch (err) {
    widget = new ListWidget()
    widget.url = SITE_URL
    const text = widget.addText(`ValueSignal\nCouldn't load data.\n${err.message}`)
    text.font = Font.systemFont(12)
    text.textColor = Color.red()
    widget.refreshAfterDate = new Date(Date.now() + 15 * 60 * 1000)
  }

  if (config.runsInWidget) {
    Script.setWidget(widget)
  } else {
    await widget.presentMedium()
  }
  Script.complete()
}

await run()
