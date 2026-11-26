#!/usr/bin/env python3
"""Read and update tracker.csv safely.

  python3 scripts/tracker.py list [--status found] [--verdict apply]
  python3 scripts/tracker.py set <job_id> verdict=apply fit_score=78 status=triaged notes="..."
  python3 scripts/tracker.py summary          # triaged jobs ranked by fit_score
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TRACKER = ROOT / "tracker.csv"
VERDICTS = {"apply", "stretch", "skip", ""}
STATUSES = {"found", "triaged", "prepared", "filled", "submitted", "skipped", "rejected", "interview", "offer"}


def load() -> tuple[list[str], list[dict]]:
    if not TRACKER.exists():
        sys.exit("tracker.csv not found. Run scripts/fetch_jobs.py first.")
    with TRACKER.open(newline="") as f:
        r = csv.DictReader(f)
        return list(r.fieldnames or []), list(r)


def save(fields: list[str], rows: list[dict]) -> None:
    tmp = TRACKER.with_suffix(".csv.tmp")
    with tmp.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    tmp.replace(TRACKER)


def cmd_list(args) -> None:
    _, rows = load()
    for r in rows:
        if args.status and r["status"] != args.status:
            continue
        if args.verdict and r["verdict"] != args.verdict:
            continue
        print(f"{r['job_id']}\t{r['status']}\t{r['verdict'] or '-'}\t{r['fit_score'] or '-'}\t{r['company']}\t{r['title']}\t{r['location']}")


def cmd_set(args) -> None:
    fields, rows = load()
    updates = {}
    for kv in args.pairs:
        if "=" not in kv:
            sys.exit(f"Expected key=value, got {kv!r}")
        k, v = kv.split("=", 1)
        if k not in fields or k == "job_id":
            sys.exit(f"Unknown or read-only field {k!r}. Fields: {fields}")
        if k == "verdict" and v not in VERDICTS:
            sys.exit(f"verdict must be one of {sorted(VERDICTS - {''})}")
        if k == "status" and v not in STATUSES:
            sys.exit(f"status must be one of {sorted(STATUSES)}")
        if k == "fit_score" and v and not (v.isdigit() and 0 <= int(v) <= 100):
            sys.exit("fit_score must be an integer 0-100")
        updates[k] = v
    for r in rows:
        if r["job_id"] == args.job_id:
            r.update(updates)
            save(fields, rows)
            print(f"updated {args.job_id}: {updates}")
            return
    sys.exit(f"job_id {args.job_id!r} not in tracker.csv")


def cmd_summary(args) -> None:
    _, rows = load()
    done = [r for r in rows if r["verdict"]]
    order = {"apply": 0, "stretch": 1, "skip": 2}
    done.sort(key=lambda r: (order.get(r["verdict"], 3), -int(r["fit_score"] or 0)))
    print("| # | Verdict | Fit | Company | Title | Location | job_id |")
    print("|---|---|---|---|---|---|---|")
    for i, r in enumerate(done, 1):
        print(f"| {i} | {r['verdict']} | {r['fit_score']} | {r['company']} | {r['title']} | {r['location']} | {r['job_id']} |")
    pending = sum(1 for r in rows if r["status"] == "found")
    print(f"\n{len(done)} triaged, {pending} awaiting triage.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("list"); p.add_argument("--status"); p.add_argument("--verdict"); p.set_defaults(fn=cmd_list)
    p = sub.add_parser("set"); p.add_argument("job_id"); p.add_argument("pairs", nargs="+"); p.set_defaults(fn=cmd_set)
    p = sub.add_parser("summary"); p.set_defaults(fn=cmd_summary)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
