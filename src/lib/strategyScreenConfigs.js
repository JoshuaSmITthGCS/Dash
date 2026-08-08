// Config for the six options-strategy research screens (src/pages/StrategyScreen.jsx).
// Every screen's pipeline output (public/data/screens/<file>) shares one envelope:
// { rank, ticker, strategy?, eligibility, sector, peer_group, percentile, score,
//   structural_score, confidence, price, trend_20d, expiration, days_to_expiration,
//   capital_required, legs: [{action, option_type, strike, bid, ask, mid, spread_pct,
//   implied_volatility, open_interest, delta}], metrics: {...}, reason_codes }
// metricsConfig/strategyLabel/riskNote are functions of a row so the one screen that
// covers two strategies (advanced-strategies: iron condor + straddle) can vary them
// per row while every other screen just ignores the argument.

const GENERIC_RISK_NOTE = 'Research screen, not a trade instruction. Confirm live bid/ask, ' +
  'open interest, and your own risk limits in your broker before acting on anything here — ' +
  'nothing in this app places orders or connects to a brokerage account.'

export const STRATEGY_SCREENS = {
  'covered-call': {
    file: 'screens/covered-calls.json',
    eyebrow: 'Income · sell against shares you own',
    title: 'Covered call',
    description: 'Sell a call against a long 100-share position to collect premium. Caps ' +
      'your upside at the strike in exchange for income — ranked by annualized yield, ' +
      'liquidity, and how much the premium cushions a decline.',
    riskNote: GENERIC_RISK_NOTE + ' Selling calls caps your upside at the strike — a hard ' +
      'rally means missing the rest of the move, and you may be assigned (forced to sell ' +
      'your shares) before expiration. Requires owning 100 shares per contract.',
    strategyLabel: () => 'Covered call',
    metricsConfig: () => [
      ['annualized_yield', 'Annualized yield', 'pct'],
      ['premium', 'Premium collected', 'money'],
      ['breakeven', 'Breakeven', 'money'],
      ['max_return_if_assigned_pct', 'Max return if assigned', 'pct'],
      ['probability_assigned', 'Probability assigned', 'pct'],
      ['downside_cushion_pct', 'Downside cushion', 'pct'],
    ],
  },
  'cash-secured-put': {
    file: 'screens/cash-secured-puts.json',
    eyebrow: 'Income · get paid to name your price',
    title: 'Cash-secured put',
    description: 'Sell a put backed by cash collateral on a stock you would not mind owning ' +
      'at a discount — ranked by annualized yield on the collateral, modeled probability of ' +
      'expiring worthless, and liquidity.',
    riskNote: GENERIC_RISK_NOTE + ' Selling puts obligates you to buy 100 shares at the ' +
      'strike if assigned, even if the stock keeps falling below it. This screen assumes the ' +
      'put is fully cash-secured, not leveraged — set aside the full collateral shown.',
    strategyLabel: () => 'Cash-secured put',
    metricsConfig: () => [
      ['annualized_yield', 'Annualized yield', 'pct'],
      ['premium', 'Premium collected', 'money'],
      ['effective_cost_basis', 'Effective cost basis', 'money'],
      ['collateral', 'Collateral required', 'money'],
      ['probability_otm', 'Probability OTM (keep premium)', 'pct'],
      ['probability_assigned', 'Probability assigned', 'pct'],
    ],
  },
  'protective-put': {
    file: 'screens/protective-puts.json',
    eyebrow: 'Hedge · portfolio insurance',
    title: 'Protective put',
    description: 'Buy a put roughly 5-10% below spot to floor the downside on a long position ' +
      '— ranked by how cheap the hedge is relative to the stock’s own realized volatility.',
    riskNote: GENERIC_RISK_NOTE + ' The put premium is a real cost that is lost if the stock ' +
      'never drops enough to justify it. This is insurance, not a return generator — expect a ' +
      'drag in flat or rising markets.',
    strategyLabel: () => 'Protective put',
    metricsConfig: () => [
      ['cost_pct', 'Cost (% of position)', 'pct'],
      ['cost', 'Cost per share', 'money'],
      ['floor_price', 'Floor price', 'money'],
      ['max_loss_with_hedge_pct', 'Max loss, hedged', 'pct'],
    ],
  },
  collar: {
    file: 'screens/collars.json',
    eyebrow: 'Defined risk · floor and cap',
    title: 'Collar',
    description: 'Buy a protective put and sell a covered call, same expiration — the call ' +
      'premium funds some or all of the put. Ranked by how close to zero-cost the collar is ' +
      'and how wide the resulting floor-to-cap range is.',
    riskNote: GENERIC_RISK_NOTE + ' The call leg caps your upside at the cap price in exchange ' +
      'for funding the put — you give up gains beyond the cap even in a strong rally.',
    strategyLabel: () => 'Collar',
    metricsConfig: () => [
      ['net_cost_pct', 'Net cost (% of position)', 'pct'],
      ['floor_price', 'Floor price', 'money'],
      ['cap_price', 'Cap price', 'money'],
      ['range_width_pct', 'Range width', 'pct'],
      ['max_loss_pct', 'Max loss', 'pct'],
      ['max_gain_pct', 'Max gain', 'pct'],
    ],
  },
  'vertical-spread': {
    file: 'screens/vertical-spreads.json',
    eyebrow: 'Defined risk · directional',
    title: 'Vertical spread',
    description: 'A bull call spread on names trending up, a bear put spread on names ' +
      'trending down — both legs same expiration, both max profit and max loss capped by the ' +
      'strikes. Ranked by risk/reward, liquidity, and trend strength.',
    riskNote: GENERIC_RISK_NOTE + ' Max loss is capped at the net debit paid, but so is max ' +
      'profit, at the spread width minus that debit — this is not a leveraged bet on an ' +
      'unlimited move.',
    strategyLabel: (row) => row.strategy_type === 'bear_put_spread' ? 'Bear put spread' : 'Bull call spread',
    metricsConfig: () => [
      ['risk_reward', 'Risk / reward', 'ratio'],
      ['net_debit', 'Net debit', 'money'],
      ['max_profit', 'Max profit', 'money'],
      ['max_loss', 'Max loss', 'money'],
      ['width', 'Spread width', 'money'],
    ],
  },
  'advanced-strategies': {
    file: 'screens/advanced-strategies.json',
    eyebrow: 'Advanced · range-bound income or big-move bets',
    title: 'Advanced strategies',
    description: 'Iron condors (sell a call spread and a put spread, profit if price stays in ' +
      'range) and straddles (buy a call and put at the same strike, profit on a big move ' +
      'either direction) from the same option chain. This screen has no earnings-calendar ' +
      'awareness — straddle candidates are ranked as cheap-volatility ideas, not catalyst-timed ones.',
    riskNote: GENERIC_RISK_NOTE + ' Iron condors have defined but real loss potential if price ' +
      'moves outside the short strikes before expiration. Straddles cost two premiums and need ' +
      'a big move just to break even — time decay works against both legs every day the stock sits still.',
    strategyLabel: (row) => row.strategy === 'iron_condor' ? 'Iron condor' : 'Straddle',
    metricsConfig: (row) => row.strategy === 'iron_condor' ? [
      ['probability_in_range', 'Probability in range', 'pct'],
      ['net_credit', 'Net credit', 'money'],
      ['max_profit', 'Max profit', 'money'],
      ['max_loss', 'Max loss', 'money'],
    ] : [
      ['probability_of_profit', 'Probability of profit', 'pct'],
      ['cost', 'Cost (both legs)', 'money'],
      ['breakeven_up', 'Breakeven, upside', 'money'],
      ['breakeven_down', 'Breakeven, downside', 'money'],
      ['required_move_pct', 'Required move', 'pct'],
    ],
  },
}
