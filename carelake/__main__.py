"""carelake <stage>: generate | land | scrub | serve | feeds | ship | all"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date

from carelake import adls, curate, feeds, generate, land, serve, settings


def say(msg: str) -> None:
    print(msg, flush=True)


def _cohort(a) -> generate.Cohort:
    if a.weekly:
        return generate.weekly_cohort(date.today(), a.size)
    return generate.Cohort(
        label=a.label, seed=a.seed, size=a.size, as_of=date.fromisoformat(a.as_of), state=a.state
    )


def _labels(p, a) -> list[str]:
    if getattr(a, "cohort", None):
        return [a.cohort]
    found = generate.labels(p)
    if not found:
        say("no cohorts under data/raw; run `carelake generate` first")
        sys.exit(2)
    return found


def stage_generate(a) -> None:
    generate.run_synthea(settings.paths(), _cohort(a), say)


def stage_land(a) -> None:
    p = settings.paths()
    for label in _labels(p, a):
        land.land_cohort(p, label, say)


def stage_scrub(a) -> None:
    p = settings.paths()
    for label in _labels(p, a):
        curate.curate_cohort(p, label, settings.scrub_secret(), say)


def stage_serve(a) -> None:
    p = settings.paths()
    result = serve.run_dbt(p, say)
    serve.export_marts(p, say)
    (p.data / "dbt_result.json").write_text(json.dumps(result, indent=1), encoding="utf-8")


def stage_feeds(a) -> None:
    p = settings.paths()
    f = p.data / "dbt_result.json"
    result = json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
    feeds.write_feeds(p, result, generate.labels(p), settings.feed_base_url(), extend=not a.fresh, say=say)


def stage_ship(a) -> None:
    account, key = settings.adls()
    adls.ship(settings.paths(), settings.sink(), account, key, say=say)


def stage_all(a) -> None:
    p = settings.paths()
    cohort = _cohort(a)
    generate.run_synthea(p, cohort, say)
    labels = [cohort.label] if a.only else generate.labels(p)
    for label in labels:
        if a.force or not land.manifest_file(p, label).exists():
            land.land_cohort(p, label, say)
        else:
            say(f"raw {label}: already landed (use --force to redo)")
        curate.curate_cohort(p, label, settings.scrub_secret(), say)
    result = serve.run_dbt(p, say)
    serve.export_marts(p, say)
    (p.data / "dbt_result.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    feeds.write_feeds(p, result, labels, settings.feed_base_url(), extend=not a.fresh, say=say)
    account, key = settings.adls()
    adls.ship(p, settings.sink(), account, key, say=say)


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="carelake", description=__doc__)
    sub = ap.add_subparsers(dest="stage", required=True)

    def cohort_args(sp):
        sp.add_argument("--size", type=int, default=1500, help="living patients to generate (default 1500)")
        sp.add_argument("--seed", type=int, default=7)
        sp.add_argument("--label", default="il-7", help="cohort folder name")
        sp.add_argument("--as-of", default="2026-11-21", help="the day Synthea treats as today")
        sp.add_argument("--state", default="Illinois")
        sp.add_argument(
            "--weekly", action="store_true", help="label, seed and as-of from the current ISO week"
        )

    g = sub.add_parser("generate", help="run Synthea for a cohort")
    cohort_args(g)
    g.set_defaults(run=stage_generate)
    for name, fn, help_ in (
        ("land", stage_land, "bundles -> raw + rejects"),
        ("scrub", stage_scrub, "raw -> curated"),
    ):
        sp = sub.add_parser(name, help=help_)
        sp.add_argument("--cohort")
        sp.set_defaults(run=fn)
    sub.add_parser("serve", help="dbt build + export marts").set_defaults(run=stage_serve)
    f = sub.add_parser("feeds", help="write web/feeds/status.json and history.json")
    f.add_argument(
        "--fresh",
        action="store_true",
        help="start the history from scratch instead of extending the published one",
    )
    f.set_defaults(run=stage_feeds)
    sub.add_parser("ship", help="upload the lake to ADLS Gen2").set_defaults(run=stage_ship)
    al = sub.add_parser("all", help="every stage in order")
    cohort_args(al)
    al.add_argument("--force", action="store_true")
    al.add_argument(
        "--only", action="store_true", help="serve just this cohort, ignore others under data/raw"
    )
    al.add_argument("--fresh", action="store_true")
    al.set_defaults(run=stage_all)
    return ap


def main(argv: list[str] | None = None) -> int:
    a = parser().parse_args(argv)
    a.run(a)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
