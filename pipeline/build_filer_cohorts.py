"""Measure survivorship: who was filing then, and who is still filing now.

Every performance number this repository can currently produce is measured on the companies
that still have a price feed today. Companies that delisted, were acquired, or went to zero
between 2016 and now are absent from the universe entirely, and no rule evaluated on that
universe recovers them. The bias is upward, and until now its size was unknown -- which is why
``research/results`` says every return is "biased upward by an amount this pipeline cannot yet
quantify".

This quantifies the count. SEC's quarterly full indexes list every filing accepted in that
quarter, including by registrants that have since deregistered, so a CIK filing annual reports
in 2017 and nothing after 2020 is a company that left. The current ticker map holds only
survivors. The difference between the two is the gap.

**What this can and cannot establish.** It gives the *attrition rate* -- what fraction of the
companies filing in a given year had stopped by today -- and the CIKs concerned. It does not
give their returns, because no price source in this repository serves delisted securities, and
inventing them would be worse than admitting the gap. So the output bounds the problem rather
than correcting it: a backtest run over survivors only is measuring N% of the companies that
were actually investable, and the missing ones underperformed on average by construction --
that is largely why they left.

Attrition is not all failure. An acquisition ends a filing history as surely as a bankruptcy
does, and acquisitions typically end *above* the prevailing price. The two are separated where
the record allows: a registrant whose final filing is a merger-related form is treated
differently from one that simply stopped, and both counts are published, because a survivorship
adjustment that assumes every disappearance was a wipe-out overcorrects.

Run it as a workflow. It reads roughly 40 quarterly indexes, a few megabytes each.
"""

import argparse
import json
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import STORE_DIR, LOG  # noqa: E402
from sec_edgar import SEC_ROOT, SecEdgarClient  # noqa: E402

OUTPUT_DIR = os.path.join(STORE_DIR, "pit")
COHORTS = os.path.join(OUTPUT_DIR, "filer_cohorts.json")

# Forms that mark a company as an operating registrant for the period, rather than one of the
# many entities that file only prospectuses, ownership reports, or fund documents.
PERIODIC_FORMS = ("10-K", "10-K/A", "10-Q", "10-Q/A", "20-F", "40-F")

# Forms that say a registrant's history ended by transaction rather than by failure. Form 25 is
# a delisting notice; 15 deregisters; S-4 and DEFM14A accompany a merger. Their presence in a
# registrant's final quarters is weak evidence, and is reported as weak.
EXIT_FORMS = ("25", "25-NSE", "15-12B", "15-12G", "15-15D", "S-4", "DEFM14A")

INDEX_LINE = re.compile(r"^(?P<form>\S+(?:\s\S+)*?)\s{2,}(?P<name>.+?)\s{2,}(?P<cik>\d+)\s{2,}"
                        r"(?P<date>\d{4}-\d{2}-\d{2})\s{2,}(?P<path>\S+)\s*$")


def quarters(start_year, end_year):
    for year in range(start_year, end_year + 1):
        for quarter in range(1, 5):
            yield year, quarter


def parse_form_index(text):
    """CIK, form and name for every filing in one quarterly index."""
    rows = []
    for line in text.splitlines():
        match = INDEX_LINE.match(line)
        if not match:
            continue
        rows.append({"form": match.group("form").strip(),
                     "name": match.group("name").strip(),
                     "cik": str(int(match.group("cik"))).zfill(10),
                     "filed": match.group("date")})
    return rows


def collect(client, start_year, end_year):
    """Per-CIK first and last periodic filing, and any exit forms seen."""
    periodic = defaultdict(lambda: {"first": None, "last": None, "name": None, "count": 0})
    exits = defaultdict(list)
    read, failed = 0, []
    for year, quarter in quarters(start_year, end_year):
        url = f"{SEC_ROOT}/Archives/edgar/full-index/{year}/QTR{quarter}/form.idx"
        try:
            text = client._get(url)  # noqa: SLF001 - same package, one rate limiter
        except Exception as error:  # noqa: BLE001 - a missing future quarter is not fatal
            failed.append({"quarter": f"{year}Q{quarter}", "error": f"{type(error).__name__}"})
            continue
        read += 1
        for row in parse_form_index(text):
            if row["form"] in PERIODIC_FORMS:
                entry = periodic[row["cik"]]
                entry["name"] = entry["name"] or row["name"]
                entry["count"] += 1
                if entry["first"] is None or row["filed"] < entry["first"]:
                    entry["first"] = row["filed"]
                if entry["last"] is None or row["filed"] > entry["last"]:
                    entry["last"] = row["filed"]
            elif row["form"] in EXIT_FORMS:
                exits[row["cik"]].append({"form": row["form"], "filed": row["filed"]})
        LOG.info(f"{year}Q{quarter}: {len(periodic)} periodic filers seen so far")
    return periodic, exits, read, failed


def cohorts(periodic, exits, survivors, *, silent_after_days=540):
    """Attrition by cohort year: filing then, still filing now, and how they left."""
    from datetime import date

    latest = max((entry["last"] for entry in periodic.values() if entry["last"]), default=None)
    if latest is None:
        return {}, []
    cutoff = date.fromisoformat(latest)

    by_year = defaultdict(lambda: {"filers": 0, "still_filing": 0, "gone": 0,
                                   "gone_by_transaction": 0, "gone_silently": 0,
                                   "in_current_ticker_map": 0})
    departed = []
    for cik, entry in periodic.items():
        if not entry["first"] or not entry["last"]:
            continue
        start_year = int(entry["first"][:4])
        gap = (cutoff - date.fromisoformat(entry["last"])).days
        still = gap <= silent_after_days
        for year in range(start_year, int(entry["last"][:4]) + 1):
            bucket = by_year[year]
            bucket["filers"] += 1
            if still:
                bucket["still_filing"] += 1
            else:
                bucket["gone"] += 1
                if exits.get(cik):
                    bucket["gone_by_transaction"] += 1
                else:
                    bucket["gone_silently"] += 1
            if cik in survivors:
                bucket["in_current_ticker_map"] += 1
        if not still:
            departed.append({"cik": cik, "name": entry["name"], "first": entry["first"],
                             "last": entry["last"], "periodic_filings": entry["count"],
                             "exit_forms": exits.get(cik, [])[:3],
                             "in_current_ticker_map": cik in survivors})
    departed.sort(key=lambda row: row["last"], reverse=True)
    return dict(sorted(by_year.items())), departed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-year", type=int, default=2016,
                        help="first year of indexes to read; the price cache starts 2016-08")
    parser.add_argument("--end-year", type=int, default=None)
    parser.add_argument("--silent-after-days", type=int, default=540,
                        help="a registrant this long without a periodic filing has left")
    parser.add_argument("--limit-departed", type=int, default=500,
                        help="how many departed registrants to list individually")
    args = parser.parse_args(argv)

    from datetime import date
    end_year = args.end_year or date.today().year

    client = SecEdgarClient()
    if not client.available:
        raise SystemExit("SEC_USER_AGENT is required by SEC fair-access policy")

    periodic, exits, read, failed = collect(client, args.start_year, end_year)
    survivors = {str(row["cik_str"]).zfill(10) for row in client.ticker_map_rows()}
    by_year, departed = cohorts(periodic, exits, survivors,
                                silent_after_days=args.silent_after_days)

    payload = {
        "generated_at": date.today().isoformat(),
        "settings": {"start_year": args.start_year, "end_year": end_year,
                     "silent_after_days": args.silent_after_days,
                     "periodic_forms": list(PERIODIC_FORMS)},
        "quarters_read": read,
        "quarters_failed": failed,
        "periodic_filers_seen": len(periodic),
        "current_ticker_map_size": len(survivors),
        "cohorts": by_year,
        "departed_count": len(departed),
        "departed": departed[:args.limit_departed],
        "how_to_read": (
            "cohorts[year].filers is every registrant filing periodic reports in that year. "
            "gone is those with no periodic filing in the most recent window, split into "
            "gone_by_transaction (a delisting, deregistration or merger form is on file) and "
            "gone_silently. The research universe is drawn from the current ticker map, so "
            "cohorts[year].filers minus in_current_ticker_map bounds how much of that year's "
            "investable set any backtest in this repository cannot see."),
        "what_this_does_not_give": (
            "Returns for the departed. No price source here serves delisted securities, so "
            "the performance impact of the gap is bounded in count but not measured in "
            "return. Do not scale a backtest by this attrition rate and call it corrected: "
            "an acquisition ends a filing history above the prevailing price and a bankruptcy "
            "ends it near zero, and this cannot tell you the mix with any precision."),
    }
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(COHORTS, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    print(json.dumps({key: payload[key] for key in
                      ("quarters_read", "periodic_filers_seen", "current_ticker_map_size",
                       "departed_count")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
