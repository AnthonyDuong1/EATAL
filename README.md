# EATAL — External Audit & Trust Assessment Layer

EATAL is a read-only governance tool that watches OpenEMR for break-glass and emergency patient-record access. It pulls the audit log, adds context about who the clinician is and whether they had a real reason to look at that patient, gives every access a trust score, and pushes the highest-risk ones into a review queue that compliance officers can actually work through.

It is important to know that EATAL should always be used with manual review. The trust scores, queues, and drift alerts are meant to help a compliance or privacy officer figure out where to look. It should not be used to automatically block access or flag a clinician without a manual review first.

## System description and architecture overview

The pipeline has six stages and they run end-to-end every time you start `main.py`:

1. **Log ingestion** (`log_ingestion.py`): opens a read-only SQL session against OpenEMR, pulls rows from the `log` table, and runs a few sanity checks: SHA-256 chunk hashes for integrity, a row-count continuity check, timestamp gap detection, and a duplicate count.
2. **Context enrichment** (`context_enrichment.py`): joins the audit rows against the `users`, `facility`, `form_encounter`, and `openemr_postcalendar_events` tables. Each event ends up tagged with the clinician's role, their department, whether there was a same-day encounter for that patient, whether there was a prior encounter within the configurable window, and whether the clinician was on shift at the time.
3. **Trust scoring** (`trust_scoring.py`): gives each access a score from 0 to 100 based on five weighted factors. Lower score = higher risk.
4. **Drift detection** (`drift_detection.py`): looks at the ratio of overrides to normal access per department over a rolling 90-day window and compares it to the previous 90 days. If a department's ratio jumps by more than the configured threshold, it gets flagged.
5. **Evidence packaging** (`evidence_packaging.py`): bundles everything (period totals, top-N riskiest incidents, drift alerts) into a JSON file with a timestamped name.
6. **Governance queue** (`governance_queue.py`): a small FastAPI service that exposes `/queue` and `/drift_alerts` so reviewers can pull the ranked list. Every queue item carries an advisory note saying it's decision support only.

```
        OpenEMR DB (read-only SQL)
          │           │
          ▼           ▼   
   log_ingestion → context_enrichment → trust_scoring
                                              │
                       drift_detection ◄──────┤
                              │               │
                              ▼               ▼
                       evidence_packaging (.json)
                              │
                              ▼
                       governance_queue API
                       (/queue, /drift_alerts)
```

### How the trust score works

The score is a weighted sum of five things, all defined in `config.py`:

| Factor | Weight |
|---|---|
| Prior encounter with this patient in the last 10 days | 0.45 |
| Clinician was on shift | 0.20 |
| Same-day encounter for this patient | 0.15 |
| Access happened during business hours (07:00–19:59) | 0.10 |
| Peer deviation (z-score against department peers) | 0.10 |

Prior encounter is weighted heaviest because in our experience it's the single strongest signal of whether an override was legitimate. The weights sum to 1.0 and you can retune them in `config.py` without touching code anywhere else.

### Read-only by construction

We didn't want EATAL to be able to touch OpenEMR even by accident, so the read-only constraint shows up in three places:

- The SQLAlchemy engine is created with `isolation_level="READ UNCOMMITTED"`.
- Every connection runs `SET SESSION TRANSACTION READ ONLY` on connect (see `database.py`).
- There are no `INSERT`, `UPDATE`, `DELETE`, or DDL statements anywhere in the source.

If somebody pointed EATAL at a writable account by accident, the session-level read-only setting would still block writes.

## Installation

You need:

- Python 3.10 or newer

Setup:

You need to clone this github: https://github.com/kabartsjc/cyseOpenEMR

After, you need to edit the docker-compose.yml so that you can expose the 3306 port of the mariadb by adding the following under the mariadb section:

```
ports:
  - "3306:3306"
```

```bash
git clone https://github.com/AnthonyDuong1/EATAL.git
cd EATAL

python -m venv .venv
source .venv/bin/activate         # Windows: .venv\Scripts\activate

pip install -r packages.txt
```

The packages inside `packages.txt` are:

```
sqlalchemy
pymysql
pandas
fastapi
uvicorn
```

Then open `config.py` and point `DATABASE_URL` at your OpenEMR DB. The default is the local Docker one (`mysql+pymysql://openemr:openemrpass@localhost:3306/openemr`).

A couple of other things in `config.py` you might want to change:

- `HASH_SALT`: used in the integrity hashing.
- `DRIFT_WINDOW_DAYS` (default 90) and `DRIFT_ALERT_THRESHOLD_RATIO_INC` (default 0.20): control how sensitive the drift detector is.
- `PRIOR_ENCOUNTER_DAYS` (default 10): how far back to look for a prior provider–patient encounter.
- The five `SCORE_WEIGHT_*` values, if you want to tune the scoring.


## Execution and demo instructions

Once the venv is active and `DATABASE_URL` is pointed at OpenEMR:

```bash
python main.py
```

That single command runs the whole pipeline:

1. Pulls the last 180 days of audit log entries.
2. Filters down to patient-record access events (`patient-record-insert`, `patient-record-update`, `view`) and drops anything from the `admin` user.
3. De-duplicates within the same `(user_id, patient_id, minute)` so that a single click that produces two log rows isn't counted twice.
4. Runs the integrity checks. If row count went backwards it raises a warning. If there are timestamp gaps over 60 minutes or duplicate rows, we'll also get a warning.
5. Enriches and scores everything.
6. Runs drift detection by comparing the last 90 days to the 90 days before that.
7. Writes a JSON audit package to the working directory.
8. Loads the scored events into the in-memory queue and starts the FastAPI server on `http://localhost:8000`.

After it's running, you can hit the API:

```bash
# Top 100 highest-risk events (lowest trust scores)
curl http://localhost:8000/queue

# Cap the response
curl "http://localhost:8000/queue?limit=20"

curl http://localhost:8000/drift_alerts
```

There's also an auto-generated Swagger docs at `http://localhost:8000/docs` if you want to mess around in a browser.


## Example inputs and expected outputs

In our example, we followed the docker-based testbed's minimal working setup (https://github.com/kabartsjc/cyseOpenEMR#openemr-minimal-working-setup) to enter data. We then setup the "In office" hours for the clinicians, where doctor1 is in SYN Clinic 1 and made sure his "In office" hours started a week before the current date and that repeated to an arbitrary end date. We then did the same for doctor2, but he was assigned to SYN Clinic 2 and made sure his "In office" hours started today. This makes it so we can assign an encounter for doctor1 with a patient before today's date (we did around a week before), where EATAL can pick this context up when both clinicians try to access that patient. The example output is below:

**The JSON audit package** that `evidence_packaging.build_package` writes:

```json
{
  "period_start": "2026-03-27T11:44:00.123458",
  "period_end":   "2026-04-26T11:44:00.123475",
  "total_overrides": 2,
  "by_role_department": {
    "general_physician|SYN Clinic 1": 1,
    "general_physician|SYN Clinic 2": 1
  },
  "top_n_incidents": [
    {
      "user_id": "6",
      "clinician_name": "doctor2",
      "patient_id": "3.0",
      "timestamp": "2026-04-26T10:59:24",
      "score": 15.0,
      "rationale": "Role-shift: 0.0, Encounter: 20.0, Temporal: 70, Peer: 50.0, PriorEncWindow: 0.0"
    },
    {
      "user_id": "5",
      "clinician_name": "doctor1",
      "patient_id": "3.0",
      "timestamp": "2026-04-26T10:57:00",
      "score": 80.0,
      "rationale": "Role-shift: 100.0, Encounter: 20.0, Temporal: 70, Peer: 50.0, PriorEncWindow: 100.0"
    }
  ],
  "drift_indicators": []
}
```

Walking through that example: `doctor2` ended up with 15/100 because the access was off-shift, there was no same-day encounter, and no prior encounter in the 10-day window. Only the temporal-consistency factor (it happened during business hours) saved any points. `doctor1` accessed the same patient two minutes earlier but scored 80/100 because he was on shift and had a prior encounter with that patient, which is a much more defensible reason to break glass. A reviewer working from this output would skip `doctor1` and start asking questions about `doctor2`.

**The `/queue` API response** for the same event:

```json
[
  {
    "event_id": 7421,
    "clinician_name": "doctor2",
    "user_id": 6,
    "patient_id": 3,
    "timestamp": "2026-04-26T10:59:24",
    "trust_score": 15.0,
    "rationale": "Role-shift: 0.0, Encounter: 20.0, Temporal: 70, Peer: 50.0, PriorEncWindow: 0.0",
    "advisory": "Decision-support only. Manual review required before any action."
  }
]
```

**A drift alert**, when one fires:

| department | ratio | baseline_ratio | ratio_increase | drift_alert |
|---|---|---|---|---|
| SYN Clinic 2 | 0.41 | 0.18 | 0.23 | True |

Read this as: SYN Clinic 2's override-to-normal-access ratio went from 0.18 in the baseline period to 0.41 in the current window. That's a 0.23 jump, which is above the 0.20 threshold, so it gets surfaced. In practice this is the signal that a department is starting to treat break-glass as routine, which is exactly the behavior the layer is supposed to catch.
