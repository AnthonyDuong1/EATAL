import pandas as pd
from datetime import datetime, timedelta
from database import ReadOnlySession
from models import User, Facility
from config import DRIFT_WINDOW_DAYS, DRIFT_ALERT_THRESHOLD_RATIO_INC

def get_user_departments() -> pd.DataFrame:
    
    session = ReadOnlySession()
    try:
        query = (session.query(User.id.label("user_id"), Facility.name.label("department"))
                 .join(Facility, User.facility_id == Facility.id))
        df = pd.read_sql(query.statement, session.bind)
        
        df["user_id"] = df["user_id"].astype(str)
        return df
    finally:
        session.close()

def detect_drift(enriched_events: pd.DataFrame, all_logs: pd.DataFrame,
                 lookback_end: datetime = None) -> pd.DataFrame:
    if lookback_end is None:
        lookback_end = datetime.now()
    window_start = lookback_end - timedelta(days=DRIFT_WINDOW_DAYS)


    user_dept = get_user_departments()

    # Ensure all_logs user_id is also string
    all_logs = all_logs.copy()
    all_logs["user_id"] = all_logs["user_id"].astype(str)

    all_logs_enriched = all_logs.merge(user_dept, on="user_id", how="left")

    recent_overrides = enriched_events[enriched_events["date"] >= window_start]
    recent_standard = all_logs_enriched[(all_logs_enriched["date"] >= window_start) &
                                        (all_logs_enriched["event"] != "break-glass-override")]

    override_counts = recent_overrides.groupby("department").size().rename("override_count")
    standard_counts = recent_standard.groupby("department").size().rename("standard_count")
    ratio = (override_counts / standard_counts).fillna(0).to_frame("ratio")

    # Baseline period
    baseline_start = window_start - timedelta(days=DRIFT_WINDOW_DAYS)
    baseline_overrides = enriched_events[(enriched_events["date"] >= baseline_start) &
                                         (enriched_events["date"] < window_start)]
    baseline_standard = all_logs_enriched[(all_logs_enriched["date"] >= baseline_start) &
                                          (all_logs_enriched["date"] < window_start) &
                                          (all_logs_enriched["event"] != "break-glass-override")]

    baseline_override_counts = baseline_overrides.groupby("department").size()
    baseline_standard_counts = baseline_standard.groupby("department").size()
    baseline_ratio = (baseline_override_counts / baseline_standard_counts).fillna(0)

    ratio["baseline_ratio"] = baseline_ratio
    ratio["ratio_increase"] = ratio["ratio"] - ratio["baseline_ratio"]
    ratio["drift_alert"] = ratio["ratio_increase"] > DRIFT_ALERT_THRESHOLD_RATIO_INC
    return ratio[ratio["drift_alert"]].reset_index()