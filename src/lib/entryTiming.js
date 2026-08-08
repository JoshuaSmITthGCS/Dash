// Buy-now-or-wait guidance for the research list: every buy-worthy name gets exactly one of
// two verdicts, reusing dipWatch's own floor/recovery estimate rather than inventing a
// second timing model. This is presentation logic over an already-published stance and
// already-computed technical levels -- not a new predictive signal, and it does not touch
// selection or ranking.
//
//   'buy_now'           stance is ATTRACTIVE/PROMISING, confidence supports conviction, and
//                        the stock is not in a dipWatch-eligible decline.
//   'set_low_alert'      stance is buy-worthy but the stock is currently down from its highs;
//                        dipWatch's floor is the suggested alert price.
//   'review'             buy-worthy and not in a pullback, but confidence is only moderate.
//   'insufficient_data'  buy-worthy by stance, but not enough evidence resolved to say
//                        anything about timing - stated out loud rather than left blank.
//
// Returns null for ETFs, ineligible stances (dipWatch's own ELIGIBLE_STANCES), and TRIM/SELL
// guidance -- there is no honest "buy now" for a name the platform is telling you to sell.
import { dipWatch, ELIGIBLE_STANCES } from './dipWatch'
import { allowsConviction, gateReason, isActionable } from './confidenceGate'

export function entryTiming(stock) {
  if (!stock || stock.is_etf) return null
  if (!ELIGIBLE_STANCES.has(stock.stance)) return null
  if (['TRIM', 'SELL'].includes(stock.recommendation?.action)) return null
  // "Buy Now" is the most prescriptive thing on the research list, so it needs the strongest
  // evidence. A row that has not resolved enough data to be actionable never gets it - that
  // is what stopped a row from displaying "Data confidence 0%" and "BUY NOW" side by side.
  //
  // It returns a stated verdict rather than null, though: this row IS buy-worthy by stance,
  // so silently rendering an empty timing cell looks like an oversight and invites the reader
  // to fill the gap themselves. Withholding a call and explaining why is the whole point.
  if (!isActionable(stock.confidence)) {
    return {
      verdict: 'insufficient_data',
      label: 'No timing call',
      reason: `${gateReason(stock.confidence)} Rated buy-worthy on stance, but there is not `
        + 'enough resolved evidence to say whether today is a reasonable entry.',
    }
  }

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
  if (!allowsConviction(stock.confidence)) {
    return {
      verdict: 'review',
      label: 'Review',
      reason: 'Rated buy-worthy and not in a pullback, but data confidence is only moderate – '
        + 'worth reviewing rather than acting on today.',
    }
  }
  return {
    verdict: 'buy_now',
    label: 'Buy Now',
    reason: 'Rated buy-worthy and not currently in a confirmed pullback.',
  }
}
