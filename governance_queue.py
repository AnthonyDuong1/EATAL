from fastapi import FastAPI, Query, Response
from fastapi.responses import HTMLResponse, JSONResponse
import pandas as pd
from config import HIGH_RISK_THRESHOLD, MEDIUM_RISK_THRESHOLD

app = FastAPI(title="EATAL Governance Output API")

review_queue = pd.DataFrame()
drift_alerts = []          # list of dicts from detect_drift()

# ---------- Queue functions ----------
def update_queue(scored_events: pd.DataFrame):
    global review_queue
    review_queue = scored_events.copy()
    review_queue["advisory"] = "Decision‑support only. Manual review required before any action."

def update_drift_alerts(drift_df: pd.DataFrame):
    global drift_alerts
    if drift_df is None or drift_df.empty:
        drift_alerts = []
    else:
        drift_alerts = drift_df.to_dict(orient="records")


# ---------- HTML table for the queue ----------
def render_html_table(df: pd.DataFrame) -> str:
    rows_html = ""
    for _, row in df.iterrows():
        score = row["trust_score"]
        if score <= HIGH_RISK_THRESHOLD:
            row_class = "high-risk"
        elif score <= MEDIUM_RISK_THRESHOLD:
            row_class = "medium-risk"
        else:
            row_class = "low-risk"

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
            table {{ border-collapse: collapse; width: 100%; margin-bottom: 30px; }}
            th, td {{ border: 1px solid #ccc; padding: 8px; text-align: left; }}
            th {{ background-color: #f2f2f2; }}
            .high-risk {{ background-color: #ffcccc; }}
            .medium-risk {{ background-color: #ffffcc; }}
            .low-risk {{ background-color: #ccffcc; }}
            .rationale {{ font-size: 0.9em; }}
            .advisory {{ font-style: italic; color: #555; }}
        </style>
        <script>
            setTimeout(function(){{
                window.location.reload();
            }}, 5000);
        </script>
    </head>
    <body>
        <h1>EATAL Governance Review Queue</h1>
        <p>Risk-ranked list of potential break-glass events (lowest score = highest risk first).</p>
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


# ---------- HTML page for drift alerts ----------
def render_drift_html(alerts: list) -> str:
    if not alerts:
        return HTMLResponse("<h1>No drift alerts</h1>").body

    df = pd.DataFrame(alerts)
    departments = df["department"].unique()

    tables_html = ""
    for dept in sorted(departments):
        dept_df = df[df["department"] == dept]
        rows = ""
        for _, row in dept_df.iterrows():
            is_alert = row.get("drift_alert", False)
            row_class = "alert-row" if is_alert else ""

            rows += f"""
            <tr class="{row_class}">
                <td>{row.get('role', 'Clinician')}</td>
                <td>{int(row.get('override_count', 0))}</td>
                <td>{int(row.get('standard_count', 0))}</td>
                <td>{row.get('ratio', 0):.3f}</td>
                <td>{row.get('baseline_ratio', 0):.3f}</td>
                <td>{row.get('ratio_increase', 0):.3f}</td>
            </tr>"""

        tables_html += f"""
        <h2>{dept}</h2>
        <table>
            <thead>
                <tr>
                    <th>Role</th>
                    <th>Overrides</th>
                    <th>Standard Accesses</th>
                    <th>Current Ratio</th>
                    <th>Baseline Ratio</th>
                    <th>Ratio Increase</th>
                </tr>
            </thead>
            <tbody>
                {rows}
            </tbody>
        </table>
        """

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>EATAL Behavioral Drift Alerts</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; }}
            h1 {{ color: #333; }}
            h2 {{ margin-top: 30px; }}
            table {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; }}
            th, td {{ border: 1px solid #ccc; padding: 8px; text-align: left; }}
            th {{ background-color: #f2f2f2; }}
            .alert-row {{ background-color: #ffcccc; }}
        </style>
        <script>
            setTimeout(function(){{
                window.location.reload();
            }}, 5000);
        </script>
    </head>
    <body>
        <h1>EATAL Behavioral Drift Alerts</h1>
        <p>Break‑glass override ratio by department and role. Rows highlighted in red indicate a drift alert.</p>
        {tables_html}
    </body>
    </html>
    """
    return html


# ---------- Endpoints ----------
@app.get("/queue", response_class=HTMLResponse)
def get_review_queue(limit: int = Query(100, le=500)):
    if review_queue.empty:
        response = HTMLResponse("<h1>No events available</h1>")
    else:
        queue = review_queue.sort_values("trust_score").head(limit)
        response = HTMLResponse(render_html_table(queue))
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@app.get("/drift_alerts", response_class=HTMLResponse)
def get_drift_alerts_page():
    if not drift_alerts:
        response = HTMLResponse("<h1>No drift data available</h1>")
    else:
        response = HTMLResponse(render_drift_html(drift_alerts))
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response