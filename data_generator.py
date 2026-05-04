"""
Populate the cyseOpenEMR testbed with synthetic data that:
 - Triggers a drift alert for Cardiology Physicians.
 - Produces three target trust‑score cases (~30, ~60, ~90).
"""
import random
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text

DB_URL = "mysql+pymysql://openemr:openemrpass@localhost:3306/openemr"
engine = create_engine(DB_URL)

# ---------- Constants ----------
TODAY = datetime.now().replace(hour=23, minute=59, second=59)
PRIOR_WINDOW = 30             # must match PRIOR_ENCOUNTER_DAYS in config.py
DRIFT_WINDOW = 90

# Event types that EATAL treats as potential overrides
OVERRIDE_EVENTS = [
    "patient-record-select",
    "patient-record-insert",
    "patient-record-update",
    "view",
]
# Standard (non‑override) event types
STANDARD_EVENTS = [
    "login", "logout", "view-record", "order-select",
    "other-insert", "other-update", "scheduling-select",
    "security-administration-select",
]

# ---------- Helper ----------
def random_minute(day, hour=None):
    """Return a datetime on a given day with a random minute."""
    h = hour if hour is not None else random.randint(6, 20)
    m = random.randint(0, 59)
    return day.replace(hour=h, minute=m, second=0, microsecond=0)

# ---------- Main ----------
def populate():
    with engine.begin() as conn:
        # 1. Clean up (keep users & facilities if they exist, we'll reuse them)
        conn.execute(text("DELETE FROM openemr_postcalendar_events"))
        conn.execute(text("DELETE FROM form_encounter"))
        conn.execute(text("DELETE FROM log"))

        # 2. Ensure facilities exist (ID 3 = Cardiology, as in your testbed)
        for fid, name in [(3, "Cardiology"), (4, "Neurology")]:
            conn.execute(text(
                "INSERT IGNORE INTO facility (id, name) VALUES (:id, :name)"
            ), {"id": fid, "name": name})

        # 3. Ensure clinicians exist (doctor1=ID5, doctor2=ID6, etc.)
        #    If they already exist, IGNORE will skip.
        clinicians = [
            (5, "doctor1", "general_physician", 3),  # Cardiology
            (6, "doctor2", "general_physician", 3),  # Cardiology
            (7, "nurse1",   "nurse",           3),  # Cardiology (optional)
        ]
        for uid, uname, ptype, fid in clinicians:
            conn.execute(text(
                "INSERT IGNORE INTO users (id, username, physician_type, "
                "main_menu_role, patient_menu_role, facility_id) "
                "VALUES (:id, :uname, :ptype, 'standard', 'standard', :fid)"
            ), {"id": uid, "uname": uname, "ptype": ptype, "fid": fid})

        # 4. Create two patients (IDs 101, 102)
        for pid, fname in [(101, "DemoPatient1"), (102, "DemoPatient2")]:
            conn.execute(text(
                "INSERT IGNORE INTO patient_data (pid, fname, lname, DOB, street) "
                "VALUES (:pid, :fname, 'Test', '1990-01-01', '123 Demo St')"
            ), {"pid": pid, "fname": fname})

        # 5. Schedules: doctor1 (ID=5) works every weekday 7‑19 for 180 days
        for delta in range(180):
            day = (TODAY - timedelta(days=delta)).date()
            if day.weekday() < 5:  # Mon-Fri
                conn.execute(text(
                    "INSERT INTO openemr_postcalendar_events "
                    "(pc_aid, pc_eventDate, pc_endDate, pc_startTime, pc_endTime, pc_facility) "
                    "VALUES ('5', :start, :end, '07:00:00', '19:00:00', 3)"
                ), {"start": day, "end": day})

        # 6. Encounters – used for prior_encounter_in_window and same‑day linkage
        now = TODAY
        # doctor1 (5) saw patient101 5 days ago → prior encounter true
        encounter_date = now - timedelta(days=5)
        conn.execute(text(
            "INSERT INTO form_encounter (pid, date, provider_id, encounter) "
            "VALUES (101, :enc, 5, 'Office Visit')"
        ), {"enc": encounter_date})
        # doctor1 also saw patient101 today (for same‑day encounter flag)
        conn.execute(text(
            "INSERT INTO form_encounter (pid, date, provider_id, encounter) "
            "VALUES (101, :enc, 5, 'Office Visit')"
        ), {"enc": now})

        # doctor2 (6) saw patient102 40 days ago → outside PRIOR_WINDOW (30 days)
        conn.execute(text(
            "INSERT INTO form_encounter (pid, date, provider_id, encounter) "
            "VALUES (102, :enc, 6, 'Office Visit')"
        ), {"enc": now - timedelta(days=40)})

        # 7. Baseline window events (days -180 to -91)
        baseline_start = now - timedelta(days=DRIFT_WINDOW*2)
        baseline_end = now - timedelta(days=DRIFT_WINDOW+1)

        current_day = baseline_start
        while current_day <= baseline_end:
            # Add many standard events
            for _ in range(random.randint(40, 60)):
                uid = random.choice([5, 6, 7])
                evt = random.choice(STANDARD_EVENTS)
                conn.execute(text(
                    "INSERT INTO log (date, event, user, patient_id, success) "
                    "VALUES (:t, :evt, :uid, 0, 1)"
                ), {"t": random_minute(current_day), "evt": evt, "uid": uid})

            # A few override events to create a small baseline ratio (~5%)
            if random.random() < 0.3:
                for _ in range(random.randint(1, 3)):
                    uid = random.choice([5, 6])     # doctors only
                    evt = random.choice(OVERRIDE_EVENTS)
                    pid = random.choice([101, 102])
                    conn.execute(text(
                        "INSERT INTO log (date, event, user, patient_id, success) "
                        "VALUES (:t, :evt, :uid, :pid, 1)"
                    ), {"t": random_minute(current_day), "evt": evt, "uid": uid, "pid": pid})
            current_day += timedelta(days=1)

        # 8. Current window events (days -90 to today) – spike overrides
        current_start = now - timedelta(days=DRIFT_WINDOW)
        current_day = current_start
        while current_day <= now:
            # Same amount of standard events as baseline to keep denominator stable
            for _ in range(random.randint(40, 60)):
                uid = random.choice([5, 6, 7])
                evt = random.choice(STANDARD_EVENTS)
                conn.execute(text(
                    "INSERT INTO log (date, event, user, patient_id, success) "
                    "VALUES (:t, :evt, :uid, 0, 1)"
                ), {"t": random_minute(current_day), "evt": evt, "uid": uid})

            # Deliberately high override count → ratio spikes > 0.2
            for _ in range(random.randint(5, 10)):
                uid = random.choice([5, 6])     # Cardiology physicians
                evt = random.choice(OVERRIDE_EVENTS)
                pid = random.choice([101, 102])
                conn.execute(text(
                    "INSERT INTO log (date, event, user, patient_id, success) "
                    "VALUES (:t, :evt, :uid, :pid, 1)"
                ), {"t": random_minute(current_day), "evt": evt, "uid": uid, "pid": pid})
            current_day += timedelta(days=1)

        # 9. The three “demo” override events (each at a unique minute)
        # Event A → target trust ~30
        #   doctor2 (6) opens patient101, no prior enc (doctor2 never saw 101),
        #   on_shift=False (weekend), no same‑day enc, time 3 AM (temp_score=30)
        demo_day = now - timedelta(days=1)
        # Make demo_day a weekend (Saturday)
        # Find a Saturday
        while demo_day.weekday() < 5:   # 0=Mon, 5=Sat, 6=Sun
            demo_day -= timedelta(days=1)
        evt_a_time = demo_day.replace(hour=10, minute=59)
        conn.execute(text(
            "INSERT INTO log (date, event, user, patient_id, success, comments) "
            "VALUES (:t, 'patient-record-select', 'doctor2', 101, 1, 'Demo A - low trust')"
        ), {"t": evt_a_time})

        # Event B → target trust ~60
        #   doctor1 (5) opens patient102, prior enc = False (never saw 102),
        #   on_shift=True (weekday), same‑day enc = False, time 10 AM (temp=70)
        demo_day = now - timedelta(days=2)
        while demo_day.weekday() >= 5:  # find a weekday
            demo_day -= timedelta(days=1)
        evt_b_time = demo_day.replace(hour=10, minute=25)
        conn.execute(text(
            "INSERT INTO log (date, event, user, patient_id, success, comments) "
            "VALUES (:t, 'patient-record-select', 'doctor1', 102, 1, 'Demo B - medium trust')"
        ), {"t": evt_b_time})

        # Event C → target trust ~90 (high)
        #   doctor1 (5) opens patient101, prior enc = True (encounter 5 days ago),
        #   on_shift=True (weekday), same‑day enc = True (encounter today), time 14:00 (temp=70)
        evt_c_time = now.replace(hour=14, minute=40)
        conn.execute(text(
            "INSERT INTO log (date, event, user, patient_id, success, comments) "
            "VALUES (:t, 'patient-record-select', 'doctor1', 101, 1, 'Demo C - high trust')"
        ), {"t": evt_c_time})

    print("✅ Demo data created!")
    print("- Cardiology Physicians: drift alert expected (baseline ratio ~0.05, current ~0.3)")
    print("- Check http://localhost:8000/queue for trust scores near 30, 60, 90")
    print("- Also check http://localhost:8000/drift_alerts for the drift alert")

if __name__ == "__main__":
    populate()
