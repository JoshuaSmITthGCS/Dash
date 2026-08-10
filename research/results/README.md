# Research results

Output of the research harnesses in `research/`. Every file here is **generated**, and every
file here is committed, because a result whose only record is a terminal buffer cannot be
checked afterwards.

## What is in here

| File | Produced by | Regenerate with |
|---|---|---|
| `phase4_baselines.json` | `research/baselines.py` | see below |

## Regenerating

No network is required — the point-in-time fundamentals store and the price cache are both
committed. A full 2017–2026 run takes roughly twenty minutes and about 4 GB of memory.

```
PYTHONPATH=pipeline python -c "import sys, json; sys.path.insert(0, 'research'); \
  import baselines; json.dump(baselines.run(), \
  open('research/results/phase4_baselines.json', 'w'), indent=2, default=str)"
```

## Reading anything in here

Two properties hold for every result file, and both are carried inside the files themselves
rather than left to a reader's memory:

- **`limitations` is part of the result, not a caveat attached to it.** Survivorship, the
  length of the window, and the absence of a multiple-testing correction are recorded next to
  every number they apply to.
- **A number that could not be computed is absent, not defaulted.** No result in this
  directory contains a neutral stand-in for a missing input.

The binding limitation on everything here is survivorship: the candidate set is the set of
companies that still have a price feed today. That biases every return upward by an amount
this pipeline cannot yet quantify, so these files support statements about the *relative
ordering* of strategies and no statement about the level of return any of them would earn.
See `research/STATE.md`, blocker B-3.

## What is deliberately not here

Results from a run whose inputs were later found to be contaminated. The first Phase 4 run
produced a factor with 559% annualised volatility, traced to a single ticker that denotes two
different companies either side of a bankruptcy; it was deleted rather than committed with a
warning, and the run repeated after the fix. A superseded number in a repository outlives the
note explaining it.
