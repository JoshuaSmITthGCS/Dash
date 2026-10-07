#!/usr/bin/env bash
# Netlify `ignore` command (wired in netlify.toml). Exit 0 = skip this build, exit 1 = build.
#
# The data pipeline commits to main many times a day. Each of those commits used to trigger
# a full Netlify build, which is what drove the build-minutes bill. Data-only commits are now
# skipped here; .github/workflows/netlify-scheduled-deploy.yml pings a build hook every 6
# hours to publish whatever data has piled up since the last deploy.
#
# Any commit touching a path NOT in DATA_ONLY builds immediately, as before. The list is
# deliberately an allowlist of pipeline output, not a denylist of source: src/ imports from
# pipeline/config/, pipeline/validation/ and docs/ at build time, so "anything under
# pipeline/" or "anything that isn't src/" would be wrong.
set -u

DATA_ONLY='^(public/data/|pipeline/data/|pipeline/[a-z_]*pit_store/|pipeline/shadow_store/|pipeline/reports/|pipeline/options_track_record/|pipeline/backtest_political_institutional_results\.json$|research/)'

base="${CACHED_COMMIT_REF:-}"
head="${COMMIT_REF:-HEAD}"

# No previous deploy to diff against, or the clone can't see it: build.
if [[ -z "$base" ]] || ! git cat-file -e "${base}^{commit}" 2>/dev/null; then
  echo "netlify-ignore: no usable CACHED_COMMIT_REF, building"
  exit 1
fi

if ! changed="$(git diff --name-only "$base" "$head" 2>/dev/null)"; then
  echo "netlify-ignore: git diff failed, building"
  exit 1
fi

if [[ -z "$changed" ]]; then
  echo "netlify-ignore: nothing changed since the last deploy (${base:0:8}), skipping"
  exit 0
fi

# Builds started by a build hook (the scheduled deploy, or a manual site refresh) exist to
# publish data, so any change at all is reason enough to build.
if [[ -n "${INCOMING_HOOK_TITLE:-}${INCOMING_HOOK_URL:-}" ]]; then
  echo "netlify-ignore: build hook '${INCOMING_HOOK_TITLE:-unnamed}' with changes since ${base:0:8}, building"
  exit 1
fi

code_changes="$(grep -Ev "$DATA_ONLY" <<<"$changed" || true)"
if [[ -n "$code_changes" ]]; then
  echo "netlify-ignore: non-data changes since ${base:0:8}, building:"
  head -20 <<<"$code_changes"
  exit 1
fi

echo "netlify-ignore: only pipeline data changed since ${base:0:8} ($(wc -l <<<"$changed") files), skipping; the scheduled build hook will publish it"
exit 0
