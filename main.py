import uvicorn
import pandas as pd
from datetime import datetime, timedelta
from log_ingestion import fetch_audit_logs, check_row_continuity, detect_timestamp_gaps, detect_duplicates
from context_enrichment import enrich_events
from trust_scoring import score_events
from drift_detection import detect_drift
from evidence_packaging import build_package, save_package
from governance_queue import update_queue, app

if __name__ == "__main__":
    # 1. Ingest logs
    all_logs = fetch_audit_logs(since=datetime.now() - timedelta(days=180))
    PATIENT_ACCESS_EVENTS = [
        "patient-record-insert",
        "patient-record-update",
        "view",
    ]   
    overrides = all_logs[all_logs["event"].isin(PATIENT_ACCESS_EVENTS)].copy()

    overrides = overrides[overrides["user_id"] != "admin"]

    overrides["minute"] = overrides["date"].dt.floor("min")
    overrides = overrides.drop_duplicates(subset=["user_id", "patient_id", "minute"])
    overrides = overrides.drop(columns=["minute"])

    # Ingestion integrity checks – adjust prev_count as needed
    prev_count = 0   # dummy; in production, load from persistent store
    if not check_row_continuity(len(overrides), prev_count):
        raise RuntimeError("Row count anomaly detected")
    gaps = detect_timestamp_gaps(overrides)
    if gaps:
        print(f"Warning: timestamp gaps at indices {gaps}")
    dups = detect_duplicates(overrides)
    if dups:
        print(f"Warning: {dups} duplicate rows found")

    enriched = enrich_events(overrides)

    scored = score_events(enriched)

    drift = detect_drift(scored, all_logs)

    # Evidence package for the last 30 days
    package = build_package(scored, drift, datetime.now() - timedelta(days=30), datetime.now())
    save_package(package)

    # Update governance queue
    update_queue(scored)

    # Start the governance API
    uvicorn.run(app, host="localhost", port=8000)