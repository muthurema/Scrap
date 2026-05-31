"""
Seed the 18 authoritative global EHS URLs into the WebSource registry.

These are GLOBAL-tier sources — international regulators, UN agencies, ISO
standards, and reputable EHS knowledge bases. They re-crawl weekly via the
scheduler in app/scheduler.py.

Run once on a fresh install (idempotent — safe to re-run):
    python /app/backend/seed_global_sources.py

Or from the deployed container:
    railway run python seed_global_sources.py
"""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone

# Make `app` importable when run as a script
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from motor.motor_asyncio import AsyncIOMotorClient
from app.config import (
    get_settings, DocumentType, DocumentSource, WebSourceScope, ScrapeFrequency,
)

settings = get_settings()


# Curated by the user — see chat history for category breakdown.
GLOBAL_SOURCES = [
    # ── International Regulators ──
    ("https://www.ilo.org/topics-and-sectors/safety-and-health-work",
     "ILO — Safety & Health at Work", "Global occupational safety standards"),
    ("https://www.ilo.org/topics-and-sectors/safety-and-health-work/chemical-safety-and-environment",
     "ILO — Chemical Safety", "GHS, chemicals conventions, SDS"),
    ("https://www.who.int/health-topics/occupational-health",
     "WHO — Occupational Health", "Workplace health guidelines"),
    ("https://www.unep.org/explore-topics/chemicals-waste",
     "UNEP — Chemicals & Waste", "Environmental safety, GHS implementation"),
    ("https://unece.org/ghs",
     "UN GHS Purple Book", "Globally Harmonized System for chemicals"),

    # ── US Regulators ──
    ("https://www.osha.gov/laws-regs",
     "OSHA — Laws & Regulations", "OSHA standards, regulations, guidance"),
    ("https://www.osha.gov/etools",
     "OSHA — e-Tools & Best Practices", "OSHA e-tools"),
    ("https://www.epa.gov/laws-regulations",
     "EPA — Laws & Regulations", "US environmental regulations"),
    ("https://www.cdc.gov/niosh",
     "NIOSH", "Occupational health research"),

    # ── EU ──
    ("https://osha.europa.eu/en",
     "EU-OSHA", "European Agency for Safety & Health at Work"),
    ("https://echa.europa.eu",
     "ECHA — Chemicals", "REACH, CLP, SDS (European Chemicals Agency)"),
    ("https://finance.ec.europa.eu/capital-markets-union-and-financial-markets/company-reporting-and-auditing/company-reporting/corporate-sustainability-reporting_en",
     "EU CSRD / ESG Reporting", "Corporate Sustainability Reporting Directive"),

    # ── ISO Standards ──
    ("https://www.iso.org/iso-45001-occupational-health-and-safety.html",
     "ISO 45001", "Occupational Health & Safety Management Systems"),
    ("https://www.iso.org/iso-14001-environmental-management.html",
     "ISO 14001", "Environmental Management Systems"),
    ("https://www.iso.org/standard/66453.html",
     "ISO 14064", "Greenhouse Gas Accounting"),

    # ── Knowledge & Best Practice ──
    ("https://iosh.com/resources",
     "IOSH Resources", "Institution of Occupational Safety & Health"),
    ("https://www.nsc.org/workplace",
     "NSC Workplace Safety", "National Safety Council"),
    ("https://ehsdailyadvisor.blr.com",
     "EHS Daily Advisor", "EHS news & best practices"),
    ("https://www.thecampbellinstitute.org/research",
     "Campbell Institute", "Leading EHS research"),
]


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


async def main():
    print(f"Connecting to {settings.mongo_url}...")
    client = AsyncIOMotorClient(settings.mongo_url)
    db = client[settings.db_name]
    web_sources = db["web_sources"]

    created = 0
    skipped = 0
    for url, label, description in GLOBAL_SOURCES:
        existing = await web_sources.find_one({"url": url})
        if existing:
            skipped += 1
            continue
        doc = {
            "id": str(uuid.uuid4()),
            "url": url,
            "label": label,
            "description": description,
            "scope": WebSourceScope.PLATFORM.value,
            "company_id": None,
            "scrape_frequency": ScrapeFrequency.WEEKLY.value,
            "crawl_depth": 1,
            "include_patterns": [],
            "exclude_patterns": [],
            "doc_type": DocumentType.REGULATORY.value,
            "is_active": True,
            "last_scraped_at": None,
            "last_chunk_count": 0,
            "last_scrape_error": None,
            "change_detected_at": None,
            "is_change_pending_review": False,
            "created_at": _now_iso(),
            "created_by": "seed_script",
            "jurisdiction": None,  # Truly global
            "source_type": DocumentSource.PLATFORM_WEB.value,
            "tier": "global",
        }
        await web_sources.insert_one(doc)
        print(f"  ✓ added: {label}")
        created += 1

    print(f"\nSeed complete: {created} added, {skipped} already existed.")
    print(f"Total global web sources in DB: {await web_sources.count_documents({})}")
    print("\nNext steps:")
    print("  1. Hit `POST /api/web-sources/{id}/scrape` for each, OR")
    print("  2. Let the weekly scheduler crawl them on its next tick (default Sunday 03:00 UTC).")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
