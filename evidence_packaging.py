import json
from datetime import datetime
import pandas as pd
from config import TOP_N_INCIDENTS

def build_package(scored_events: pd.DataFrame, drift_alerts: pd.DataFrame,
                  period_start: datetime, period_end: datetime) -> dict:

    role_dept_counts = scored_events.groupby(["role", "department"]).size()
    by_role_dept = {
        f"{role}|{dept}": count
        for (role, dept), count in role_dept_counts.items()
    }

    package = {
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "total_overrides": len(scored_events),
        "by_role_department": by_role_dept,
        "top_n_incidents": [],
        "drift_indicators": drift_alerts.to_dict(orient="records"),
    }

    # Top‑N override incidents (lower trust scores = higher risk)
    top_n = scored_events.nsmallest(TOP_N_INCIDENTS, "trust_score")
    for _, row in top_n.iterrows():
        user_id = row["user_id"]
        patient_id = row["patient_id"]
        package["top_n_incidents"].append({
            "user_id": str(user_id) if pd.notna(user_id) else None,
            "clinician_name": row.get("username", "Unknown"),
            "patient_id": str(patient_id) if pd.notna(patient_id) else None,
            "timestamp": row["date"].isoformat(),
            "score": row["trust_score"],
            "rationale": row["score_rationale"]
        })
    return package

def save_package(package: dict, filename: str = None):
    """Save package as JSON, sanitising the timestamp for Windows filenames."""
    if not filename:
        safe_time = package['period_end'].replace(":", "-").replace(".", "-")
        filename = f"audit_package_{safe_time}.json"
    with open(filename, "w") as f:
        json.dump(package, f, indent=2)
    return filename
