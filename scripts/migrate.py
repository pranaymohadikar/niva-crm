"""
Niva Bupa CRM Migration (SQLite + Supabase) — Changed 2026-05-12
=================================================================
ONE-TIME bulk migrator. Drops all tables and rebuilds from CSV/Excel.

Usage:
  python scripts/migrate.py <inside_sales.csv> <ops_tracker.xlsx>

Safety:
  This script calls drop_all() — set ALLOW_DROP=yes to confirm:
    ALLOW_DROP=yes python scripts/migrate.py <csv> <xlsx>

Connecting to Supabase:
  Use the DIRECT connection URL (port 5432), NOT the pooler (port 6543).
  Pooler in Transaction mode doesn't reliably support DDL operations.
    export DATABASE_URL="postgresql://postgres:PASSWORD@db.PROJECT.supabase.co:5432/postgres"

For local SQLite, no env var needed — falls back to sqlite:///crm.db.
"""

import pandas as pd
import sys
import os
import hashlib
from pathlib import Path
from datetime import datetime, date, time as dt_time

# Allow importing db.py and models.py from ../api — Changed 2026-05-12
sys.path.insert(0, str(Path(__file__).parent.parent / "api"))

from db import engine, SessionLocal
from models import (Base, User, Staff, Patient, RMData, WCAttempt, CoachingData,
                    MonthlyCycle, MonthlyAttempt, FollowupAttempt,
                    WeeklyEntry, Dropdown, AuditLog, Notification, Task, Comment)

# Safety check — drop_all destroys all data — Added 2026-05-12
if os.environ.get("ALLOW_DROP") != "yes":
    print("ERROR: This script will drop ALL tables and rebuild from scratch.")
    print("       Set ALLOW_DROP=yes to confirm you understand this:")
    print("         ALLOW_DROP=yes python scripts/migrate.py <csv> <xlsx>")
    sys.exit(1)

CSV_PATH = sys.argv[1] if len(sys.argv) > 1 else "Niva_Bupa_Tracker_Niva_-_Inside_Sales_.csv"
EXCEL_PATH = sys.argv[2] if len(sys.argv) > 2 else "Niva_Bupa_Ops_Tracker__5_.xlsx"

# ─── NORMALIZATION MAPS (unchanged) ───
CONDITION_MAP = {"cholesterol": "Cholesterol"}
DURATION_MAP = {"3 months":"3 Months","6 months":"6 Months","6 months ":"6 Months","12 months":"12 Months","1 year":"12 Months"}
DIET_COACH_MAP = {"bhakti":"Bhakti Bhavsar","Bhakti":"Bhakti Bhavsar","BHUVANESWARI":"Bhuvaneshwari Savant","Bhuvaneswari":"Bhuvaneshwari Savant","Dr.Radhika/Vandna":"Radhika Rao","Radhika":"Radhika Rao","Swetha.K":"Swetha Sheerasagar", "Vandana": "Vandna Lalchandani","Vandna":"Vandna Lalchandani","Bhumika": "Bhumika Shah","Michelle":"Michelle Christopher","No coach Assigned":None}
WELLNESS_COACH_MAP = {"shubha":"Shubha Dubey","Shubha":"Shubha Dubey","Shubha ":"Shubha Dubey","Shubha dubey":"Shubha Dubey","Shubha Dubey ":"Shubha Dubey","shobika":"Shobika KR","Shobika":"Shobika KR","sridurga":"Sridurga","sridurga ":"Sridurga","Manya Jain":"Manya Jain","Manya":"Manya Jain","No coach Assigned":None}
PHYSIO_COACH_MAP = {"Ishwarya":"Dr. Iswarya V","Iswarya":"Dr. Iswarya V","sakshi":"Sakshi Vaidya","sakshi ":"Sakshi Vaidya","Sakshi ":"Sakshi Vaidya","Sakshi Vaidya":"Sakshi Vaidya", "Sakshi":"Sakshi Vaidya","Nisheshika": "Nisheshilka  Singh", "Jiwangi": "Dr. Jiwangi Singh"}

# ─── HELPERS (unchanged) ───
def safe_str(val):
    if pd.isna(val) or val is None: return None
    s = str(val).strip()
    return None if s in ("","0","nan","NaT","None") else s

def safe_date(val):
    if pd.isna(val) or val is None: return None
    if isinstance(val, (datetime, date)): return val.strftime("%Y-%m-%d")
    s = str(val).strip()
    if s in ("","0","nan","NaT"): return None
    try: return pd.to_datetime(val, dayfirst=True).strftime("%Y-%m-%d")
    except: return None

def safe_time(val):
    if pd.isna(val) or val is None: return None
    if isinstance(val, dt_time): return val.strftime("%H:%M")
    s = str(val).strip()
    return None if s in ("","0","nan","NaT") else s

def norm_condition(val):
    s = safe_str(val)
    return CONDITION_MAP.get(s, s) if s else None

def norm_duration(val):
    s = safe_str(val)
    return DURATION_MAP.get(s, s) if s else None

def norm_coach(val, mapping):
    s = safe_str(val)
    if s is None: return None
    return mapping.get(s, s)

def norm_name(val):
    s = safe_str(val)
    return s.strip() if s else None

def is_real_patient(row, name_col, phone_col):
    name = str(row.get(name_col, "")).strip()
    phone = str(row.get(phone_col, "")).strip().replace("+", "")
    return name not in ("","0","nan","None") and len(phone.replace(" ", "")) >= 7

def get_col(row, col_name, default=None):
    if row is None: return default
    return row[col_name] if col_name in row.index else default


# ─── STEP 1: CREATE TABLES ───
print("Creating database tables...")
Base.metadata.drop_all(engine)
Base.metadata.create_all(engine)
db = SessionLocal()

# ─── STEP 2: READ DATA ───
print(f"\nReading {CSV_PATH}...")
csv_df = pd.read_csv(CSV_PATH, low_memory=False)
csv_real = csv_df.dropna(subset=["Patient Name"]).copy()
csv_real.reset_index(drop=True, inplace=True)
csv_real["_phone"] = csv_real["Mobile"].astype(str).str.replace(" ","").str.strip()
print(f"  Inside Sales: {len(csv_real)} patients")

MAX_ROWS = 2000
print(f"Reading {EXCEL_PATH}...")
rm_df = pd.read_excel(EXCEL_PATH, sheet_name="Niva-RM (2)", nrows=MAX_ROWS)
diet_df = pd.read_excel(EXCEL_PATH, sheet_name="Niva - Diet", nrows=MAX_ROWS)
phys_df = pd.read_excel(EXCEL_PATH, sheet_name="Niva - Physio", nrows=MAX_ROWS)
well_df = pd.read_excel(EXCEL_PATH, sheet_name="Niva - Wellness (2)", nrows=MAX_ROWS)
weekly_df = pd.read_excel(EXCEL_PATH, sheet_name="Niva - RM Weekly", nrows=MAX_ROWS)
coaches_df = pd.read_excel(EXCEL_PATH, sheet_name="Coaches Sheet")

rm_real = rm_df[rm_df.apply(lambda r: is_real_patient(r,"Patient Name","Contact Number"), axis=1)].copy()
rm_real.reset_index(drop=True, inplace=True)
rm_real["_phone"] = rm_real["Contact Number"].astype(str).str.replace(" ","").str.strip()
rm_phone_map = {}
for i, row in rm_real.iterrows():
    ph = row["_phone"]
    if ph not in rm_phone_map: rm_phone_map[ph] = i
diet_real = diet_df.head(len(rm_real)).copy()
phys_real = phys_df.head(len(rm_real)).copy()
well_real = well_df.head(len(rm_real)).copy()
weekly_real = weekly_df.head(len(rm_real)).copy()
print(f"  RM: {len(rm_real)}, Matched: {sum(1 for ph in csv_real['_phone'] if ph in rm_phone_map)}")


# ─── STEP 3: INSERT STAFF — Added 2026-05-04 ───
print("\nInserting staff...")

def coach_list(df, col):
    return [s for s in df[col].dropna().astype(str).str.strip().tolist() if s and s != "nan"]

# Build staff entries with their types
staff_entries = []

# Staff name normalization — align staff table names with normalized patient data — Added 2026-05-05
STAFF_NAME_MAP = {
    # Diet
    "Swetha": "Swetha K",
    # Wellness
    "Shubha": "Shubha Dubey",
    # Physio
    "Dr. Iswarya": "Iswarya",
    "Dr. Jiwangi": "Jiwangi",
    "Nisheshilka": "Nisheshika",
    # Health Partner
    "Khusboo": "Khushboo",
}

# Extra staff that exist in patient data but not in Coaches Sheet — Added 2026-05-05
EXTRA_STAFF = [
    ("wellness_coach", "Sridurga"),
    ("wellness_coach", "Riya"),
    ("physio_coach", "Juilee"),
    ("physio_coach", "Shweta"),
]

def norm_staff_name(name):
    return STAFF_NAME_MAP.get(name, name)

# Diet coaches
for name in sorted([c for c in coach_list(coaches_df,"Diet") if c not in ("Diet Coach","Chief HC")]):
    staff_entries.append(("diet_coach", norm_staff_name(name)))

# Wellness coaches
for name in sorted(coach_list(coaches_df,"Wellness")):
    staff_entries.append(("wellness_coach", norm_staff_name(name)))

# Physio coaches
for name in sorted([c for c in coach_list(coaches_df,"Physio") if c != "Test MyTatva"]):
    staff_entries.append(("physio_coach", norm_staff_name(name)))

# Health partners — handle missing HP column — Changed 2026-05-05
if "HP" in coaches_df.columns:
    for name in coach_list(coaches_df,"HP"):
        staff_entries.append(("health_partner", norm_staff_name(name)))
else:
    # Fallback: extract from patient data
    for name in sorted(rm_real["Health Partner "].dropna().astype(str).str.strip().unique()):
        if name and name != "nan":
            staff_entries.append(("health_partner", norm_staff_name(name)))

# Add extra staff not in Coaches Sheet — Added 2026-05-05
for stype, sname in EXTRA_STAFF:
    if (stype, sname) not in staff_entries:
        staff_entries.append((stype, sname))

# Deduplicate — Added 2026-05-05
staff_entries = list(dict.fromkeys(staff_entries))

# CS agents
for name in sorted([a for a in rm_real["CS Agent Assigned"].dropna().astype(str).str.strip().unique() if a and a!="nan"]):
    staff_entries.append(("cs_agent", name))

# ISA owners
for name in sorted([a for a in csv_real["ISA Owner"].dropna().astype(str).str.strip().unique() if a and a!="nan"]):
    staff_entries.append(("isa_owner", name))

# Insert and build name->id lookup — Added 2026-05-04
staff_lookup = {}  # (type, name) -> id
for stype, sname in staff_entries:
    s = Staff(name=sname, type=stype)
    db.add(s)
    db.flush()
    staff_lookup[(stype, sname)] = s.id
    print(f"  Staff #{s.id}: {sname} ({stype})")

db.commit()
print(f"  Total staff: {len(staff_entries)}")

def get_staff_id(stype, name):
    """Look up staff ID by type and name — Added 2026-05-04"""
    if not name: return None
    return staff_lookup.get((stype, name))


# ─── STEP 4: INSERT DROPDOWNS ───
print("\nInserting dropdowns...")
dd = {
    "health_partners": [s[1] for s in staff_entries if s[0]=="health_partner"],
    "rm_agents": coach_list(coaches_df,"RM") if "RM" in coaches_df.columns else [],  # Handle missing column — Changed 2026-05-05
    "diet_coaches": [s[1] for s in staff_entries if s[0]=="diet_coach"],
    "wellness_coaches": [s[1] for s in staff_entries if s[0]=="wellness_coach"],
    "physio_coaches": [s[1] for s in staff_entries if s[0]=="physio_coach"],
    "cs_agents": [s[1] for s in staff_entries if s[0]=="cs_agent"],
    "isa_owners": [s[1] for s in staff_entries if s[0]=="isa_owner"],
    "conditions": ["Cholesterol","Diabetes","Weight Management","Hypertension","PCOS","Pre-Diabetic"],
    "durations": ["3 Months","6 Months","12 Months"],
    "dispositions": ["Completed","Partially Completed","No answer","Asked to call later","Not Reachable/Switch Off","Patient did not join the call"],
    "statuses": ["Welcome Call Pending","Welcome Call Completed","Month 1 Assessment Pending","Month 1 Assessment Completed","Month 2 Assessment Pending","Month 2 Assessment Completed","Month 3 Assessment Pending","Month 3 Assessment Completed","Month 4 Assessment Pending","Month 4 Assessment Completed","Month 5 Assessment Pending","Month 5 Assessment Completed","Month 6 Assessment Pending","Month 6 Assessment Completed","Inactive from Month 1 Assessment","Inactive from Month 2 Assessment","Inactive from Month 3 Assessment","Inactive from Month 4 Assessment","Inactive from Month 5 Assessment","Inactive from Month 6 Assessment","others","Plan Ended"],
    "plan_prices": ["2499","2999","4299","4699","4799","7499","7999","11298","11299","11449","12499"],
    "payment_modes": ["App","Link","QR Code"],
}
for ln, vals in dd.items():
    for v in vals: db.add(Dropdown(list_name=ln, value=str(v)))
db.commit()


# ─── STEP 5: DEFAULT ADMIN ───
pw_hash = hashlib.sha256(b"admin123").hexdigest()
try:
    import bcrypt
    pw_hash = bcrypt.hashpw(b"admin123", bcrypt.gensalt()).decode()
except ImportError: pass
db.add(User(username="admin", password_hash=pw_hash, name="Admin", role="admin"))
db.commit()
print("  Admin user created (admin / admin123)")


# ─── STEP 6: INSERT PATIENTS — Changed 2026-05-04: stores both ID and name ───
print(f"\nInserting {len(csv_real)} patients...")
count = 0

for idx in range(len(csv_real)):
    csv_row = csv_real.iloc[idx]
    phone = str(csv_row["_phone"])
    name = norm_name(csv_row["Patient Name"])
    if not name or not phone or len(phone) < 7: continue

    rm_idx = rm_phone_map.get(phone)
    rm_row = rm_real.iloc[rm_idx] if rm_idx is not None else None
    diet_row = diet_real.iloc[rm_idx] if rm_idx is not None and rm_idx < len(diet_real) else None
    phys_row = phys_real.iloc[rm_idx] if rm_idx is not None and rm_idx < len(phys_real) else None
    well_row = well_real.iloc[rm_idx] if rm_idx is not None and rm_idx < len(well_real) else None
    weekly_row = weekly_real.iloc[rm_idx] if rm_idx is not None and rm_idx < len(weekly_real) else None

    isa_name = safe_str(csv_row.get("ISA Owner"))

    p = Patient(
        patient_name=name, contact_number=phone,
        alt_number=safe_str(csv_row.get("Alt No.")),
        condition_type=norm_condition(safe_str(csv_row["Program Name"])),
        plan_purchase_date=safe_date(csv_row["Date of Payment"]),
        plan_duration=norm_duration(safe_str(csv_row["Duration"])),
        plan_price=safe_str(csv_row.get("Amount")),
        expiry_date=safe_date(csv_row.get("Expiry date")),
        isa_owner_id=get_staff_id("isa_owner", isa_name),  # ID — Added 2026-05-04
        isa_owner=isa_name,                                  # Name — readability
        mode_of_payment=safe_str(csv_row.get("Mode of Payment")),
        rm_call_booked=safe_str(csv_row.get("RM Call Booked")),
        sales_remarks=safe_str(csv_row.get("Remarks for RM")),
        payment_month=safe_str(csv_row.get("Payment Month")),
        week_no=safe_str(csv_row.get("Week No.")),
        created_by="migration",
    )
    db.add(p); db.flush()

    # RM — with HP and CS agent IDs — Changed 2026-05-04
    hp_name = safe_str(get_col(rm_row,"Health Partner ")) if rm_row is not None else None
    cs_name_rm = safe_str(get_col(rm_row,"CS Agent Assigned")) if rm_row is not None else None

    db.add(RMData(
        patient_id=p.id,
        health_partner_id=get_staff_id("health_partner", hp_name),  # ID
        health_partner=hp_name,                                       # Name
        welcome_call_booked_timestamp=safe_str(get_col(rm_row,"Welcome Call Booked for Time Stamp")) if rm_row is not None else None,
        welcome_call_done=safe_str(get_col(rm_row,"Welcome Call done Y/N")) if rm_row is not None else None,
        welcome_call_completion_date=safe_date(get_col(rm_row,"Welcome call completion Date")) if rm_row is not None else None,
        welcome_call_booked_not_completed=safe_str(get_col(rm_row,"Welcome Call Booked but Not completed")) if rm_row is not None else None,
        metabolic_assessment=safe_str(get_col(rm_row,"Metabolic Assessment Done Y/N")) if rm_row is not None else None,
        final_remarks=safe_str(get_col(rm_row,"Final/Current Remarks")) if rm_row is not None else None,
        diet_coach_assignment=safe_str(get_col(rm_row,"Appointment, coach name & Special Remarks For Diet Coach")) if rm_row is not None else None,
        wellness_coach_assignment=safe_str(get_col(rm_row,"Appointment, coach name & Special Remarks For Wellness Coach")) if rm_row is not None else None,
        physio_coach_assignment=safe_str(get_col(rm_row,"Appointment, coach name & Special Remarks For Physio Coach")) if rm_row is not None else None,
        cs_agent_id=get_staff_id("cs_agent", cs_name_rm),  # ID
        cs_agent=cs_name_rm,                                  # Name
        cs_call_date=safe_date(get_col(rm_row,"CS call Attempt Date")) if rm_row is not None else None,
        cs_call_time=safe_time(get_col(rm_row,"CS call Attempt Time")) if rm_row is not None else None,
        cs_remarks=safe_str(get_col(rm_row,"CS Remarks")) if rm_row is not None else None,
    ))

    # WC attempts
    if rm_row is not None:
        for i in range(1, 6):
            d = safe_date(get_col(rm_row, f"Welcome Call Attempt {i} Date"))
            t = safe_time(get_col(rm_row, f"Welcome Call Attempt {i} Time"))
            r = safe_str(get_col(rm_row, f"Welcome Call Attempt {i} Remarks"))
            if d or t or r:
                db.add(WCAttempt(patient_id=p.id, attempt_number=i, date=d, time=t, remarks=r))

    # DIET — with coach_id and cs_agent_id — Changed 2026-05-04
    diet_coach_name = norm_coach(safe_str(get_col(diet_row,"Diet Coach")),DIET_COACH_MAP) if diet_row is not None else None
    cs_name_diet = safe_str(get_col(diet_row,"CS Agent Assigned")) if diet_row is not None else None

    cd = CoachingData(patient_id=p.id, module="diet",
        coach_id=get_staff_id("diet_coach", diet_coach_name),  # ID
        coach=diet_coach_name,                                    # Name
        status=safe_str(get_col(diet_row,"Diet Status")) if diet_row is not None else None,
        current_status=safe_str(get_col(diet_row,"Current Diet Status")) if diet_row is not None else None,
        appointment_remarks=safe_str(get_col(diet_row,"Appointment, coach name & Special Remarks For Diet Coach")) if diet_row is not None else None,
        head_coach_comment=safe_str(get_col(diet_row,"Head Coach Comment")) if diet_row is not None else None,
        cs_agent_id=get_staff_id("cs_agent", cs_name_diet),  # ID
        cs_agent=cs_name_diet,                                  # Name
        cs_call_date=safe_date(get_col(diet_row,"CS call Attempt Date")) if diet_row is not None else None,
        cs_call_time=safe_time(get_col(diet_row,"CS call Attempt Time")) if diet_row is not None else None,
        cs_remarks=safe_str(get_col(diet_row,"CS Remarks")) if diet_row is not None else None,
    )
    db.add(cd); db.flush()
    if diet_row is not None:
        for m in range(1, 7):
            ad = safe_str(get_col(diet_row, f"Month {m} Assessment Completed (Y/N)"))
            atts = []
            for a in range(1,4):
                d2=safe_date(get_col(diet_row,f"Month {m} Attempt {a} Date")); t2=safe_time(get_col(diet_row,f"Month {m} Attempt {a} Time")); dp=safe_str(get_col(diet_row,f"Month {m} Attempt {a} Disposition"))
                if d2 or t2 or dp: atts.append((a,d2,t2,dp))
            pyn=safe_str(get_col(diet_row,f"Month {m}\nDiet Plan Assigned (Y/N)"))
            if ad or atts or pyn:
                mc = MonthlyCycle(coaching_id=cd.id, month_number=m, assessment_done=ad,
                    assessment_date=safe_date(get_col(diet_row,f"Month {m} Assessment Completion Date")),
                    plan_assigned=pyn, plan_date=safe_date(get_col(diet_row,f"Month {m}\nDiet Plan Assigned Date")),
                    plan_comments=safe_str(get_col(diet_row,f"Month {m}\nDiet Plan Assigned Comments")))
                db.add(mc); db.flush()
                for an,d2,t2,dp in atts: db.add(MonthlyAttempt(monthly_cycle_id=mc.id,attempt_number=an,date=d2,time=t2,disposition=dp))

    # WELLNESS — with coach_id and cs_agent_id — Changed 2026-05-04
    well_coach_name = norm_coach(safe_str(get_col(well_row,"Wellness Coach Name")),WELLNESS_COACH_MAP) if well_row is not None else None
    cs_name_well = safe_str(get_col(well_row,"CS Agent Assigned")) if well_row is not None else None

    cw = CoachingData(patient_id=p.id, module="wellness",
        coach_id=get_staff_id("wellness_coach", well_coach_name),
        coach=well_coach_name,
        status=safe_str(get_col(well_row,"Wellness Status")) if well_row is not None else None,
        current_status=safe_str(get_col(well_row,"Current Wellness Status")) if well_row is not None else None,
        appointment_remarks=safe_str(get_col(well_row,"Appointment, coach name & Special Remarks For Wellness Coach")) if well_row is not None else None,
        cs_agent_id=get_staff_id("cs_agent", cs_name_well),
        cs_agent=cs_name_well,
        cs_call_date=safe_date(get_col(well_row,"CS call Attempt Date")) if well_row is not None else None,
        cs_call_time=safe_time(get_col(well_row,"CS call Attempt Time")) if well_row is not None else None,
        cs_remarks=safe_str(get_col(well_row,"CS Remarks")) if well_row is not None else None,
    )
    db.add(cw); db.flush()
    if well_row is not None:
        for m in range(1, 7):
            ad = safe_str(get_col(well_row,"Yes")) if m==1 else safe_str(get_col(well_row,f"Month {m} Assessment Completed (Y/N)"))
            cbt = safe_str(get_col(well_row,"CBT Tools")) if m==1 else safe_str(get_col(well_row,"CBT Tools2")) if m==2 else None
            com = safe_str(get_col(well_row,"Comments")) if m==2 else None
            atts = []
            for a in range(1,4):
                d2=safe_date(get_col(well_row,f"Month {m} Attempt {a} Date")); t2=safe_time(get_col(well_row,f"Month {m} Attempt {a} Time")); dp=safe_str(get_col(well_row,f"Month {m} Attempt {a} Disposition"))
                if d2 or t2 or dp: atts.append((a,d2,t2,dp))
            if ad or atts or cbt:
                mc = MonthlyCycle(coaching_id=cw.id, month_number=m, assessment_done=ad,
                    assessment_date=safe_date(get_col(well_row,f"Month {m} Assessment Completion Date")), cbt_tools=cbt, comments=com)
                db.add(mc); db.flush()
                for an,d2,t2,dp in atts: db.add(MonthlyAttempt(monthly_cycle_id=mc.id,attempt_number=an,date=d2,time=t2,disposition=dp))

    # PHYSIO — with coach_id and cs_agent_id — Changed 2026-05-04
    phys_coach_name = norm_coach(safe_str(get_col(phys_row,"Physio Coach Name")),PHYSIO_COACH_MAP) if phys_row is not None else None
    cs_name_phys = safe_str(get_col(phys_row,"CS Agent Assigned")) if phys_row is not None else None

    cp = CoachingData(patient_id=p.id, module="physio",
        coach_id=get_staff_id("physio_coach", phys_coach_name),
        coach=phys_coach_name,
        status=safe_str(get_col(phys_row,"Physio Status")) if phys_row is not None else None,
        current_status=safe_str(get_col(phys_row,"Current Physio Status")) if phys_row is not None else None,
        appointment_remarks=safe_str(get_col(phys_row,"Appointment, coach name & Special Remarks For Physio Coach")) if phys_row is not None else None,
        cs_agent_id=get_staff_id("cs_agent", cs_name_phys),
        cs_agent=cs_name_phys,
        cs_call_date=safe_date(get_col(phys_row,"CS call Attempt Date")) if phys_row is not None else None,
        cs_call_time=safe_time(get_col(phys_row,"CS call Attempt Time")) if phys_row is not None else None,
        cs_remarks=safe_str(get_col(phys_row,"CS Remarks")) if phys_row is not None else None,
    )
    db.add(cp); db.flush()
    if phys_row is not None:
        for m in [1, 4]:
            ad = safe_str(get_col(phys_row,f"Month {m} Assessment Completed (Y/N)"))
            exyn = safe_str(get_col(phys_row,f"Month {m}\nExercise Plan Assigned (Y/N)"))
            fud = safe_str(get_col(phys_row,f"Month {m} Followup Call Completed (Y/N)"))
            atts = []
            for a in range(1,4):
                d2=safe_date(get_col(phys_row,f"Month {m} Attempt {a} Date")); t2=safe_time(get_col(phys_row,f"Month {m} Attempt {a} Time")); dp=safe_str(get_col(phys_row,f"Month {m} Attempt {a} Disposition"))
                if d2 or t2 or dp: atts.append((a,d2,t2,dp))
            fu_atts = []
            for a in range(1,4):
                fd=safe_date(get_col(phys_row,f" Month {m} Followup Call Attempt {a}\n(Date)"))
                if fd is None: fd=safe_date(get_col(phys_row,f"Month {m} Followup Call Attempt {a}\n(Date)"))
                ft=safe_time(get_col(phys_row,f"Month {m} Followup Call Attempt {a}\n(Time)"))
                fc=safe_str(get_col(phys_row,f"Month {m} Followup Call Attempt {a}\n(Comments)"))
                if fd or ft or fc: fu_atts.append((a,fd,ft,fc))
            if ad or atts or exyn or fu_atts:
                mc = MonthlyCycle(coaching_id=cp.id, month_number=m, assessment_done=ad,
                    assessment_date=safe_date(get_col(phys_row,f"Month {m} Assessment Completion Date")),
                    exercise_plan_assigned=exyn, exercise_plan_date=safe_date(get_col(phys_row,f"Month {m}\nExercise Plan Assigned Date")),
                    exercise_plan_comments=safe_str(get_col(phys_row,f"Month {m}\nExercise Plan Assigned Comments")),
                    followup_done=fud, followup_date=safe_date(get_col(phys_row,f"Month {m} Followup Call Completion Date")))
                db.add(mc); db.flush()
                for an,d2,t2,dp in atts: db.add(MonthlyAttempt(monthly_cycle_id=mc.id,attempt_number=an,date=d2,time=t2,disposition=dp))
                for an,fd,ft,fc in fu_atts: db.add(FollowupAttempt(monthly_cycle_id=mc.id,attempt_number=an,date=fd,time=ft,comments=fc))

    # WEEKLY
    if weekly_row is not None:
        for w in range(1, 20):
            dc = f"Week {w} Attempt date" if w < 17 else f"Week {w} Attempt date2"
            rc = f"Week {w} Attempt Remarks" if w < 17 else f"Week {w} Attempt Remarks3"
            d = safe_date(get_col(weekly_row, dc)); r = safe_str(get_col(weekly_row, rc))
            if d or r: db.add(WeeklyEntry(patient_id=p.id, week_number=w, date=d, remarks=r))

    count += 1
    if count % 100 == 0: db.commit(); print(f"  ...{count}")

db.commit()

print(f"\n{'='*50}")
print("MIGRATION COMPLETE")
print(f"{'='*50}")
# Show DB info (works for both SQLite and Postgres) — Changed 2026-05-12
db_url = os.environ.get("DATABASE_URL", "sqlite:///crm.db")
if db_url.startswith("sqlite") and os.path.exists("crm.db"):
    print(f"  Database: crm.db ({os.path.getsize('crm.db')//1024} KB)")
else:
    import re as _re
    safe_url = _re.sub(r'://([^:]+):[^@]+@', r'://\1:***@', db_url)
    print(f"  Database: {safe_url}")
print(f"  Patients: {count}")
print(f"  Staff: {len(staff_entries)}")
print(f"  Admin login: admin / admin123")
wcd = db.query(RMData).filter(RMData.welcome_call_done=="Yes").count()
print(f"  WC Done: {wcd}/{count}")
db.close()