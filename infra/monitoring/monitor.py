import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from highwayvlm.storage import (
    get_archive_overview,
    init_db,
    list_hourly_snapshots,
    list_incident_events,
)


def _fmt_ts(value):
    if not value:
        return "--"
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return str(value)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _print_json(payload):
    print(json.dumps(payload, ensure_ascii=True, indent=2))


def cmd_summary(args):
    payload = get_archive_overview(camera_id=args.camera_id or None)
    _print_json(payload)


def cmd_hourly(args):
    rows = list_hourly_snapshots(limit=args.limit, camera_id=args.camera_id or None)
    if args.json:
        _print_json(rows)
        return
    if not rows:
        print("No hourly snapshots found.")
        return
    for row in rows:
        camera = row.get("camera_name") or row.get("camera_id") or "unknown"
        hour_bucket = _fmt_ts(row.get("hour_bucket"))
        status = row.get("status") or "unknown"
        incidents = row.get("incident_count") or 0
        print(f"[{hour_bucket}] {camera} | status={status} | incident_count={incidents}")
        reports = row.get("incident_reports") or []
        for report in reports:
            kind = report.get("incident_type") or report.get("report_kind") or "unknown"
            severity = report.get("severity") or "unknown"
            description = report.get("description") or "No description"
            print(f"  - {kind} ({severity}): {description}")
        if row.get("error"):
            print(f"  - error: {row['error']}")
        if row.get("skipped_reason"):
            print(f"  - skipped_reason: {row['skipped_reason']}")


def cmd_incidents(args):
    rows = list_incident_events(limit=args.limit, camera_id=args.camera_id or None)
    if args.json:
        _print_json(rows)
        return
    if not rows:
        print("No incident events found.")
        return
    for row in rows:
        camera = row.get("camera_name") or row.get("camera_id") or "unknown"
        created_at = _fmt_ts(row.get("created_at"))
        incident_type = row.get("incident_type") or "unknown"
        severity = row.get("severity") or "unknown"
        description = row.get("description") or "No description"
        print(f"[{created_at}] {camera} | {incident_type} ({severity})")
        print(f"  - {description}")


def cmd_watch(args):
    print(f"Watching updates every {args.interval}s. Press Ctrl+C to stop.")
    try:
        while True:
            print("\n=== Overview ===")
            cmd_summary(args)
            print("\n=== Latest Hourly Rows ===")
            hourly_args = argparse.Namespace(
                camera_id=args.camera_id,
                limit=args.limit,
                json=False,
            )
            cmd_hourly(hourly_args)
            print("\n=== Latest Incidents ===")
            incident_args = argparse.Namespace(
                camera_id=args.camera_id,
                limit=min(args.limit, 20),
                json=False,
            )
            cmd_incidents(incident_args)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nStopped.")


def build_parser():
    parser = argparse.ArgumentParser(
        description="Monitor HighwayVLM incident and hourly snapshot report archives."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    summary = subparsers.add_parser("summary", help="Show archive totals and latest timestamps.")
    summary.add_argument("--camera-id", default="", help="Optional camera id filter.")
    summary.set_defaults(func=cmd_summary)

    hourly = subparsers.add_parser("hourly", help="Show hourly snapshot records with incident reports.")
    hourly.add_argument("--camera-id", default="", help="Optional camera id filter.")
    hourly.add_argument("--limit", type=int, default=20, help="Max rows to display.")
    hourly.add_argument("--json", action="store_true", help="Print raw JSON.")
    hourly.set_defaults(func=cmd_hourly)

    incidents = subparsers.add_parser("incidents", help="Show incident event records.")
    incidents.add_argument("--camera-id", default="", help="Optional camera id filter.")
    incidents.add_argument("--limit", type=int, default=20, help="Max rows to display.")
    incidents.add_argument("--json", action="store_true", help="Print raw JSON.")
    incidents.set_defaults(func=cmd_incidents)

    watch = subparsers.add_parser("watch", help="Continuously refresh summary + hourly + incident records.")
    watch.add_argument("--camera-id", default="", help="Optional camera id filter.")
    watch.add_argument("--limit", type=int, default=10, help="Max rows shown per section.")
    watch.add_argument("--interval", type=int, default=60, help="Refresh interval in seconds.")
    watch.set_defaults(func=cmd_watch)

    return parser


def main():
    init_db()
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
