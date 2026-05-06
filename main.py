import uvicorn
import threading
import time
import pandas as pd
from datetime import datetime, timedelta
from log_ingestion import fetch_audit_logs, check_row_continuity, detect_timestamp_gaps, detect_duplicates
from context_enrichment import enrich_events
from trust_scoring import score_events
from drift_detection import detect_drift
from evidence_packaging import build_package, save_package
from governance_queue import update_queue, app, update_drift_alerts
from config import EXCLUDED_USERS

POLL_INTERVAL_SECONDS = 5          # how often to refresh the queue
PACKAGE_WINDOW_DAYS = 30           # evidence package covers the last X days

last_package_date = None           # track the last calendar day we saved

def run_pipeline():
    """Execute one full EATAL pipeline cycle and update the API data."""
    global last_package_date

    print(f"[{datetime.now().strftime('%H:%M:%S')}] Pipeline running ...")
    try:
        # 1. Ingest logs
        all_logs = fetch_audit_logs(since=datetime.now() - timedelta(days=180))

        # Filter out system users
        all_logs = all_logs[~all_logs["user_id"].isin(EXCLUDED_USERS)]

        PATIENT_ACCESS_EVENTS = [
            "patient-record-insert",
            "patient-record-update",
            "view",
        ]
        overrides = all_logs[all_logs["event"].isin(PATIENT_ACCESS_EVENTS)].copy()

        if overrides.empty:
            update_queue(pd.DataFrame())
            update_drift_alerts(pd.DataFrame())
            return

        # Deduplicate
        overrides["minute"] = overrides["date"].dt.floor("min")
        overrides = overrides.drop_duplicates(subset=["user_id", "patient_id", "minute"])
        overrides = overrides.drop(columns=["minute"])

        # Integrity checks (warnings only)
        prev_count = 0
        if not check_row_continuity(len(overrides), prev_count):
            print("Warning: row count anomaly")
        gaps = detect_timestamp_gaps(overrides)
        if gaps:
            print(f"Warning: timestamp gaps at indices {gaps}")
        dups = detect_duplicates(overrides)
        if dups:
            print(f"Warning: {dups} duplicate rows")

        enriched = enrich_events(overrides)

        scored = score_events(enriched)

        drift = detect_drift(scored, all_logs)

        # save evidence package once a day
        today = datetime.now().date()
        if last_package_date != today:
            now = datetime.now()
            package = build_package(scored, drift,
                                    now - timedelta(days=PACKAGE_WINDOW_DAYS),
                                    now)
            save_package(package)
            last_package_date = today
            print(f"Evidence package saved for {today}")

        # 6. Update the API globals
        update_queue(scored)
        update_drift_alerts(drift)

        print(f"[{datetime.now().strftime('%H:%M:%S')}] Pipeline finished. Queue size: {len(scored)}")
    except Exception as e:
        print(f"Pipeline error: {e}")

if __name__ == "__main__":
    api_thread = threading.Thread(
        target=uvicorn.run,
        args=(app,),
        kwargs={"host": "0.0.0.0", "port": 8000, "log_level": "info"},
        daemon=True
    )
    api_thread.start()
    print("EATAL API started at http://localhost:8000")

    run_pipeline()

    while True:
        time.sleep(POLL_INTERVAL_SECONDS)
        run_pipeline()