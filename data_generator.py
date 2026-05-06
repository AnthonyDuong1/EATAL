"""
Minimal demo data for EATAL with active drift alert (reproducible).
 - Drift alert: Cardiology Physicians, ratio increase ≈ 0.35
 - Queue after dedup: 2 red, 3 yellow, 2 green
 - 08:00‑20:00 In‑Office schedules for Bob Altman (doctor1)
 - Fixed seed ensures identical output every run.
"""
import random
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text

DB_URL = "mysql+pymysql://openemr:openemrpass@localhost:3306/openemr"
engine = create_engine(DB_URL)

TODAY = datetime.now().replace(hour=23, minute=59, second=59)
DRIFT_WINDOW = 90

STANDARD_EVENTS = [
    "login", "logout", "view-record", "order-select",
    "other-insert", "other-update", "scheduling-select",
    "security-administration-select",
]

USERNAMES = {5: "doctor1", 6: "doctor2"}

# UI‑matching serialised schedule strings
RECUR_SPEC = (
    'a:6:{s:17:"event_repeat_freq";s:1:"0";s:22:"event_repeat_freq_type";s:1:"0";'
    's:19:"event_repeat_on_num";s:1:"1";s:19:"event_repeat_on_day";s:1:"0";'
    's:20:"event_repeat_on_freq";s:1:"0";s:6:"exdate";s:0:"";}'
)
LOCATION_SERIALISED = (
    'a:6:{s:14:"event_location";s:0:"";s:13:"event_street1";s:0:"";'
    's:13:"event_street2";s:0:"";s:10:"event_city";s:0:"";'
    's:11:"event_state";s:0:"";s:12:"event_postal";s:0:"";}'
)

def random_minute(day, hour=None):
    h = hour if hour is not None else random.randint(6, 20)
    m = random.randint(0, 59)
    return day.replace(hour=h, minute=m, second=0, microsecond=0)

def get_in_office_category_id(conn):
    row = conn.execute(text(
        "SELECT pc_catid FROM openemr_postcalendar_categories WHERE pc_catname = 'In Office'"
    )).fetchone()
    if not row:
        raise RuntimeError("'In Office' category not found.")
    return row[0]

def populate():
    random.seed(2500)

    with engine.begin() as conn:
        # 1. Clean up
        conn.execute(text("DELETE FROM openemr_postcalendar_events"))
        conn.execute(text("DELETE FROM form_encounter"))
        conn.execute(text("DELETE FROM log"))

        # 2. Facilities – Cardiology
        conn.execute(text("INSERT IGNORE INTO facility (id, name) VALUES (3, 'Cardiology')"))
        conn.execute(text("UPDATE facility SET name = 'Cardiology' WHERE id = 3"))

        # 3. Clinicians
        clinicians = [
            (5, "doctor1", "general_physician", 3, "Bob", "Altman"),
            (6, "doctor2", "general_physician", 3, "Jordan", "Gilbert"),
        ]
        for uid, uname, ptype, fid, fname, lname in clinicians:
            conn.execute(text(
                "INSERT IGNORE INTO users (id, username, physician_type, main_menu_role, "
                "patient_menu_role, facility_id) VALUES (:id, :uname, :ptype, 'standard', 'standard', :fid)"
            ), {"id": uid, "uname": uname, "ptype": ptype, "fid": fid})

        for uid, uname, ptype, fid, fname, lname in clinicians:
            conn.execute(text("""
                UPDATE users SET fname=:fname, lname=:lname,
                facility=(SELECT name FROM facility WHERE id=:fid),
                facility_id=:fid, calendar=1, active=1, see_auth=1, authorized=1
                WHERE id=:uid
            """), {"fname": fname, "lname": lname, "fid": fid, "uid": uid})

        for uid, _, _, fid, _, _ in clinicians:
            conn.execute(text(
                "INSERT IGNORE INTO users_facility (tablename, table_id, facility_id) "
                "VALUES ('users', :uid, :fid)"
            ), {"uid": uid, "fid": fid})

        # 4. Patients
        for pid, fname in [(101, "DemoPatient1"), (102, "DemoPatient2")]:
            conn.execute(text(
                "INSERT IGNORE INTO patient_data (pid, fname, lname, DOB, street) "
                "VALUES (:pid, :fname, 'Test', '1990-01-01', '123 Demo St')"
            ), {"pid": pid, "fname": fname})

        # 5. Schedules – doctor1 08:00‑20:00 every weekday for 180 days
        cat_id = get_in_office_category_id(conn)
        for delta in range(180):
            day = (TODAY - timedelta(days=delta)).date()
            if day.weekday() < 5:
                conn.execute(text(
                    "INSERT INTO openemr_postcalendar_events "
                    "(pc_aid, pc_eventDate, pc_endDate, pc_startTime, pc_endTime, "
                    " pc_facility, pc_multiple, pc_catid, pc_eventstatus, pc_sharing, "
                    " pc_duration, pc_title, pc_informant, pc_pid, pc_hometext, pc_time, "
                    " pc_recurrspec, pc_location, pc_billing_location) "
                    "VALUES (TRIM('5'), :start, :end, '08:00:00', '20:00:00', "
                    " 3, 0, :cat, 1, 1, TIME_TO_SEC(TIMEDIFF('20:00:00','08:00:00')), "
                    " 'In Office', 1, '', '', NOW(), :recur, :loc, 3)"
                ), {"start": day, "end": day, "cat": cat_id, "recur": RECUR_SPEC, "loc": LOCATION_SERIALISED})

        # 6. Encounters
        now = TODAY
        # Green event prior encounter
        encounter_date = now - timedelta(days=5)
        conn.execute(text(
            "INSERT INTO form_encounter (pid, date, provider_id) VALUES (101, :enc, 5)"
        ), {"enc": encounter_date})
        conn.execute(text(
            "INSERT INTO form_encounter (pid, date, provider_id) VALUES (101, :enc, 5)"
        ), {"enc": now})

        # 7. Baseline window – 10 standard events + 1 red override
        baseline_start = now - timedelta(days=DRIFT_WINDOW * 2)
        baseline_end   = now - timedelta(days=DRIFT_WINDOW + 1)
        day = baseline_start
        while day <= baseline_end:
            if day.weekday() < 5 and random.random() < 0.11:   # ~10 events (fixed by seed)
                uname = USERNAMES[random.choice([5, 6])]
                evt = random.choice(STANDARD_EVENTS)
                conn.execute(text(
                    "INSERT INTO log (date, event, user, patient_id, success) "
                    "VALUES (:t, :evt, :user, 0, 1)"
                ), {"t": random_minute(day), "evt": evt, "user": uname})
            day += timedelta(days=1)

        # Baseline override: doctor2, Saturday 3 AM
        baseline_sat = baseline_start
        while baseline_sat.weekday() != 5:
            baseline_sat += timedelta(days=1)
        conn.execute(text(
            "INSERT INTO log (date, event, user, patient_id, success) "
            "VALUES (:t, 'view', 'doctor2', 101, 1)"
        ), {"t": baseline_sat.replace(hour=3, minute=0)})

        # 8. Current window – 20 standard events (low enough for drift alert)
        current_start = now - timedelta(days=DRIFT_WINDOW)
        day = current_start
        while day <= now:
            if day.weekday() < 5 and random.random() < 0.22:   # ~20 events
                uname = USERNAMES[random.choice([5, 6])]
                evt = random.choice(STANDARD_EVENTS)
                conn.execute(text(
                    "INSERT INTO log (date, event, user, patient_id, success) "
                    "VALUES (:t, :evt, :user, 0, 1)"
                ), {"t": random_minute(day), "evt": evt, "user": uname})
            day += timedelta(days=1)

        # ---- RED events (2 distinct minutes) ----
        red_sat = current_start
        while red_sat.weekday() != 5:
            red_sat += timedelta(days=1)
        for _ in range(10):   # duplicates, only 1 queue row
            conn.execute(text(
                "INSERT INTO log (date, event, user, patient_id, success, comments) "
                "VALUES (:t, 'view', 'doctor2', 101, 1, 'Red auto')"
            ), {"t": red_sat.replace(hour=3, minute=10)})

        # Demo A: red
        demo_sat = now - timedelta(days=1)
        while demo_sat.weekday() != 5:
            demo_sat -= timedelta(days=1)
        for _ in range(5):
            conn.execute(text(
                "INSERT INTO log (date, event, user, patient_id, success, comments) "
                "VALUES (:t, 'view', 'doctor2', 101, 1, 'Demo A - low trust')"
            ), {"t": demo_sat.replace(hour=3, minute=15)})

        # ---- YELLOW events (3 distinct minutes, each with same‑day encounter) ----
        yellow_days = []
        d = current_start
        while d <= now and len(yellow_days) < 3:
            if d.weekday() < 5:
                yellow_days.append(d)
            d += timedelta(days=1)

        for i, day in enumerate(yellow_days):
            minute = 30 + i
            # Same‑day encounter for patient102
            conn.execute(text(
                "INSERT INTO form_encounter (pid, date, provider_id) VALUES (102, :enc, 6)"
            ), {"enc": day.replace(hour=9, minute=0)})
            for _ in range(10):
                conn.execute(text(
                    "INSERT INTO log (date, event, user, patient_id, success, comments) "
                    "VALUES (:t, 'view', 'doctor1', 102, 1, 'Yellow auto')"
                ), {"t": day.replace(hour=10, minute=minute)})

        # Demo B: yellow
        demo_weekday = now - timedelta(days=2)
        while demo_weekday.weekday() >= 5:
            demo_weekday -= timedelta(days=1)
        conn.execute(text(
            "INSERT INTO form_encounter (pid, date, provider_id) VALUES (102, :enc, 6)"
        ), {"enc": demo_weekday.replace(hour=9, minute=0)})
        for _ in range(5):
            conn.execute(text(
                "INSERT INTO log (date, event, user, patient_id, success, comments) "
                "VALUES (:t, 'view', 'doctor1', 102, 1, 'Demo B - medium trust')"
            ), {"t": demo_weekday.replace(hour=10, minute=28)})

        # ---- GREEN events (2 distinct minutes) ----
        green_day = now
        while green_day.weekday() >= 5:
            green_day -= timedelta(days=1)
        for _ in range(10):
            conn.execute(text(
                "INSERT INTO log (date, event, user, patient_id, success, comments) "
                "VALUES (:t, 'view', 'doctor1', 101, 1, 'Green auto')"
            ), {"t": green_day.replace(hour=14, minute=45)})

        for _ in range(5):
            conn.execute(text(
                "INSERT INTO log (date, event, user, patient_id, success, comments) "
                "VALUES (:t, 'view', 'doctor1', 101, 1, 'Demo C - high trust')"
            ), {"t": green_day.replace(hour=14, minute=42)})

        # Trim whitespace
        conn.execute(text("UPDATE log SET user = TRIM(user)"))

    print("Demo data created!")
    print("   http://localhost:8000/queue and /drift_alerts")

if __name__ == "__main__":
    populate()