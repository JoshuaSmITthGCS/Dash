# ValueSignal iOS widget (Scriptable)

`valuesignal-widget.js` is a [Scriptable](https://scriptable.app) script that turns your
deployed ValueSignal site into a home screen widget. It fetches the public
`public/data/advisor.json` and `public/data/etfs.json` files your pipeline already publishes
(no login required) and shows the top research-score picks. **Tap the widget to switch it
between top stocks and top ETFs.**

## Install

1. Install **Scriptable** from the App Store.
2. Open Scriptable → `+` → paste in the contents of `valuesignal-widget.js`.
3. Edit the `SITE_URL` constant near the top of the script if your deployment isn't
   `https://dash1212.netlify.app`.
4. Rename the script (e.g. "ValueSignal") — Scriptable uses the script name as the widget name.
5. Long-press your home screen → `+` → **Scriptable** → add a small, medium, or large widget.
6. Long-press the new widget → **Edit Widget** → set **Script** to the one you created.

## Notes

- Tapping the widget switches it between **Stocks** and **ETFs**. This opens Scriptable
  briefly (iOS widgets can't run background logic on tap) and shows a preview of the new
  view; the actual home screen widget picks up the change on its next refresh, which iOS
  schedules — not always instant, but usually within a few seconds to a minute.
- Data refreshes roughly every hour (`widget.refreshAfterDate`); iOS decides the exact timing.
- If the fetch fails (offline, site down), the widget falls back to the last successful
  response cached on-device, marked with an orange dot and "cached" timestamp.
- The score colors here are a simplified 4-bucket visual scale for the widget only — the
  authoritative tier system lives in `src/lib/scoreBands.js` and is percentile-based, not
  absolute-score-based, so don't treat the widget's colors as identical to the app's Tier A–E.
- This directory is excluded from `npm run lint` (see `eslint.config.js`) because Scriptable
  scripts run against Scriptable's own globals (`Request`, `ListWidget`, `FileManager`,
  `config`, `Script`, ...), not a browser or Node environment.
