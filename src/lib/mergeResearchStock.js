// Pure move from src/components/StockDetailModal.jsx (mergeResearchStock was defined inline
// there). Zero behavior change — same body, just relocated so both the legacy Classic modal
// and the core Stock Detail Sheet (src/mediums/core/screens/StockDetailSheet.jsx) can import it
// without either one depending on the other.

/**
 * Browse/portfolio routes open the detail sheet immediately from a lighter row (report.json:
 * research/portfolio_coverage/screen_universe). Once the deeper advisor.json snapshot arrives,
 * this fills in evidence, modifiers and explainability while preserving any newer live quote or
 * position-specific fields the calling route already placed on the row.
 */
export function mergeResearchStock(suppliedStock, fullResearch) {
  if (!suppliedStock) return suppliedStock
  const fullStock = fullResearch?.research?.find((row) => row.ticker === suppliedStock.ticker)
    || fullResearch?.portfolio_coverage?.find((row) => row.ticker === suppliedStock.ticker)
    || fullResearch?.screen_universe?.find((row) => row.ticker === suppliedStock.ticker)
  if (!fullStock) return suppliedStock
  return {
    ...fullStock,
    ...suppliedStock,
    analysis_v2: { ...(fullStock.analysis_v2 || {}), ...(suppliedStock.analysis_v2 || {}) },
  }
}

export default mergeResearchStock
