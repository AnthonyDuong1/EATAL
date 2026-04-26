from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
import pandas as pd

app = FastAPI(title="EATAL Governance Output API")

review_queue = pd.DataFrame()

def update_queue(scored_events: pd.DataFrame):
    global review_queue
    review_queue = scored_events.copy()

@app.get("/queue", response_class=JSONResponse)
def get_review_queue(limit: int = Query(100, le=500)):
    if review_queue.empty:
        return {"message": "No events available"}
    queue = review_queue.sort_values("trust_score").head(limit)
    output = []
    for _, row in queue.iterrows():
        output.append({
            "event_id": int(row["id"]),
            "clinician_name": row.get("username"),
            "user_id": row.get("user_id"),
            "patient_id": row.get("patient_id"),
            "timestamp": row["date"].isoformat(),
            "trust_score": row["trust_score"],
            "rationale": row["score_rationale"],
            "advisory": "Decision‑support only. Manual review required before any action."
        })
    return output

@app.get("/drift_alerts")
def get_drift_alerts():
    return {"alerts": []}