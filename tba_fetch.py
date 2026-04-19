#!/usr/bin/env python3
"""
TBA Data Fetcher - FRC Mid-Atlantic District
Fetches schedules, results, component OPRs, and rankings for all
regular season events and the district championship.

Usage:
    export TBA_API_KEY=your_key_here
    python tba_fetch.py [--year 2025] [--district mar]

Get a free API key at: https://www.thebluealliance.com/account
"""

import os
import sys
import json
import time
import argparse
import requests
from pathlib import Path

TBA_BASE = "https://www.thebluealliance.com/api/v3"

# FRC event types from TBA
EVENT_TYPE_DISTRICT = 1
EVENT_TYPE_DISTRICT_CMP = 2


class TBAClient:
    def __init__(self, api_key: str):
        self.session = requests.Session()
        self.session.headers.update({"X-TBA-Auth-Key": api_key})
        self._last_request = 0.0

    def get(self, endpoint: str):
        # Stay under TBA's rate limit (~20 req/s)
        elapsed = time.monotonic() - self._last_request
        if elapsed < 0.05:
            time.sleep(0.05 - elapsed)

        url = f"{TBA_BASE}/{endpoint}"
        try:
            resp = self.session.get(url, timeout=15)
            self._last_request = time.monotonic()
        except requests.RequestException as e:
            print(f"  [network error] {endpoint}: {e}")
            return None

        if resp.status_code == 200:
            return resp.json()
        if resp.status_code == 304:
            return None  # not modified
        if resp.status_code == 404:
            print(f"  [404] {endpoint}")
            return None
        print(f"  [HTTP {resp.status_code}] {endpoint}")
        return None


def save(data, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"    saved {path}")


def fetch_event(client: TBAClient, event_key: str, out: Path, include_coprs: bool = True):
    """Fetch schedule, results, OPRs, component OPRs, and rankings for one event."""

    # Full match objects (includes score breakdown — the component-level data)
    matches = client.get(f"event/{event_key}/matches")
    if matches:
        # Split into schedule (unplayed) and results (played)
        played = [m for m in matches if m.get("actual_time") is not None]
        unplayed = [m for m in matches if m.get("actual_time") is None]
        save(unplayed, out / "schedule.json")
        save(played, out / "results.json")
        save(matches, out / "matches_full.json")

    # Standard OPR / DPR / CCWM
    oprs = client.get(f"event/{event_key}/oprs")
    if oprs:
        save(oprs, out / "oprs.json")

    # Component OPRs (auto, teleop, endgame broken out per team)
    if include_coprs:
        coprs = client.get(f"event/{event_key}/coprs")
        if coprs:
            save(coprs, out / "coprs.json")

    # Event rankings (final standing at this event)
    rankings = client.get(f"event/{event_key}/rankings")
    if rankings:
        save(rankings, out / "rankings.json")


def fetch_district(client: TBAClient, district_key: str, out: Path):
    print(f"\nDistrict: {district_key}")

    events = client.get(f"district/{district_key}/events")
    if not events:
        print("ERROR: Could not fetch events. Check your API key and district key.")
        sys.exit(1)
    save(events, out / "events.json")

    regular = sorted(
        [e for e in events if e.get("event_type") == EVENT_TYPE_DISTRICT],
        key=lambda e: e.get("start_date", ""),
    )
    champ = next(
        (e for e in events if e.get("event_type") == EVENT_TYPE_DISTRICT_CMP), None
    )

    print(f"  {len(regular)} regular season events, district championship: {champ['key'] if champ else 'not found'}")

    # ── Regular season events ─────────────────────────────────────────────────
    for event in regular:
        key = event["key"]
        name = event.get("short_name") or event.get("name") or key
        dates = f"{event.get('start_date','')} → {event.get('end_date','')}"
        print(f"\n  [{key}] {name}  ({dates})")
        fetch_event(client, key, out / "regular_season" / key)

    # ── District Championship ─────────────────────────────────────────────────
    if champ:
        key = champ["key"]
        name = champ.get("short_name") or champ.get("name") or key
        print(f"\n  [{key}] {name}  (district championship)")
        fetch_event(client, key, out / "district_championship")
    else:
        print("\n  No district championship event found (may not have occurred yet).")

    # ── District-wide rankings ─────────────────────────────────────────────────
    print("\n  Fetching district point rankings...")
    district_rankings = client.get(f"district/{district_key}/rankings")
    if district_rankings:
        save(district_rankings, out / "district_rankings.json")
        print(f"    {len(district_rankings)} teams ranked")

    print(f"\nDone. All data saved under: {out}/")


def main():
    parser = argparse.ArgumentParser(description="Fetch FRC Mid-Atlantic district data from TBA")
    parser.add_argument("--year", type=int, default=2025, help="Season year (default: 2025)")
    parser.add_argument("--district", default="mar", help="District code (default: mar)")
    parser.add_argument("--out", default="data", help="Output directory (default: data/)")
    args = parser.parse_args()

    api_key = os.environ.get("TBA_API_KEY", "").strip()
    if not api_key:
        print("ERROR: Set the TBA_API_KEY environment variable.")
        print("       Get a free key at https://www.thebluealliance.com/account")
        sys.exit(1)

    district_key = f"{args.year}{args.district}"
    out = Path(args.out) / district_key

    client = TBAClient(api_key)
    fetch_district(client, district_key, out)


if __name__ == "__main__":
    main()
