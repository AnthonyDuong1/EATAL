from sqlalchemy import Column, Integer, String, DateTime, Boolean, Date, ForeignKey
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class AuditLog(Base):
    __tablename__ = "log"
    id = Column(Integer, primary_key=True)
    date = Column(DateTime, index=True)
    event = Column(String(255))
    user_id = Column("user", Integer, index=True)        
    patient_id = Column(Integer, index=True)
    success = Column(Boolean)
    comments = Column(String(1024))

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(255))
    physician_type = Column(String(50))
    main_menu_role = Column(String(50))
    patient_menu_role = Column(String(50))
    facility_id = Column(Integer, ForeignKey("facility.id"))

class Encounter(Base):
    __tablename__ = "form_encounter"
    id = Column(Integer, primary_key=True)
    pid = Column(Integer, ForeignKey("patient_data.pid"))
    date = Column(DateTime)                
    provider_id = Column(Integer)

class Schedule(Base):
    __tablename__ = "openemr_postcalendar_events"
    pc_eid = Column(Integer, primary_key=True)
    pc_aid = Column(String(30))
    pc_eventDate = Column(Date)
    pc_endDate = Column(Date)
    pc_startTime = Column(String(8))
    pc_endTime = Column(String(8))
    pc_facility = Column(Integer)

class Facility(Base):
    __tablename__ = "facility"
    id = Column(Integer, primary_key=True)
    name = Column(String(255))