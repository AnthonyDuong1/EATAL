import hashlib
import pandas as pd
from datetime import datetime, timedelta
from sqlalchemy import text
from database import ReadOnlySession
from config import AUDIT_LOG_TABLE, HASH_SALT, SNAPSHOT_BUCKET_SIZE

def fetch_audit_logs(since: datetime = None) -> pd.DataFrame:
    session = ReadOnlySession()
    try:
        query = f"SELECT * FROM {AUDIT_LOG_TABLE}"
        if since:
            query += " WHERE date >= :since"
            df = pd.read_sql(text(query), session.bind, params={"since": since})
        else:
            df = pd.read_sql(text(query), session.bind)

        df.rename(columns={"user": "user_id"}, inplace=True)  # ← add this
        return df
    finally:
        session.close()

def compute_snapshot_hash(df: pd.DataFrame) -> list:
    hashes = []
    for start in range(0, len(df), SNAPSHOT_BUCKET_SIZE):
        chunk = df.iloc[start:start+SNAPSHOT_BUCKET_SIZE]
        chunk_str = chunk.to_json() + HASH_SALT
        hashes.append(hashlib.sha256(chunk_str.encode()).hexdigest())
    return hashes

def check_row_continuity(current_count: int, previous_count: int) -> bool:
    return current_count >= previous_count

def detect_timestamp_gaps(df: pd.DataFrame, max_gap_minutes: int = 60) -> list:
    df_sorted = df.sort_values("date")
    gaps = df_sorted["date"].diff().dropna()
    large_gaps = gaps[gaps > timedelta(minutes=max_gap_minutes)]
    return large_gaps.index.tolist()

def detect_duplicates(df: pd.DataFrame) -> int:
    return df.duplicated().sum()

def detect_volume_anomaly(df: pd.DataFrame, baseline_avg: float, threshold_factor: float = 2.0) -> bool:
    return len(df) > baseline_avg * threshold_factor or len(df) < baseline_avg / threshold_factor