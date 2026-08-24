"""Bootstrap-based Elo tournament for comparing pipeline/optimization_harness.py candidates.

A single train/validation split answers "which candidate wins on this one split" -- exactly
the search-then-split-once comparison Round 11 Priority 1 already gates carefully with PBO
and deflated Sharpe. This is a complementary tool, not a replacement: it asks a narrower
question -- given only the periods already in one split (never touching another split), how
ROBUST is any apparent edge between two candidates across many different resamples of those
same periods?

Bootstrap resampling cannot manufacture information beyond what is already in the sampled
periods. If a panel genuinely lacks the statistical power to distinguish two candidates (as
several R11-P1/P5 runs found via PBO on this exact fundamentals panel), repeated Elo play
will show that honestly: ratings that stay close together and never separate, round after
round -- not a false winner manufactured by re-running the same comparison until one candidate
happens to look better. What "improvements like chess Elo" buys here is a running, updating
rating that reveals whether an edge is consistent under resampling, not a way around the
underlying data limit a small panel imposes.

Each round draws one bootstrap sample of period indices (with replacement, default size
equal to the pool) from the periods handed in. Every candidate's mean rank IC is computed on
that same sample, so all candidates in a round are compared on identical data. Every pair
then "plays": whichever has the higher mean IC on that round's sample wins (a tie splits the
Elo update evenly), and ratings update by the standard logistic Elo formula. Repeated over
many rounds, a real, small, consistent edge accumulates into rating separation; a
non-existent one does not.

Usage:
    python3 pipeline/elo_tournament.py --panel pipeline/backtest_signal_panel.json \
        --candidates '{"champion": null}' --include-formula --rounds 200 --seed 0
"""

import argparse
import json
import os
import random
import sys
from itertools import combinations

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from evaluation import rank_ic  # noqa: E402
from optimization_harness import Panel, composite_score, formula_weights  # noqa: E402

DEFAULT_ELO = 1500.0
DEFAULT_K = 24.0


def period_ic(period, weights):
    leg_scores_by_ticker = period.get("leg_scores") or {}
    forwards = period.get("forward_returns") or {}
    pairs = []
    for ticker, legs in leg_scores_by_ticker.items():
        score = composite_score(legs, weights)
        forward = forwards.get(ticker)
        if score is not None and forward is not None:
            pairs.append((score, forward))
    if len(pairs) < 5:
        return None
    return rank_ic([pair[0] for pair in pairs], [pair[1] for pair in pairs])


def mean_ic_on_sample(periods, sample_indices, weights):
    values = [ic for ic in (period_ic(periods[index], weights) for index in sample_indices)
             if ic is not None]
    return sum(values) / len(values) if values else None


def expected_score(rating_a, rating_b):
    return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / 400.0))


def update_elo(rating_a, rating_b, score_a, *, k=DEFAULT_K):
    expected_a = expected_score(rating_a, rating_b)
    new_a = rating_a + k * (score_a - expected_a)
    new_b = rating_b + k * ((1 - score_a) - (1 - expected_a))
    return new_a, new_b


def run_tournament(periods, candidates, *, rounds, seed=0, k=DEFAULT_K, sample_size=None):
    """``candidates``: ``[(name, weights)]``. Runs ``rounds`` bootstrap draws from ``periods``,
    a full round-robin of Elo-updating matches per draw. Returns ratings, a sorted
    leaderboard, and the per-round scores so a caller can see how ratings evolved rather than
    only the final snapshot.
    """
    if len(candidates) < 2:
        raise ValueError("need at least two candidates to run a tournament")
    if rounds < 1:
        raise ValueError("rounds must be at least 1")
    rng = random.Random(seed)
    names = [name for name, _ in candidates]
    weights_by_name = dict(candidates)
    ratings = {name: DEFAULT_ELO for name in names}
    pool_size = len(periods)
    if pool_size < 1:
        raise ValueError("periods must be non-empty")
    sample_size = sample_size or pool_size
    history = []

    for round_index in range(rounds):
        sample_indices = [rng.randrange(pool_size) for _ in range(sample_size)]
        round_scores = {name: mean_ic_on_sample(periods, sample_indices, weights_by_name[name])
                        for name in names}
        for name_a, name_b in combinations(names, 2):
            score_a_value, score_b_value = round_scores[name_a], round_scores[name_b]
            if score_a_value is None or score_b_value is None:
                continue
            if score_a_value > score_b_value:
                outcome = 1.0
            elif score_a_value < score_b_value:
                outcome = 0.0
            else:
                outcome = 0.5
            ratings[name_a], ratings[name_b] = update_elo(
                ratings[name_a], ratings[name_b], outcome, k=k)
        history.append({"round": round_index, "scores": round_scores})

    leaderboard = sorted(({"name": name, "elo": round(rating, 1)} for name, rating in ratings.items()),
                         key=lambda row: -row["elo"])
    return {"ratings": {name: round(rating, 1) for name, rating in ratings.items()},
           "leaderboard": leaderboard, "rounds_played": rounds, "sample_size": sample_size,
           "pool_size": pool_size, "history": history}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--panel", required=True)
    parser.add_argument("--candidates", default="",
                        help="JSON object {name: {leg: weight}}. Always includes the panel's "
                             "own leg_weights as 'champion'.")
    parser.add_argument("--include-formula", action="store_true",
                        help="Also enter a formula_weights() candidate derived from the "
                             "train slice below.")
    parser.add_argument("--train-fraction", type=float, default=0.5)
    parser.add_argument("--validation-fraction", type=float, default=0.25)
    parser.add_argument("--rounds", type=int, default=200)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--k", type=float, default=DEFAULT_K)
    parser.add_argument("--sample-size", type=int, default=0,
                        help="0 = same as the validation pool size (standard bootstrap)")
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)

    panel_data = json.load(open(args.panel))
    periods = panel_data["periods"]
    panel = Panel(periods, train_fraction=args.train_fraction,
                 validation_fraction=args.validation_fraction)

    candidates = [("champion", panel_data["leg_weights"])]
    if args.candidates:
        candidates += list(json.loads(args.candidates).items())
    if args.include_formula:
        formula = formula_weights(panel.train)
        if formula:
            candidates.append(("formula", formula))
        else:
            print("[elo] formula_weights() returned nothing usable on the train slice, skipping")

    result = run_tournament(panel.validation, candidates, rounds=args.rounds, seed=args.seed,
                            k=args.k, sample_size=args.sample_size or None)
    result["candidates"] = dict(candidates)
    result["panel"] = args.panel

    print(f"Elo leaderboard after {args.rounds} rounds "
         f"(pool={result['pool_size']} validation periods, sample={result['sample_size']}):")
    for row in result["leaderboard"]:
        print(f"  {row['elo']:>7.1f}  {row['name']}")

    if args.out:
        with open(args.out, "w") as handle:
            json.dump(result, handle, indent=2)
        print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
