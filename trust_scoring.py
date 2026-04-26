import pandas as pd
from config import (
    SCORE_WEIGHT_ROLE_SHIFT,
    SCORE_WEIGHT_ENCOUNTER_LINK,
    SCORE_WEIGHT_TEMP_CONSISTENCY,
    SCORE_WEIGHT_PEER_DEVIATION,
    SCORE_WEIGHT_PRIOR_ENCOUNTER
)

def calculate_trust_score(event: pd.Series, department_peer_mean: float, dept_peer_std: float) -> dict:
    score = 0.0
    
    # Role/shift
    role_shift_score = 100.0 if event["on_shift"] else 0.0
    score += SCORE_WEIGHT_ROLE_SHIFT * role_shift_score

    # Same day encounter
    enc_score = 100.0 if event["linked_encounter"] else 20.0
    score += SCORE_WEIGHT_ENCOUNTER_LINK * enc_score

    # Temporal consistency
    event_hour = event["date"].hour
    temp_score = 70 if 7 <= event_hour <= 19 else 30
    score += SCORE_WEIGHT_TEMP_CONSISTENCY * temp_score

    # Peer deviation
    user_count = event.get("user_override_count", 0)
    if dept_peer_std > 0:
        z_score = abs(user_count - department_peer_mean) / dept_peer_std
        peer_score = max(0, 100 - 25 * z_score)
    else:
        peer_score = 50
    score += SCORE_WEIGHT_PEER_DEVIATION * peer_score

    # Prior encounter in the configurable window
    prior_score = 100.0 if event["prior_encounter_in_window"] else 0.0
    score += SCORE_WEIGHT_PRIOR_ENCOUNTER * prior_score

    score = min(100, max(0, score))
    rationale = (f"Role-shift: {role_shift_score}, Encounter: {enc_score}, "
                 f"Temporal: {temp_score}, Peer: {peer_score:.1f}, "
                 f"PriorEncWindow: {prior_score}")
    return {"score": score, "rationale": rationale}

def score_events(enriched_df: pd.DataFrame) -> pd.DataFrame:
    user_counts = enriched_df.groupby(["department", "user_id"]).size().reset_index(name="user_override_count")
    enriched_df = enriched_df.merge(user_counts, on=["department", "user_id"], how="left")
    dept_stats = user_counts.groupby("department")["user_override_count"].agg(["mean", "std"]).fillna(0)

    scores = []
    for _, row in enriched_df.iterrows():
        dept = row["department"]
        mean_val = dept_stats.loc[dept, "mean"] if dept in dept_stats.index else 0
        std_val = dept_stats.loc[dept, "std"] if dept in dept_stats.index else 0
        result = calculate_trust_score(row, mean_val, std_val)
        scores.append(result)

    enriched_df["trust_score"] = [s["score"] for s in scores]
    enriched_df["score_rationale"] = [s["rationale"] for s in scores]
    return enriched_df.sort_values("trust_score")