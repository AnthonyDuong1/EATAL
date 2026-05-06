import pandas as pd
from datetime import timedelta
from database import ReadOnlySession
from models import User, Encounter, Schedule, Facility
from config import PRIOR_ENCOUNTER_DAYS

def enrich_events(events_df: pd.DataFrame) -> pd.DataFrame:
    session = ReadOnlySession()
    try:
        # Map log.usernames to numeric user IDs
        # Fetch all users: id and username
        users_all = pd.read_sql(
            session.query(User.id, User.username).statement, session.bind
        )
        
        users_all = users_all.rename(columns={"username": "user_id", "id": "numeric_user_id"})

        # Both as string for safe merge
        events_df["user_id"] = events_df["user_id"].astype(str)
        users_all["user_id"] = users_all["user_id"].astype(str)

        # Merge to get the numeric user id
        events_df = events_df.merge(users_all, on="user_id", how="left")

        # Drop the old string username column and replace with numeric id
        events_df = events_df.drop(columns=["user_id"]).rename(columns={"numeric_user_id": "user_id"})
        

        users_query = (
            session.query(User.id.label("user_id"),
                          User.username,
                          User.fname,
                          User.lname,
                          User.physician_type,
                          Facility.name.label("department"))
            .join(Facility, User.facility_id == Facility.id)
        )
        users_df = pd.read_sql(users_query.statement, session.bind)
        users_df["role"] = users_df["physician_type"].fillna("Clinician")

        users_df["name"] = users_df.apply(
            lambda r: f"{r['fname']} {r['lname']}" if pd.notna(r['fname']) and pd.notna(r['lname'])
                      else (r['fname'] if pd.notna(r['fname']) else r['lname'] if pd.notna(r['lname']) else None),
            axis=1
        )
        # If name is still None, fallback to username
        users_df["name"].fillna(users_df["username"], inplace=True)

        events_df = events_df.merge(users_df, on="user_id", how="left")

        encounters = pd.read_sql(
            session.query(Encounter.provider_id, Encounter.pid, Encounter.date).statement,
            session.bind
        )
        encounters["encounter_datetime"] = pd.to_datetime(encounters["date"])

        # Same day encounter
        encounters["encounter_date_dt"] = encounters["encounter_datetime"].dt.date
        events_df["event_date_dt"] = pd.to_datetime(events_df["date"]).dt.date
        events_df["linked_encounter"] = events_df.apply(
            lambda row: ((encounters["pid"] == row["patient_id"]) &
                         (encounters["encounter_date_dt"] == row["event_date_dt"])).any(),
            axis=1
        )

        # Prior encounter within configurable window
        events_df["event_datetime"] = pd.to_datetime(events_df["date"])

        def had_prior_encounter_in_window(row):
            if pd.isna(row["user_id"]):
                return False
            window_start = row["event_datetime"] - timedelta(days=PRIOR_ENCOUNTER_DAYS)
            mask = (
                (encounters["provider_id"] == int(row["user_id"])) &
                (encounters["pid"] == row["patient_id"]) &
                (encounters["encounter_datetime"] >= window_start) &
                (encounters["encounter_datetime"] <= row["event_datetime"])
            )
            return mask.any()

        events_df["prior_encounter_in_window"] = events_df.apply(had_prior_encounter_in_window, axis=1)

        # Shift / schedule
        schedules = pd.read_sql(
            session.query(Schedule.pc_aid, Schedule.pc_eventDate, Schedule.pc_endDate).statement,
            session.bind
        )
        schedules["pc_aid"] = schedules["pc_aid"].astype(str)

        schedules["pc_eventDate"] = pd.to_datetime(schedules["pc_eventDate"], errors="coerce")
        schedules["pc_endDate"]   = pd.to_datetime(schedules["pc_endDate"],   errors="coerce")
        schedules["pc_endDate"] = schedules["pc_endDate"].fillna(schedules["pc_eventDate"])

        def on_shift(row):
            if pd.isna(row["user_id"]):
                return False
            user_str = str(int(row["user_id"]))
            provider_sched = schedules[schedules["pc_aid"] == user_str]
            for _, sched in provider_sched.iterrows():
                if pd.notna(sched["pc_eventDate"]) and pd.notna(sched["pc_endDate"]):
                    if sched["pc_eventDate"].date() <= row["date"].date() <= sched["pc_endDate"].date():
                        return True
            return False

        events_df["on_shift"] = events_df.apply(on_shift, axis=1)

        return events_df
    finally:
        session.close()