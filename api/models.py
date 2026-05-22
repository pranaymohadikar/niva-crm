"""
Database models — Changed 2026-05-04
=====================================
Added Staff table for coaches, HPs, CS agents, ISA owners.
All person references now have both ID (foreign key) and name (readability).
"""

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime, timezone, timedelta

Base = declarative_base()

# IST timezone helper — Added 2026-05-06
IST = timezone(timedelta(hours=5, minutes=30))
def now_ist():
    return datetime.now(IST).replace(tzinfo=None)  # Store without tz info for SQLite compatibility


class User(Base):
    """Login users — Changed 2026-05-05: added staff_id link"""
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(200), nullable=False)
    name = Column(String(200), nullable=False)
    role = Column(String(50), nullable=False)
    staff_id = Column(Integer, ForeignKey("staff.id"), nullable=True)  # Link to staff record — Added 2026-05-05
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=now_ist)


class Staff(Base):
    """All staff: coaches, HPs, CS agents, ISA owners — Added 2026-05-04
    type values: diet_coach, wellness_coach, physio_coach, health_partner, cs_agent, isa_owner
    """
    __tablename__ = "staff"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    type = Column(String(50), nullable=False)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=now_ist)


class Patient(Base):
    """Core patient record — Changed 2026-05-04: added isa_owner_id"""
    __tablename__ = "patients"
    id = Column(Integer, primary_key=True)
    patient_name = Column(String(300), nullable=False)
    contact_number = Column(String(20), nullable=False)
    alt_number = Column(String(20))
    condition_type = Column(String(100))
    plan_purchase_date = Column(String(20))
    plan_duration = Column(String(50))
    plan_price = Column(String(20))
    expiry_date = Column(String(20))
    # ISA owner — both ID and name — Changed 2026-05-04
    isa_owner_id = Column(Integer, ForeignKey("staff.id"), nullable=True)
    isa_owner = Column(String(200))
    mode_of_payment = Column(String(50))
    rm_call_booked = Column(String(10))
    sales_remarks = Column(Text)
    payment_month = Column(String(20))
    week_no = Column(String(10))
    created_at = Column(DateTime, default=now_ist)
    created_by = Column(String(100))

    rm_data = relationship("RMData", uselist=False, back_populates="patient", cascade="all,delete")
    wc_attempts = relationship("WCAttempt", back_populates="patient", cascade="all,delete", order_by="WCAttempt.attempt_number")
    coaching = relationship("CoachingData", back_populates="patient", cascade="all,delete")
    weekly_entries = relationship("WeeklyEntry", back_populates="patient", cascade="all,delete", order_by="WeeklyEntry.week_number")
    audit_entries = relationship("AuditLog", back_populates="patient", cascade="all,delete")


class RMData(Base):
    """RM operational data — Changed 2026-05-04: added ID fields for HP and CS agent"""
    __tablename__ = "rm_data"
    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), unique=True, nullable=False)
    # Health partner — both ID and name
    health_partner_id = Column(Integer, ForeignKey("staff.id"), nullable=True)
    health_partner = Column(String(200))
    welcome_call_booked_timestamp = Column(String(50))
    welcome_call_done = Column(String(10))
    welcome_call_completion_date = Column(String(20))
    welcome_call_booked_not_completed = Column(String(10))
    metabolic_assessment = Column(String(10))
    final_remarks = Column(Text)
    diet_coach_assignment = Column(Text)
    wellness_coach_assignment = Column(Text)
    physio_coach_assignment = Column(Text)
    # CS agent — both ID and name
    cs_agent_id = Column(Integer, ForeignKey("staff.id"), nullable=True)
    cs_agent = Column(String(200))
    cs_call_date = Column(String(20))
    cs_call_time = Column(String(20))
    cs_remarks = Column(Text)

    patient = relationship("Patient", back_populates="rm_data")


class WCAttempt(Base):
    """Welcome call attempts — Created 2026-05-04"""
    __tablename__ = "wc_attempts"
    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    attempt_number = Column(Integer, nullable=False)
    date = Column(String(20))
    time = Column(String(20))
    remarks = Column(Text)

    patient = relationship("Patient", back_populates="wc_attempts")


class CoachingData(Base):
    """Coaching module data — Changed 2026-05-04: added coach_id and cs_agent_id"""
    __tablename__ = "coaching_data"
    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    module = Column(String(20), nullable=False)
    # Coach — both ID and name
    coach_id = Column(Integer, ForeignKey("staff.id"), nullable=True)
    coach = Column(String(200))
    status = Column(String(200))
    current_status = Column(Text)
    appointment_remarks = Column(Text)
    head_coach_comment = Column(Text)
    # CS agent — both ID and name
    cs_agent_id = Column(Integer, ForeignKey("staff.id"), nullable=True)
    cs_agent = Column(String(200))
    cs_call_date = Column(String(20))
    cs_call_time = Column(String(20))
    cs_remarks = Column(Text)

    patient = relationship("Patient", back_populates="coaching")
    monthly_cycles = relationship("MonthlyCycle", back_populates="coaching_data", cascade="all,delete", order_by="MonthlyCycle.month_number")


class MonthlyCycle(Base):
    """Monthly assessment cycle — Created 2026-05-04"""
    __tablename__ = "monthly_cycles"
    id = Column(Integer, primary_key=True)
    coaching_id = Column(Integer, ForeignKey("coaching_data.id"), nullable=False)
    month_number = Column(Integer, nullable=False)
    assessment_done = Column(String(10))
    assessment_date = Column(String(20))
    plan_assigned = Column(String(10))
    plan_date = Column(String(20))
    plan_comments = Column(Text)
    exercise_plan_assigned = Column(String(10))
    exercise_plan_date = Column(String(20))
    exercise_plan_comments = Column(Text)
    followup_done = Column(String(10))
    followup_date = Column(String(20))
    cbt_tools = Column(Text)
    comments = Column(Text)

    coaching_data = relationship("CoachingData", back_populates="monthly_cycles")
    attempts = relationship("MonthlyAttempt", back_populates="monthly_cycle", cascade="all,delete", order_by="MonthlyAttempt.attempt_number")
    followup_attempts = relationship("FollowupAttempt", back_populates="monthly_cycle", cascade="all,delete", order_by="FollowupAttempt.attempt_number")


class MonthlyAttempt(Base):
    """Assessment call attempts — Created 2026-05-04"""
    __tablename__ = "monthly_attempts"
    id = Column(Integer, primary_key=True)
    monthly_cycle_id = Column(Integer, ForeignKey("monthly_cycles.id"), nullable=False)
    attempt_number = Column(Integer, nullable=False)
    date = Column(String(20))
    time = Column(String(20))
    disposition = Column(String(100))

    monthly_cycle = relationship("MonthlyCycle", back_populates="attempts")


class FollowupAttempt(Base):
    """Physio follow-up attempts — Created 2026-05-04"""
    __tablename__ = "followup_attempts"
    id = Column(Integer, primary_key=True)
    monthly_cycle_id = Column(Integer, ForeignKey("monthly_cycles.id"), nullable=False)
    attempt_number = Column(Integer, nullable=False)
    date = Column(String(20))
    time = Column(String(20))
    comments = Column(Text)

    monthly_cycle = relationship("MonthlyCycle", back_populates="followup_attempts")


class WeeklyEntry(Base):
    """RM weekly follow-ups — Created 2026-05-04"""
    __tablename__ = "weekly_entries"
    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    week_number = Column(Integer, nullable=False)
    date = Column(String(20))
    remarks = Column(Text)

    patient = relationship("Patient", back_populates="weekly_entries")


class Dropdown(Base):
    """Dropdown validation lists — Created 2026-05-04"""
    __tablename__ = "dropdowns"
    id = Column(Integer, primary_key=True)
    list_name = Column(String(100), nullable=False)
    value = Column(String(300), nullable=False)
    active = Column(Boolean, default=True)


class AuditLog(Base):
    """Edit history — Created 2026-05-04"""
    __tablename__ = "audit_log"
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=now_ist)
    user = Column(String(200))
    role = Column(String(50))
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=True)
    action = Column(String(50))
    section = Column(String(50))
    field = Column(String(200))
    old_value = Column(Text)
    new_value = Column(Text)

    patient = relationship("Patient", back_populates="audit_entries")


class Notification(Base):
    """In-app notifications for @mentions — Added 2026-05-05"""
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True)
    recipient_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    recipient_name = Column(String(200))
    sender_name = Column(String(200))
    sender_role = Column(String(50))
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=True)
    patient_name = Column(String(300))
    message = Column(Text)
    section = Column(String(50))  # rm, diet, wellness, physio, weekly
    read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=now_ist)


class Task(Base):
    """Auto-generated tasks — Added 2026-05-06"""
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True)
    assigned_to_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    assigned_to_name = Column(String(200))
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=True)
    patient_name = Column(String(300))
    task_type = Column(String(50))  # coach_assigned, wc_completed, patient_inactive
    message = Column(Text)
    section = Column(String(50))  # diet, wellness, physio, rm
    status = Column(String(20), default="open")  # open, done
    created_by = Column(String(200))
    created_at = Column(DateTime, default=now_ist)
    completed_at = Column(DateTime, nullable=True)


class Comment(Base):
    """Patient comments from any user — Added 2026-05-06"""
    __tablename__ = "comments"
    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    patient_name = Column(String(300))
    user_name = Column(String(200))
    user_role = Column(String(50))
    text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=now_ist)