// Variables used by Scriptable.
// icon-color: green; icon-glyph: chart-line;
//
// ValueSignal home screen widget.
//
// Install:
//   1. Install "Scriptable" from the App Store (https://scriptable.app).
//   2. Open Scriptable, create a new script, paste this file's contents in.
//   3. Name it "ValueSignal" (the script's name is used to build the tap URL
//      below) and set SITE_URL if your deployment isn't dash1212.netlify.app.
//   4. Long-press your home screen -> "+" -> Scriptable -> add a
//      small/medium/large widget -> long-press it -> Edit Widget ->
//      set "Script" to this script.
//
// The widget reads public/data/advisor.json and public/data/etfs.json,
// which this repo's pipeline publishes as static files (no auth) and
// Netlify serves at SITE_URL. Tapping the widget switches it between
// top stock picks and top ETF picks (the switch shows up on the widget's
// next refresh — iOS decides that timing, so it isn't always instant).
// Falls back to the last successful fetch per view when offline.

const SITE_URL = "https://dash1212.netlify.app"

const VIEWS = {
  stocks: {
    label: "Stocks",
    url: `${SITE_URL}/data/advisor.json`,
    itemsKey: "research",
    cacheFile: "valuesignal-widget-cache-stocks.json",
    getScore: (item) => item.score,
    getSector: (item) => item.sector,
  },
  etfs: {
    label: "ETFs",
    url: `${SITE_URL}/data/etfs.json`,
    itemsKey: "etfs",
    cacheFile: "valuesignal-widget-cache-etfs.json",
    getScore: (item) => item.scores?.overall,
    getSector: (item) => item.category,
  },
}
const VIEW_ORDER = ["stocks", "etfs"]

const STATE_PATH = FileManager.local().joinPath(
  FileManager.local().documentsDirectory(),
  "valuesignal-widget-state.json"
)

// Simplified visual scale for the widget only — not the app's authoritative
// percentile tier system (see src/lib/scoreBands.js), just a quick eyeball cue.
function dynamicColor(lightHex, darkHex) {
  return Color.dynamic(new Color(lightHex), new Color(darkHex))
}

const TIER_COLORS = [
  { min: 85, color: dynamicColor("#1fae7c", "#3ddba0") },
  { min: 75, color: dynamicColor("#2b6cc4", "#5b9be6") },
  { min: 65, color: dynamicColor("#c58a1f", "#e0b24f") },
  { min: 0, color: dynamicColor("#b83c37", "#e0655f") },
]

function colorForScore(score) {
  return (TIER_COLORS.find((t) => score >= t.min) ?? TIER_COLORS.at(-1)).color
}

function readCurrentView() {
  const fm = FileManager.local()
  if (fm.fileExists(STATE_PATH)) {
    try {
      const state = JSON.parse(fm.readString(STATE_PATH))
      if (VIEWS[state.view]) return state.view
    } catch {
      // fall through to default below
    }
  }
  return VIEW_ORDER[0]
}

function writeCurrentView(view) {
  FileManager.local().writeString(STATE_PATH, JSON.stringify({ view }))
}

function nextView(view) {
  const i = VIEW_ORDER.indexOf(view)
  return VIEW_ORDER[(i + 1) % VIEW_ORDER.length]
}

async function fetchViewData(view) {
  const spec = VIEWS[view]
  const cachePath = FileManager.local().joinPath(
    FileManager.local().documentsDirectory(),
    spec.cacheFile
  )
  try {
    const req = new Request(spec.url)
    req.timeoutInterval = 15
    const data = await req.loadJSON()
    if (!Array.isArray(data[spec.itemsKey])) throw new Error("malformed response")
    FileManager.local().writeString(cachePath, JSON.stringify(data))
    return { data, stale: false }
  } catch (err) {
    if (FileManager.local().fileExists(cachePath)) {
      const cached = JSON.parse(FileManager.local().readString(cachePath))
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

// Tapping the widget runs this same script via Scriptable's URL scheme with
// ?toggle=1, which flips the stored view. There's no public API to force an
// instant WidgetKit timeline reload from inside Scriptable, so the change
// shows up on the widget's next natural refresh rather than immediately.
function tapUrl() {
  return `scriptable:///run/${encodeURIComponent(Script.name())}?toggle=1`
}

function buildWidget({ view, data, stale }, family) {
  const spec = VIEWS[view]
  const widget = new ListWidget()
  widget.url = tapUrl()
  widget.backgroundColor = dynamicColor("#ffffff", "#111318")
  widget.setPadding(14, 14, 12, 14)

  const rowCounts = { small: 3, medium: 5, large: 10 }
  const rowCount = rowCounts[family] ?? 5
  const picks = (data[spec.itemsKey] ?? [])
    .map((item) => ({
      ticker: item.ticker,
      sector: spec.getSector(item),
      score: spec.getScore(item) ?? 0,
    }))
    .slice(0, rowCount)

  const header = widget.addStack()
  header.centerAlignContent()
  const title = header.addText(`ValueSignal · ${spec.label}`)
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
      : `${formatGeneratedAt(data.generated_at)} · tap to switch`
  )
  footer.font = Font.systemFont(10)
  footer.textColor = Color.gray()

  widget.refreshAfterDate = new Date(Date.now() + 60 * 60 * 1000)
  return widget
}

async function widgetForView(view, family) {
  try {
    const result = await fetchViewData(view)
    return buildWidget({ view, ...result }, family)
  } catch (err) {
    const widget = new ListWidget()
    widget.url = tapUrl()
    const text = widget.addText(`ValueSignal · ${VIEWS[view].label}\nCouldn't load data.\n${err.message}`)
    text.font = Font.systemFont(12)
    text.textColor = Color.red()
    widget.refreshAfterDate = new Date(Date.now() + 15 * 60 * 1000)
    return widget
  }
}

async function run() {
  const family = config.widgetFamily ?? "medium"
  const toggled = args.queryParameters?.toggle === "1"

  let view = readCurrentView()
  if (toggled) {
    view = nextView(view)
    writeCurrentView(view)
  }

  const widget = await widgetForView(view, family)

  if (config.runsInWidget) {
    Script.setWidget(widget)
  } else {
    // Opened from the widget tap (toggled) or run manually in-app: show a
    // preview so there's visible confirmation of the current/new view.
    await widget.presentMedium()
  }
  Script.complete()
}

await run()
