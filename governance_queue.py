from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, JSONResponse
import pandas as pd
from config import ( HIGH_RISK_THRESHOLD, MEDIUM_RISK_THRESHOLD )

app = FastAPI(title="EATAL Governance Output API")

review_queue = pd.DataFrame()

def update_queue(scored_events: pd.DataFrame):
    global review_queue
    review_queue = scored_events.copy()
    # Add the advisory column directly to the DataFrame
    review_queue["advisory"] = "Decision-support only. Manual review required before any action."

# ---------- Helper: generate HTML page ----------
def render_html_table(df: pd.DataFrame) -> str:
    """Build an HTML table with colour-coded rows."""
    rows_html = ""
    for _, row in df.iterrows():
        score = row["trust_score"]
        # Determine colour class
        if score <= HIGH_RISK_THRESHOLD:
            row_class = "high-risk"      # red
        elif score <= MEDIUM_RISK_THRESHOLD:
            row_class = "medium-risk"    # yellow
        else:
            row_class = "low-risk"       # green

        rows_html += f"""
        <tr class="{row_class}">
            <td>{int(row['id'])}</td>
            <td>{row.get("name", row.get("username", "N/A"))}</td>
            <td>{int(row['user_id']) if pd.notna(row.get('user_id')) else 'N/A'}</td>
            <td>{int(row['patient_id']) if pd.notna(row.get('patient_id')) else 'N/A'}</td>
            <td>{row['date'].strftime('%Y-%m-%d %H:%M:%S')}</td>
            <td>{row['trust_score']:.1f}</td>
            <td class="rationale">{row['score_rationale']}</td>
            <td class="advisory">{row['advisory']}</td>
        </tr>"""

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>EATAL Review Queue</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; }}
            h1 {{ color: #333; }}
            table {{ border-collapse: collapse; width: 100%; }}
            th, td {{ border: 1px solid #ccc; padding: 8px; text-align: left; }}
            th {{ background-color: #f2f2f2; }}
            .high-risk {{ background-color: #ffcccc; }}   /* light red */
            .medium-risk {{ background-color: #ffffcc; }} /* light yellow */
            .low-risk {{ background-color: #ccffcc; }}    /* light green */
            .rationale {{ font-size: 0.9em; }}
            .advisory {{ font-style: italic; color: #555; }}
        </style>
    </head>
    <body>
        <h1>EATAL Governance Review Queue</h1>
        <p>Risk‑ranked list of potential break‑glass events (lowest score = highest risk first).</p>
        <table>
            <tr>
                <th>Event ID</th>
                <th>Clinician</th>
                <th>User ID</th>
                <th>Patient ID</th>
                <th>Timestamp</th>
                <th>Trust Score</th>
                <th>Rationale</th>
                <th>Advisory</th>
            </tr>
            {rows_html}
        </table>
    </body>
    </html>
    """
    return html

# ---------- Endpoints ----------
@app.get("/queue", response_class=HTMLResponse)
def get_review_queue(limit: int = Query(100, le=500)):
    """Return a colour-coded HTML page."""
    if review_queue.empty:
        return HTMLResponse("<h1>No events available</h1>")
    queue = review_queue.sort_values("trust_score").head(limit)
    return HTMLResponse(render_html_table(queue))

@app.get("/queue/json", response_class=JSONResponse)
def get_review_queue_json(limit: int = Query(100, le=500)):
    """Original JSON endpoint (kept for API access)."""
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
            "advisory": row["advisory"]
        })
    return output

@app.get("/drift_alerts")
def get_drift_alerts():
    return {"alerts": []}