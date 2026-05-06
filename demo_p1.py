"""
Set up a single patient with:
 - Cardiology facility (needed for future doctors)
 - Patient: given name, DOB, and sex
 - No doctors, encounters, or schedules (add them separately)
"""
from sqlalchemy import create_engine, text

DB_URL = "mysql+pymysql://openemr:openemrpass@localhost:3306/openemr"
engine = create_engine(DB_URL)

PATIENT_PID = 201                   
PATIENT_FNAME = "Alex"            
PATIENT_LNAME = "Doe"            
PATIENT_DOB = "1985-07-24"         
PATIENT_SEX = "Male"                

def setup():
    with engine.begin() as conn:
        # 1. Delete only secondary data (you can keep existing doctors)
        conn.execute(text("DELETE FROM openemr_postcalendar_events"))
        conn.execute(text("DELETE FROM form_encounter"))
        conn.execute(text("DELETE FROM log"))
        conn.execute(text("DELETE FROM patient_data"))
        conn.execute(text("DELETE FROM users_secure WHERE id IN (5, 6)"))
        conn.execute(text("DELETE FROM users_facility WHERE table_id IN (5, 6) AND tablename = 'users'"))
        conn.execute(text("DELETE FROM users WHERE id IN (5, 6)"))

        # 2. Ensure the Cardiology facility exists (future doctors need it)
        conn.execute(text(
            "INSERT IGNORE INTO facility (id, name) VALUES (3, 'Cardiology')"
        ))
        conn.execute(text(
            "UPDATE facility SET name = 'Cardiology' WHERE id = 3"
        ))

        # 3. Create (or update) the patient
        conn.execute(text(
            "INSERT INTO patient_data (pid, fname, lname, DOB, sex, street) "
            "VALUES (:pid, :fname, :lname, :dob, :sex, '123 Testing Lane') "
            "ON DUPLICATE KEY UPDATE "
            "fname = :fname2, lname = :lname2, DOB = :dob2, sex = :sex2"
        ), {
            "pid": PATIENT_PID,
            "fname": PATIENT_FNAME, "lname": PATIENT_LNAME,
            "dob": PATIENT_DOB, "sex": PATIENT_SEX,
            "fname2": PATIENT_FNAME, "lname2": PATIENT_LNAME,
            "dob2": PATIENT_DOB, "sex2": PATIENT_SEX
        })

    print(f"Patient {PATIENT_FNAME} {PATIENT_LNAME} (pid={PATIENT_PID}) created/updated.")
    print("Facility 'Cardiology' is ready for doctors.")

if __name__ == "__main__":
    setup()