import pandas as pd
from datetime import datetime, timedelta
from database import ReadOnlySession
from models import User, Facility
from config import DRIFT_WINDOW_DAYS, DRIFT_ALERT_THRESHOLD_RATIO_INC

# Exactly match the event types your main.py treats as overrides
OVERRIDE_EVENT_TYPES = [
    "patient-record-insert",
    "patient-record-update",
    "view",
]

def _get_username_to_numeric_id() -> pd.DataFrame:
    """Return a DataFrame with 'username' → 'numeric_id'."""
    session = ReadOnlySession()
    try:
        df = pd.read_sql(
            session.query(User.id, User.username).statement, session.bind
        )
        df = df.rename(columns={"username": "user_id", "id": "numeric_id"})
        df["user_id"] = df["user_id"].astype(str).str.strip()
        df["numeric_id"] = df["numeric_id"].astype(str)
        return df
    finally:
        session.close()

def _get_user_dept_role() -> pd.DataFrame:
    """Return a DataFrame with 'numeric_id', 'department', and 'role'."""
    session = ReadOnlySession()
    try:
        df = pd.read_sql(
            session.query(
                User.id.label("numeric_id"),
                Facility.name.label("department"),
                User.physician_type.label("role")
            )
            .join(Facility, User.facility_id == Facility.id)
            .statement,
            session.bind
        )
        df["role"] = df["role"].fillna("Clinician")
        df["numeric_id"] = df["numeric_id"].astype(str)
        return df
    finally:
        session.close()

def detect_drift(enriched_events: pd.DataFrame, all_logs: pd.DataFrame,
                 lookback_end: datetime = None) -> pd.DataFrame:
    if lookback_end is None:
        lookback_end = datetime.now()
    window_start = lookback_end - timedelta(days=DRIFT_WINDOW_DAYS)

    # Map raw usernames in all_logs to numeric IDs
    username_map = _get_username_to_numeric_id()
    all_logs = all_logs.copy()
    all_logs["user_id"] = all_logs["user_id"].astype(str).str.strip()
    all_logs = all_logs.merge(username_map, on="user_id", how="left")
    all_logs.rename(columns={"numeric_id": "user_id_numeric"}, inplace=True)

    # Add department and role using numeric ID
    dept_role = _get_user_dept_role()
    all_logs = all_logs.merge(
        dept_role.rename(columns={"numeric_id": "user_id_numeric"}),
        on="user_id_numeric", how="left"
    )

    # Standard events = everything NOT in override list
    standard_access = all_logs[
        ~all_logs["event"].isin(OVERRIDE_EVENT_TYPES)
    ]

    # Current window
    recent_overrides = enriched_events[enriched_events["date"] >= window_start]
    recent_standard = standard_access[standard_access["date"] >= window_start]

    override_counts = recent_overrides.groupby(["department", "role"]).size().rename("override_count")
    standard_counts = recent_standard.groupby(["department", "role"]).size().rename("standard_count")

    ratio_df = pd.concat([override_counts, standard_counts], axis=1).fillna(0)
    ratio_df["ratio"] = ratio_df["override_count"] / ratio_df["standard_count"].replace(0, 1)

    # Baseline window
    baseline_start = window_start - timedelta(days=DRIFT_WINDOW_DAYS)
    baseline_overrides = enriched_events[(enriched_events["date"] >= baseline_start) &
                                         (enriched_events["date"] < window_start)]
    baseline_standard = standard_access[(standard_access["date"] >= baseline_start) &
                                        (standard_access["date"] < window_start)]

    baseline_override_counts = baseline_overrides.groupby(["department", "role"]).size()
    baseline_standard_counts = baseline_standard.groupby(["department", "role"]).size()
    baseline_ratio = (baseline_override_counts / baseline_standard_counts.replace(0, 1)).fillna(0)

    # Determine drift alert
    ratio_df["baseline_ratio"] = baseline_ratio.reindex(ratio_df.index).fillna(0)
    ratio_df["ratio_increase"] = ratio_df["ratio"] - ratio_df["baseline_ratio"]
    ratio_df["drift_alert"] = ratio_df["ratio_increase"] > DRIFT_ALERT_THRESHOLD_RATIO_INC

    ratio_df["ratio"] = round(ratio_df["ratio"], 2)
    ratio_df["baseline_ratio"] = round(ratio_df["baseline_ratio"], 2)
    ratio_df["ratio_increase"] = round(ratio_df["ratio_increase"], 2)

    return ratio_df[ratio_df["drift_alert"]].reset_index()