import os

# OpenEMR Database connection 
DATABASE_URL = "mysql+pymysql://openemr:openemrpass@localhost:3306/openemr"


# Table names
AUDIT_LOG_TABLE = "log"
USER_TABLE = "users"
ENCOUNTER_TABLE = "form_encounter"
SCHEDULE_TABLE = "openemr_postcalendar_events"
FACILITY_TABLE = "facility"

# Ingestion integrity
HASH_SALT = os.getenv("EATAL_HASH_SALT", "eatal-integrity-2025")
SNAPSHOT_BUCKET_SIZE = 5000

# Trust scoring weights (sum to 1.0)
SCORE_WEIGHT_ROLE_SHIFT = 0.2
SCORE_WEIGHT_ENCOUNTER_LINK = 0.15
SCORE_WEIGHT_TEMP_CONSISTENCY = 0.1
SCORE_WEIGHT_PEER_DEVIATION = 0.1
SCORE_WEIGHT_PRIOR_ENCOUNTER = 0.45

# Drift detection
DRIFT_WINDOW_DAYS = 90
DRIFT_ALERT_THRESHOLD_RATIO_INC = 0.2

# Query limits
MAX_REVIEW_QUEUE_ITEMS = 500

# Prior encounter window (days) – how far back to look for a provider‑patient encounter
PRIOR_ENCOUNTER_DAYS = 8

# Risk Thresholds (It'll be in that category if it's lower than the given score)
HIGH_RISK_THRESHOLD = 40
MEDIUM_RISK_THRESHOLD = 75