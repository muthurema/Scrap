"""
Seed script: creates admin user + base EHS knowledge corpus.
Run: cd /app/backend && python seed.py
"""
import asyncio
import uuid
import sys
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from app.db import users_col, documents_col
from app.auth import hash_password
from app.config import DocumentType, DocumentSource
from app.vector_store import get_vector_store
from app.ingestion import IngestionService


ADMIN_EMAIL = os.environ.get("SEED_ADMIN_EMAIL", "admin@ehsrag.com")
ADMIN_PASSWORD = os.environ.get("SEED_ADMIN_PASSWORD", "Admin@12345")
ADMIN_FULL_NAME = "EHS Superadmin"


BASE_CORPUS_DOCS = [
    {
        "title": "OSHA Confined Space Entry Requirements (29 CFR 1910.146)",
        "doc_type": DocumentType.REGULATORY,
        "text": """
OSHA 29 CFR 1910.146 - Permit-Required Confined Spaces

A permit-required confined space (PRCS) is one that:
- Is large enough for an employee to bodily enter and perform assigned work,
- Has limited or restricted means for entry and exit,
- Is not designed for continuous employee occupancy, AND
- Contains or has the potential to contain a hazardous atmosphere, contains material with potential to engulf an entrant, has internal configuration that could trap or asphyxiate an entrant, or contains any other recognized serious safety/health hazard.

Required program elements:
1. Identification and evaluation of confined spaces.
2. Written permit-required confined space program.
3. Entry permit system - permit must be completed and posted before entry. Permit must include:
   - Space identification
   - Purpose of entry
   - Date and authorized duration
   - Authorized entrants, attendants, entry supervisor
   - Atmospheric testing results (oxygen 19.5-23.5%, LEL <10%, toxic <PEL)
   - Communication procedures
   - Rescue services
4. Atmospheric testing - test in this order: oxygen, combustible gases/vapors, toxic gases/vapors. Continuous monitoring required if conditions can change.
5. Ventilation - mechanical ventilation often required to maintain safe atmosphere.
6. Attendant must remain outside the space, maintain continuous communication, and order evacuation if conditions become unsafe.
7. Rescue and emergency services must be available before entry begins.
8. Training - employees must receive training in their assigned roles before entry duties.

Common confined spaces include: storage tanks, silos, vaults, pits, sewers, manholes, pipelines, ductwork.

LEGAL REQUIREMENT: Employers MUST evaluate workplaces to determine if any spaces are permit-required confined spaces.
""",
    },
    {
        "title": "ISO 45001 - Occupational Health & Safety Management Systems Overview",
        "doc_type": DocumentType.REGULATORY,
        "text": """
ISO 45001:2018 - Occupational Health and Safety Management Systems

ISO 45001 is the international standard for occupational health and safety (OH&S) management systems. It follows the Plan-Do-Check-Act (PDCA) cycle and Annex SL high-level structure.

Key clauses:
- Clause 4: Context of the organization - understand internal/external issues, needs of interested parties, scope of the OH&S management system.
- Clause 5: Leadership and worker participation - top management must demonstrate leadership and commitment; workers must be consulted on OH&S matters.
- Clause 6: Planning - identify hazards (clause 6.1.2.1), assess OH&S risks and opportunities, determine legal requirements, plan actions.
- Clause 7: Support - resources, competence, awareness, communication, documented information.
- Clause 8: Operation - operational planning and control, eliminate hazards using hierarchy of controls (elimination > substitution > engineering > administrative > PPE), management of change, procurement, contractors, emergency preparedness.
- Clause 9: Performance evaluation - monitoring, measurement, analysis, internal audit, management review.
- Clause 10: Improvement - incident investigation, nonconformity & corrective action, continual improvement.

Hierarchy of Controls (Clause 8.1.2):
1. Elimination - remove the hazard entirely
2. Substitution - replace with less hazardous alternative
3. Engineering controls - isolate people from the hazard
4. Administrative controls - change the way people work
5. PPE - personal protective equipment (last resort)

Risk and opportunity-based thinking and worker participation are mandatory features that distinguish ISO 45001 from the older OHSAS 18001.
""",
    },
    {
        "title": "Hot Work Permit Procedure",
        "doc_type": DocumentType.PERMIT,
        "text": """
HOT WORK PERMIT PROCEDURE

Hot work includes any operation that produces flames, sparks, or significant heat: welding, cutting, grinding, brazing, soldering, torch-applied roofing, and use of open flames.

A hot work permit MUST be issued before any hot work begins outside designated hot work areas.

Required Permit Elements:
1. Permit number, date, time range (max 8 hours, renewed daily)
2. Exact location of work
3. Description of hot work to be performed
4. Identification of hazards and combustibles within 35 feet (10.7 m)
5. Fire watch requirements
6. Atmospheric testing (LEL must be <10%)
7. Authorized worker(s) and fire watch personnel
8. Issuer signature and approver signature

Pre-Work Inspection (within 30 minutes of start):
- Remove all combustible materials within 35 feet, or cover with non-combustible blankets
- Sweep floors clean
- Cover floor openings, cracks, ducts
- Provide appropriate fire extinguisher (minimum 2-A:20-B:C) at the work location
- Verify nearby fire detection/suppression systems are operational
- Test atmosphere for flammable gases/vapors

Fire Watch Requirements:
- Required during ALL hot work and for 30 minutes after work ends
- Fire watch person must be trained in fire extinguisher use
- Must have unobstructed view of work area
- Has authority to STOP work if unsafe conditions develop
- Must remain in adjacent areas if fire could spread there

Prohibited Conditions:
- In areas where explosive atmospheres may develop
- On containers that held flammables until properly cleaned/purged
- When fire suppression systems are impaired
- In sprinklered buildings with sprinklers shut off

Reference: NFPA 51B "Standard for Fire Prevention During Welding, Cutting, and Other Hot Work"
""",
    },
    {
        "title": "Lockout/Tagout (LOTO) — 29 CFR 1910.147 Control of Hazardous Energy",
        "doc_type": DocumentType.PERMIT,
        "text": """
LOCKOUT/TAGOUT (LOTO) PROCEDURE - 29 CFR 1910.147

Purpose: Prevent injury from unexpected energization, startup, or release of stored energy during service or maintenance of machines and equipment.

Energy Sources Covered:
- Electrical
- Mechanical (springs, gravity, flywheels)
- Hydraulic
- Pneumatic
- Chemical
- Thermal
- Stored energy (capacitors, batteries)

Required 6-Step Procedure:
1. PREPARATION - identify all energy sources and isolation devices for the equipment.
2. NOTIFICATION - notify all affected employees that a lockout is going to be performed.
3. SHUTDOWN - shut down the equipment using normal stopping procedure.
4. ISOLATION - isolate all energy sources using approved isolation devices.
5. LOCKOUT/TAGOUT - apply lockout device and tag with the authorized employee's name. Each authorized employee applies their OWN lock.
6. VERIFICATION - verify zero-energy state by attempting to start the equipment, testing voltages, releasing stored energy. Then return controls to OFF.

Re-energization (Reverse Procedure):
1. Inspect machine area, remove tools, ensure components are operationally intact.
2. Check that all employees are safely positioned or removed.
3. Verify controls are in neutral.
4. Remove lockout devices - each employee removes their OWN lock only.
5. Notify affected employees that lockout has been removed.
6. Re-energize and test.

Group Lockout: When more than one person is involved, use a group lockout device (lockout hasp) so each authorized employee applies their personal lock.

Training Requirements:
- Authorized employees: full training in recognition, isolation, control of hazardous energy.
- Affected employees: purpose and use of energy control procedure.
- Other employees: awareness training.

Periodic Inspection: Energy control procedures must be inspected at least annually by an authorized employee other than the one(s) using the procedure.

Tags Alone Are NOT Sufficient when an energy isolating device is capable of being locked out. Lockout is the primary means of energy control.
""",
    },
    {
        "title": "Job Safety Analysis (JSA) — Risk Assessment Methodology",
        "doc_type": DocumentType.RISK_ASSESSMENT,
        "text": """
JOB SAFETY ANALYSIS (JSA) / JOB HAZARD ANALYSIS (JHA)

A JSA is a systematic process for identifying hazards in a specific job or task and establishing control measures. Required for non-routine, high-risk, or new tasks.

5-Step JSA Methodology:
1. SELECT THE JOB - prioritize jobs with: history of injury/illness, potential severity, frequency, new/modified procedures, complex tasks.
2. BREAK DOWN INTO STEPS - list each step in sequence; describe what is done, not how. Aim for 5-15 logical steps.
3. IDENTIFY HAZARDS for each step using the "What if..." technique:
   - Energy sources (electrical, mechanical, kinetic, thermal, chemical)
   - Physical hazards (slips, trips, falls, struck-by, caught-in)
   - Chemical exposures (inhalation, skin, ingestion)
   - Biological hazards
   - Ergonomic stressors (lifting, repetition, posture)
   - Environmental conditions (heat, cold, noise, lighting)
4. DETERMINE CONTROL MEASURES using the Hierarchy of Controls:
   - Elimination > Substitution > Engineering Controls > Administrative Controls > PPE
5. COMMUNICATE & TRAIN - review JSA with all workers performing the task; sign-off required.

Risk Matrix Example (5x5):
- Likelihood: 1=Rare, 2=Unlikely, 3=Possible, 4=Likely, 5=Almost Certain
- Severity: 1=Negligible, 2=Minor, 3=Moderate, 4=Major, 5=Catastrophic
- Risk Score = Likelihood × Severity
- Risk Rating: 1-4 Low, 5-9 Medium, 10-15 High, 16-25 Extreme

JSA Review Triggers:
- After any incident or near-miss involving the task
- Change in equipment, procedure, or personnel
- Annually for high-risk tasks
- When new hazards are identified

Reference: OSHA Publication 3071 "Job Hazard Analysis"
""",
    },
    {
        "title": "Incident Investigation — Root Cause Analysis Best Practices",
        "doc_type": DocumentType.INCIDENT_REPORT,
        "text": """
INCIDENT INVESTIGATION & ROOT CAUSE ANALYSIS

Investigation Objective: Determine WHAT happened, HOW it happened, and WHY it happened - so corrective actions prevent recurrence. NOT to assign blame.

Investigation Steps:
1. SECURE THE SCENE - render aid to injured, eliminate ongoing hazards, preserve evidence.
2. NOTIFY - supervisor, EHS, regulatory authorities as required (OSHA: fatality within 8 hours, hospitalization/amputation/eye loss within 24 hours).
3. GATHER FACTS - photographs, sketches, witness interviews (separately, ASAP), physical evidence, documentation review.
4. ANALYZE - determine sequence of events, identify direct causes (unsafe acts/conditions), contributing factors, and ROOT causes (management system failures).
5. DEVELOP CORRECTIVE ACTIONS - eliminate root causes, apply hierarchy of controls.
6. IMPLEMENT & VERIFY - assign owners and deadlines; verify effectiveness.
7. SHARE LESSONS LEARNED across the organization.

Root Cause Techniques:
- 5-Why Analysis: Ask "why?" five times to drill from symptom to root cause.
- Fishbone (Ishikawa): categorize causes into People, Process, Equipment, Materials, Environment, Management.
- Fault Tree Analysis: top-down deductive analysis for complex incidents.
- TapRoot, ECFA (Events and Causal Factors Analysis) for major incidents.

Causal Categories (typically 3-5 root causes per incident):
- People: training, fitness for duty, awareness, communication
- Process: procedures missing/inadequate, not followed, design
- Equipment: design, maintenance, failure
- Environment: layout, housekeeping, lighting, noise
- Management Systems: risk assessment, supervision, change management, leadership

Common Investigation Pitfalls:
- Stopping at unsafe act/condition (symptom, not cause)
- Blaming the worker - "carelessness" is not a root cause
- Single root cause assumption - most incidents have multiple contributors
- Weak corrective actions (training alone, signage alone)

Effective Corrective Actions follow the Hierarchy of Controls and address management system root causes, not just immediate ones.
""",
    },
    {
        "title": "Chemical Safety - GHS, SDS, and Hazard Communication",
        "doc_type": DocumentType.MSDS,
        "text": """
CHEMICAL SAFETY: GHS, SAFETY DATA SHEETS, AND HAZARD COMMUNICATION

Globally Harmonized System (GHS) is the international system for classifying and labeling chemicals. Adopted in OSHA's HazCom 2012 standard (29 CFR 1910.1200).

GHS HAZARD CLASSES:
- Physical Hazards: explosives, flammable gases/aerosols/liquids/solids, oxidizers, self-reactive substances, organic peroxides, corrosive to metals, gases under pressure, pyrophoric substances.
- Health Hazards: acute toxicity, skin corrosion/irritation, serious eye damage, respiratory/skin sensitization, germ cell mutagenicity, carcinogenicity, reproductive toxicity, STOT (single/repeated exposure), aspiration hazard.
- Environmental Hazards: aquatic toxicity, hazardous to the ozone layer.

GHS LABEL ELEMENTS:
1. Product identifier
2. Signal word: "DANGER" (severe hazards) or "WARNING" (less severe)
3. Hazard statements (H-codes: e.g., H225 "Highly flammable liquid and vapour")
4. Precautionary statements (P-codes: e.g., P210 "Keep away from heat")
5. Pictograms (9 standard pictograms - flame, exclamation mark, skull, health hazard, etc.)
6. Supplier identification

SAFETY DATA SHEET (SDS) - 16 Required Sections:
1. Identification
2. Hazard(s) identification
3. Composition / ingredients
4. First-aid measures
5. Fire-fighting measures
6. Accidental release measures
7. Handling and storage
8. Exposure controls / personal protection (PEL, TLV, engineering controls, PPE)
9. Physical and chemical properties
10. Stability and reactivity
11. Toxicological information
12. Ecological information (not enforced by OSHA)
13. Disposal considerations (not enforced)
14. Transport information (not enforced)
15. Regulatory information (not enforced)
16. Other information (preparation date, revision)

Employer Obligations (HazCom 2012):
- Written hazard communication program
- List of hazardous chemicals in workplace
- Maintain SDS readily accessible (electronic OK)
- Proper labeling of all containers (including secondary)
- Employee training on hazards, label reading, SDS use - at initial assignment and whenever new hazards introduced.

Storage Compatibility: Acids must be segregated from bases and cyanides. Oxidizers must be segregated from flammables and combustibles. Pyrophorics require inert atmosphere storage.
""",
    },
]


async def main():
    print("=== EHS RAG Seed ===")

    # 1. Admin user
    existing = await users_col().find_one({"email": ADMIN_EMAIL})
    if existing:
        print(f"Admin user already exists: {ADMIN_EMAIL}")
        # Ensure superadmin role
        if existing.get("role") != "superadmin":
            await users_col().update_one({"email": ADMIN_EMAIL}, {"$set": {"role": "superadmin"}})
            print("  Promoted to superadmin")
    else:
        user_id = str(uuid.uuid4())
        await users_col().insert_one({
            "id": user_id,
            "email": ADMIN_EMAIL,
            "hashed_password": hash_password(ADMIN_PASSWORD),
            "full_name": ADMIN_FULL_NAME,
            "role": "superadmin",
            "company_id": None,
            "is_active": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        print(f"Created admin user: {ADMIN_EMAIL} / {ADMIN_PASSWORD}")

    # 2. Base corpus ingestion
    ingestion = IngestionService(get_vector_store())

    existing_titles = {d["title"] async for d in documents_col().find(
        {"source": DocumentSource.BASE_CORPUS.value}, {"title": 1, "_id": 0}
    )}

    for entry in BASE_CORPUS_DOCS:
        if entry["title"] in existing_titles:
            print(f"Skipping (exists): {entry['title']}")
            continue

        doc_id = str(uuid.uuid4())
        # Save metadata
        await documents_col().insert_one({
            "id": doc_id,
            "company_id": None,
            "filename": f"{doc_id}.txt",
            "original_filename": f"{entry['title']}.txt",
            "file_path": None,
            "file_type": "txt",
            "file_size_bytes": len(entry["text"]),
            "mime_type": "text/plain",
            "doc_type": entry["doc_type"].value,
            "source": DocumentSource.BASE_CORPUS.value,
            "title": entry["title"],
            "description": None,
            "tags": [],
            "version": None,
            "is_processed": False,
            "chunk_count": 0,
            "uploaded_by": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "processed_at": None,
            "processing_error": None,
        })

        try:
            chunk_count, _ = await ingestion.ingest_document(
                file_bytes=entry["text"].encode("utf-8"),
                file_ext="txt",
                doc_id=doc_id,
                title=entry["title"],
                doc_type=entry["doc_type"],
                source=DocumentSource.BASE_CORPUS,
                extra_metadata={"company_id": "", "filename": f"{entry['title']}.txt"},
            )
            await documents_col().update_one(
                {"id": doc_id},
                {"$set": {
                    "is_processed": True,
                    "chunk_count": chunk_count,
                    "processed_at": datetime.now(timezone.utc).isoformat(),
                }},
            )
            print(f"  Ingested ({chunk_count} chunks): {entry['title']}")
        except Exception as e:
            print(f"  FAILED: {entry['title']} — {e}")
            await documents_col().update_one(
                {"id": doc_id},
                {"$set": {"processing_error": str(e)}},
            )

    print("=== Seed complete ===")


if __name__ == "__main__":
    asyncio.run(main())
