"""Runs every options-strategy screen's walk-forward backtest.

Each strategy module's own build_*_screen.py owns its backtest_universe()/run_backtest()
- this script is just the orchestration point that calls all seven, the same way the
GitHub Actions workflow calls each live screen builder as its own step. Kept as a single
script (rather than one workflow step per backtest) because every backtest reuses the
same already-cached price history and costs no live network call, so there's no
rate-limit reason to spread them across separate steps - a failure in one strategy's
backtest is logged and skipped rather than stopping the rest, same non-fatal spirit as
the live screens' `|| echo "::warning::..."` workflow steps.
"""

from common import LOG

import build_advanced_options_screen
import build_cash_secured_put_screen
import build_collar_screen
import build_covered_call_screen
import build_iron_butterfly_screen
import build_jade_lizard_screen
import build_options_screen
import build_options_strategies
import build_pmcc_screen
import build_protective_put_screen
import build_vertical_spread_screen

BACKTEST_MODULES = [
    ("Multi-day options", build_options_screen),
    ("Covered call", build_covered_call_screen),
    ("Cash-secured put", build_cash_secured_put_screen),
    ("Protective put", build_protective_put_screen),
    ("Collar", build_collar_screen),
    ("Vertical spread", build_vertical_spread_screen),
    ("Advanced strategies", build_advanced_options_screen),
    ("Short-term trades (combined)", build_options_strategies),
    ("Iron butterfly", build_iron_butterfly_screen),
    ("Jade lizard", build_jade_lizard_screen),
    ("PMCC", build_pmcc_screen),
]


def run():
    results = {}
    for label, module in BACKTEST_MODULES:
        try:
            results[label] = module.run_backtest()
        except Exception as exc:  # noqa: BLE001 - one strategy's failure shouldn't block the rest
            LOG.error(f"{label} backtest failed: {type(exc).__name__}: {exc}")
            results[label] = None
    succeeded = sum(1 for result in results.values() if result and result.get("status") == "success")
    LOG.info(f"Strategy backtests: {succeeded}/{len(BACKTEST_MODULES)} published successfully")
    return results


if __name__ == "__main__":
    run()
