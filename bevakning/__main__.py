"""python -m bevakning [--dry-run]"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from .config import load_config
from .http import PoliteClient
from .notify import NtfyNotifier, listing_lines, listing_title
from .runner import RunReport, run
from .sources import default_sources
from .state import State


def print_report(report: RunReport, labels: dict[str, str], dry_run: bool) -> None:
    fetched = " · ".join(f"{labels.get(k, k)} {v}" for k, v in report.fetched.items()) or "inget"
    print(f"Hämtade annonser: {fetched}")
    for name, err in report.failed.items():
        print(f"⚠️  {labels.get(name, name)} misslyckades: {err}")
    for name in report.initialized:
        print(f"Första körningen för {labels.get(name, name)}: alla annonser markerade som sedda, inga notiser.")
    heading = "Matchningar just nu" if dry_run else "Nya matchningar"
    print(f"\n{heading}: {len(report.matches)}")
    for m in sorted(report.matches, key=lambda m: (not m.is_new, m.listing.source, m.listing.rent_sek or 0)):
        flag = "NY   " if m.is_new else "sedd "
        print(f"\n[{flag}] {listing_title(m.listing)}")
        for line in listing_lines(m.listing, m.markers):
            print(f"        {line}")
        print(f"        {m.listing.url}")
    if not dry_run:
        print(f"\nNotiser skickade: {report.notified}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m bevakning",
                                 description="Bevakar lediga hyreslägenheter i Örebro.")
    ap.add_argument("--dry-run", action="store_true",
                    help="skriv ut matchningar utan att skicka notiser eller ändra state")
    ap.add_argument("--config", default="config.yaml", type=Path)
    ap.add_argument("--state", default="data/seen.json", type=Path)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")

    cfg = load_config(args.config)
    state = State.load(args.state)
    client = PoliteClient()
    notifier = None
    if not args.dry_run:
        topic = os.environ.get("NTFY_TOPIC", "").strip()
        if not topic:
            print("Fel: miljövariabeln NTFY_TOPIC saknas (använd --dry-run för att testa).", file=sys.stderr)
            return 2
        notifier = NtfyNotifier(os.environ.get("NTFY_SERVER") or "https://ntfy.sh", topic, client)

    sources = default_sources(client)
    report = run(cfg, state, sources, notifier, now=datetime.now(timezone.utc), dry_run=args.dry_run)
    print_report(report, {s.name: s.label for s in sources}, args.dry_run)

    if not args.dry_run:
        print("State sparad." if state.save(args.state) else "State oförändrad.")
    return 1 if report.failed and not report.fetched else 0


if __name__ == "__main__":
    sys.exit(main())
