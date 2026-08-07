// Buy-now-or-wait guidance for the research list: every buy-worthy name gets exactly one of
// two verdicts, reusing dipWatch's own floor/recovery estimate rather than inventing a
// second timing model. This is presentation logic over an already-published stance and
// already-computed technical levels -- not a new predictive signal, and it does not touch
// selection or ranking.
//
//   'buy_now'       stance is ATTRACTIVE/PROMISING and the stock is not currently in a
//                    dipWatch-eligible decline -- no reason a research-driven buyer would wait.
//   'set_low_alert'  stance is buy-worthy but the stock is currently down from its highs;
//                    dipWatch's floor is the suggested alert price.
//
// Returns null for ETFs, ineligible stances (dipWatch's own ELIGIBLE_STANCES), and TRIM/SELL
// guidance -- there is no honest "buy now" for a name the platform is telling you to sell.
import { dipWatch, ELIGIBLE_STANCES } from './dipWatch'

export function entryTiming(stock) {
  if (!stock || stock.is_etf) return null
  if (!ELIGIBLE_STANCES.has(stock.stance)) return null
  if (['TRIM', 'SELL'].includes(stock.recommendation?.action)) return null

  const dip = dipWatch(stock)
  if (dip) {
    return {
      verdict: 'set_low_alert',
      label: 'Set Low Alert',
      alertPrice: dip.floor,
      recoveryPrice: dip.max,
      status: dip.status,
      reason: `Down from its highs and not confirmed to have bottomed - a below-$${dip.floor.toFixed(2)} alert catches it if the decline continues.`,
    }
  }
  return {
    verdict: 'buy_now',
    label: 'Buy Now',
    reason: 'Rated buy-worthy and not currently in a confirmed pullback.',
  }
}
