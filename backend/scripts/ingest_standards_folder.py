"""
One-time bulk ingest of the `Standards/` folder into S3 + the documents table.

Intended to be run ONCE on the production EC2 instance, after copying the
`Standards/` folder onto the box (e.g. with scp into /home/ubuntu/Standards).
The folder is temporary — delete it once this script reports success.

    cd /opt/iso-tracker/backend

    # 1. Dry run — changes nothing, prints exactly what would happen
    APP_ENV=production ./venv/bin/python scripts/ingest_standards_folder.py \
        --source /home/ubuntu/Standards --purge-existing

    # 2. For real
    APP_ENV=production ./venv/bin/python scripts/ingest_standards_folder.py \
        --source /home/ubuntu/Standards --purge-existing --confirm

Nothing is written unless --confirm is passed. Without it the script runs the
full plan read-only and prints the report.

WHAT IT DOES
    1. Preflight — verifies storage backend, S3 bucket reachability, source
       folder contents and the actor user, and reconciles the folder against
       the embedded mapping (reports missing and unexpected files).
    2. Purge (only with --purge-existing) — deletes EVERY existing document
       row and its stored object. Used to clear test uploads before the real
       ingest. Standards left with no document have is_purchased cleared, so
       the "purchase requires a document" rule is not violated.
    3. Ingest — for each file: find the standard by iso_reference or create it
       from the embedded mapping, upload the file to the configured storage
       backend, insert the documents row, and create the pending
       document_tags row.
    4. Report — writes a markdown file/standard map and prints a summary.

DELIBERATE DIFFERENCES FROM THE NORMAL UPLOAD PATH
    * No notifications. app.services.document_service creates an in-app
      notification per active user AND queues an email to every distribution
      list mapped to `document_uploaded`. For ~100 files that is hundreds of
      emails, so this script writes documents directly and skips both.
    * AI tagging is NOT queued unless --enqueue-tagging is passed. The
      document_tags rows are still created as `pending`, so tagging can be
      triggered later per document via POST /documents/{id}/retag.
    * Everything else — MIME magic-byte validation, SHA-256 duplicate
      detection, version numbering, is_current flipping, audit logging — is
      the same as an interactive upload.

RE-RUNNING IS SAFE. A file whose SHA-256 already exists on its standard is
skipped, so an interrupted run can simply be run again (without
--purge-existing the second time).
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import sys
import unicodedata
import uuid
from pathlib import Path
from typing import Any

# Make `app` importable when run as `python scripts/ingest_standards_folder.py`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import magic  # python-magic  # noqa: E402
from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.config import settings  # noqa: E402
from app.core.iso_stages import is_draft_stage  # noqa: E402
from app.core.storage import compute_sha256, get_storage_backend  # noqa: E402
from app.database import async_session_factory  # noqa: E402
from app.models.document import Document  # noqa: E402
from app.models.document_tag import DocumentTag, DocumentTagStatus  # noqa: E402
from app.models.standard import Standard, StandardStatus  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.audit_service import write_audit_log  # noqa: E402
from app.tasks.feeds import _extract_base_reference  # noqa: E402

_ALLOWED_MIME_TYPES: set[str] = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/msword",
    "application/vnd.ms-excel",
}

# ── File → standard mapping ──────────────────────────────────────────────────
# Exported from the reviewed local ingest so production ends up with exactly
# the same mapping. `created_by_upload` records whether the standard had to be
# created locally (true) or already existed in the library (false) — it is
# informational only; this script decides per environment.
#
# Wrapped in json.loads so JSON `null` stays valid Python source.
MAPPING: list[dict[str, Any]] = json.loads(r"""
[
  {
    "filename": "AAPM Report 31 - Standard Methods for Measuring X Ray Exposures.pdf",
    "iso_reference": "AAPM 31",
    "title": "Standard Methods for Measuring X Ray Exposures",
    "standards_body": "AAPM",
    "status": "active",
    "stage_code": null,
    "edition": null,
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "ANSI_SCTE_51_2018_R2024 Method for Determining Drop Cable Braid Coverage.pdf",
    "iso_reference": "ANSI/SCTE 51",
    "title": "Method for Determining Drop Cable Braid Coverage",
    "standards_body": "ANSI",
    "status": "active",
    "stage_code": null,
    "edition": null,
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "ASME B1.13M-2005 - Metric Screw Threads.pdf",
    "iso_reference": "ASME B1.13M:2005",
    "title": "Metric Screw Threads",
    "standards_body": "ASME",
    "status": "active",
    "stage_code": null,
    "edition": "2005",
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "ASTM A313 - SS Wire Specification.pdf",
    "iso_reference": "ASTM A313",
    "title": "SS Wire Specification",
    "standards_body": "ASTM",
    "status": "active",
    "stage_code": null,
    "edition": null,
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "ASTM D2240-15 - Durometer Hardness.pdf",
    "iso_reference": "ASTM D2240-15",
    "title": "Durometer Hardness",
    "standards_body": "ASTM",
    "status": "active",
    "stage_code": null,
    "edition": null,
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "ASTM D4092-2013 - Plastics Dynamic Mechanical Properties Definition.pdf",
    "iso_reference": "ASTM D4092:2013",
    "title": "Plastics Dynamic Mechanical Properties Definition",
    "standards_body": "ASTM",
    "status": "active",
    "stage_code": null,
    "edition": "2013",
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "ASTM-D4169-14 - Shipping Containers.pdf",
    "iso_reference": "ASTM D4169-14",
    "title": "Shipping Containers",
    "standards_body": "ASTM",
    "status": "active",
    "stage_code": null,
    "edition": null,
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "ASTM D4169-22 - Shipping Containers and Systems.pdf",
    "iso_reference": "ASTM D4169-22",
    "title": "Shipping Containers and Systems",
    "standards_body": "ASTM",
    "status": "active",
    "stage_code": null,
    "edition": null,
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "ASTM D5279-21 - Dynamic Properties of Plastics Torsion.pdf",
    "iso_reference": "ASTM D5279-21",
    "title": "Dynamic Properties of Plastics Torsion",
    "standards_body": "ASTM",
    "status": "active",
    "stage_code": null,
    "edition": null,
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "ASTM D638-14 - Plastics Tensile Properties.pdf",
    "iso_reference": "ASTM D638-14",
    "title": "Plastics Tensile Properties",
    "standards_body": "ASTM",
    "status": "active",
    "stage_code": null,
    "edition": null,
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "ASTM D790-15 - Flexural Properties Reinforced Plastics.pdf",
    "iso_reference": "ASTM D790-15",
    "title": "Flexural Properties Reinforced Plastics",
    "standards_body": "ASTM",
    "status": "active",
    "stage_code": null,
    "edition": null,
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "ASTM E8M-13a - Tension Testing of Metallic Materials.pdf",
    "iso_reference": "ASTM E8M-13",
    "title": "Tension Testing of Metallic Materials",
    "standards_body": "ASTM",
    "status": "active",
    "stage_code": null,
    "edition": null,
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "ASTM E94-17 - Radiographic Examination Using Industrial Radiographic.pdf",
    "iso_reference": "ASTM E94-17",
    "title": "Radiographic Examination Using Industrial Radiographic",
    "standards_body": "ASTM",
    "status": "active",
    "stage_code": null,
    "edition": null,
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "ASTM F1801-20 Corrosion Fatigue Metallic Implant.pdf",
    "iso_reference": "ASTM F1801-20",
    "title": "Corrosion Fatigue Metallic Implant",
    "standards_body": "ASTM",
    "status": "active",
    "stage_code": null,
    "edition": null,
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "ASTM F2081-06 - Dimensional Attributes of Vascular Stents.pdf",
    "iso_reference": "ASTM F2081-06",
    "title": "Dimensional Attributes of Vascular Stents",
    "standards_body": "ASTM",
    "status": "active",
    "stage_code": null,
    "edition": null,
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "ASTM F2503-20 - Medical Devices and Other Items for Safety in the Magnetic Resonance Environment.pdf",
    "iso_reference": "ASTM F2503-20",
    "title": "Medical Devices and Other Items for Safety in the Magnetic Resonance Environment",
    "standards_body": "ASTM",
    "status": "active",
    "stage_code": null,
    "edition": null,
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "ASTM F2606-08 - Three point bending stent.pdf",
    "iso_reference": "ASTM F2606-08",
    "title": "Three point bending stent",
    "standards_body": "ASTM",
    "status": "active",
    "stage_code": null,
    "edition": null,
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "ASTM F2924-14 - Specification for Additive Manufacturing Ti6Al4V.pdf",
    "iso_reference": "ASTM F2924-14",
    "title": "Specification for Additive Manufacturing Ti6Al4V",
    "standards_body": "ASTM",
    "status": "active",
    "stage_code": null,
    "edition": null,
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "ASTM F3067-14 - Radial Loading of Stents.pdf",
    "iso_reference": "ASTM F3067-14",
    "title": "Radial Loading of Stents",
    "standards_body": "ASTM",
    "status": "active",
    "stage_code": null,
    "edition": null,
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "F3141-15.pdf",
    "iso_reference": "ASTM F3141:2015",
    "title": "ASTM F3141:2015",
    "standards_body": "ASTM",
    "status": "active",
    "stage_code": null,
    "edition": "2015",
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "ASTM F3306-19 - Ion Release Evaluation of Medical Implants.pdf",
    "iso_reference": "ASTM F3306-19",
    "title": "Ion Release Evaluation of Medical Implants",
    "standards_body": "ASTM",
    "status": "active",
    "stage_code": null,
    "edition": null,
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "ASTM F640-23 - Radiopacity for Medical Use.pdf",
    "iso_reference": "ASTM F640-23",
    "title": "Radiopacity for Medical Use",
    "standards_body": "ASTM",
    "status": "active",
    "stage_code": null,
    "edition": null,
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "ASTM F640-79 - Radiopacity of Plastics for Medical Use.pdf",
    "iso_reference": "ASTM F640-79",
    "title": "Radiopacity of Plastics for Medical Use",
    "standards_body": "ASTM",
    "status": "active",
    "stage_code": null,
    "edition": null,
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "ASTM G5-13 - Potentiodynamic Anodic Polarization.pdf",
    "iso_reference": "ASTM G5-13",
    "title": "Potentiodynamic Anodic Polarization",
    "standards_body": "ASTM",
    "status": "active",
    "stage_code": null,
    "edition": null,
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "ASTM G61-09 - Cyclic Potentiodynamic Polarization.pdf",
    "iso_reference": "ASTM G61-09",
    "title": "Cyclic Potentiodynamic Polarization",
    "standards_body": "ASTM",
    "status": "active",
    "stage_code": null,
    "edition": null,
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "ASTM G71-03 - Galvanic Corrosion.pdf",
    "iso_reference": "ASTM G71-03",
    "title": "Galvanic Corrosion",
    "standards_body": "ASTM",
    "status": "active",
    "stage_code": null,
    "edition": null,
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "BS 546 (1950) - Power Outlet.pdf",
    "iso_reference": "BS 546:1950",
    "title": "Power Outlet",
    "standards_body": "BS",
    "status": "active",
    "stage_code": null,
    "edition": "1950",
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "BS EN 13868 (2002) - Catheter Kink.pdf",
    "iso_reference": "BS EN 13868:2002",
    "title": "Catheter Kink",
    "standards_body": "BS EN",
    "status": "active",
    "stage_code": null,
    "edition": "2002",
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "BS EN 62366-1 (2015) - Usability.pdf",
    "iso_reference": "BS EN 62366-1:2015",
    "title": "Usability",
    "standards_body": "BS EN",
    "status": "active",
    "stage_code": null,
    "edition": "2015",
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "BS ISO 22679 (2021) - Cardiovascular occluders.pdf",
    "iso_reference": "BS ISO 22679:2021",
    "title": "Cardiovascular occluders",
    "standards_body": "BS ISO",
    "status": "active",
    "stage_code": null,
    "edition": "2021",
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "IEC 60227-1 [SASO] - PVC insulated cables.pdf",
    "iso_reference": "IEC 60227-1",
    "title": "PVC insulated cables",
    "standards_body": "IEC",
    "status": "active",
    "stage_code": null,
    "edition": null,
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "IEC 60320 - 1 IS (2001) Appliance couplers for household and similar general purposes.pdf",
    "iso_reference": "IEC 60320-1:2001",
    "title": "Appliance couplers for household and similar general purposes",
    "standards_body": "IEC",
    "status": "active",
    "stage_code": null,
    "edition": "2001",
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "IEC 60417 - Graphical Symbols for Use on Equipment.pdf",
    "iso_reference": "IEC 60417",
    "title": "Graphical Symbols for Use on Equipment",
    "standards_body": "IEC",
    "status": "active",
    "stage_code": null,
    "edition": null,
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "IEC 60529 (2013) - Ingress Protection.pdf",
    "iso_reference": "IEC 60529:2013",
    "title": "Ingress Protection",
    "standards_body": "IEC",
    "status": "active",
    "stage_code": null,
    "edition": "2013",
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "IEC 60601-1-11 (2020) - ME for Home Healthcare.pdf",
    "iso_reference": "IEC 60601-1-11:2020",
    "title": "ME for Home Healthcare",
    "standards_body": "IEC",
    "status": "active",
    "stage_code": null,
    "edition": "2020",
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "IEC 60601-1-6 (2006) - Medical electrical equipment Usability.pdf",
    "iso_reference": "IEC 60601-1-6:2006",
    "title": "Medical electrical equipment Usability",
    "standards_body": "IEC",
    "status": "active",
    "stage_code": null,
    "edition": "2006",
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "IEC 60601-1 (2012) - Medical Electrical Equipments.pdf",
    "iso_reference": "IEC 60601-1:2012",
    "title": "Medical Electrical Equipments",
    "standards_body": "IEC",
    "status": "active",
    "stage_code": null,
    "edition": "2012",
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "IEC 60695-11-10 (2013) - Fire Hazard testing PREVIEW ONLY.pdf",
    "iso_reference": "IEC 60695-11-10:2013",
    "title": "Fire Hazard testing PREVIEW ONLY",
    "standards_body": "IEC",
    "status": "active",
    "stage_code": null,
    "edition": "2013",
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "IEC 60825-1 (2001) - Safety of laser products.pdf",
    "iso_reference": "IEC 60825-1:2001",
    "title": "Safety of laser products",
    "standards_body": "IEC",
    "status": "active",
    "stage_code": null,
    "edition": "2001",
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "IEC 60950-1 (2013) - Information technology equipment Safety.pdf",
    "iso_reference": "IEC 60950-1:2013",
    "title": "Information technology equipment Safety",
    "standards_body": "IEC",
    "status": "active",
    "stage_code": null,
    "edition": "2013",
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "IEC 62304 (2015) - Medical device software – Software life cycle processes.pdf",
    "iso_reference": "IEC 62304:2015",
    "title": "Medical device software – Software life cycle processes",
    "standards_body": "IEC",
    "status": "active",
    "stage_code": null,
    "edition": "2015",
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "IEC 62366 (2007) - Usability engineering to medical devices_en.pdf",
    "iso_reference": "IEC 62366:2007",
    "title": "Medical devices — Application of usability engineering to medical devices",
    "standards_body": "IEC",
    "status": "withdrawn",
    "stage_code": "95.99",
    "edition": "2007",
    "tc_committee": "ISO/TC 210",
    "created_by_upload": false
  },
  {
    "filename": "IEC 62366 (2020) - Usability engineering to medical devices AMD ONLY.pdf",
    "iso_reference": "IEC 62366:2020",
    "title": "Usability engineering to medical devices AMD ONLY",
    "standards_body": "IEC",
    "status": "active",
    "stage_code": null,
    "edition": "2020",
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "IEC TR 80002-1 (2009) - Guidance on medical device software risk management.pdf",
    "iso_reference": "IEC/TR 80002-1:2009",
    "title": "Medical device software — Part 1: Guidance on the application of ISO 14971 to medical device software",
    "standards_body": "IEC",
    "status": "active",
    "stage_code": "60.60",
    "edition": "2009",
    "tc_committee": "ISO/TC 210",
    "created_by_upload": false
  },
  {
    "filename": "IS 1293 (2005) - Plugs and Socket Outlets.pdf",
    "iso_reference": "IS 1293:2005",
    "title": "Plugs and Socket Outlets",
    "standards_body": "IS",
    "status": "active",
    "stage_code": null,
    "edition": "2005",
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "ISO 10079-1 (2015) - Electrically Powered Suction Equipment.pdf",
    "iso_reference": "ISO 10079-1:2015",
    "title": "Electrically Powered Suction Equipment",
    "standards_body": "ISO",
    "status": "active",
    "stage_code": null,
    "edition": "2015",
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "ISO 10079-2 (2014) - Manual Medical Suction Equipment.pdf",
    "iso_reference": "ISO 10079-2:2014",
    "title": "Manual Medical Suction Equipment",
    "standards_body": "ISO",
    "status": "active",
    "stage_code": null,
    "edition": "2014",
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "ISO 10079-3 IS (1999) - Suction Equipment Powered by Vacuum Source.pdf",
    "iso_reference": "ISO 10079-3:1999",
    "title": "Suction Equipment Powered by Vacuum Source",
    "standards_body": "ISO",
    "status": "active",
    "stage_code": null,
    "edition": "1999",
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "ISO 10079-4 (2021) - Medical Suction Equipment General Requirements.pdf",
    "iso_reference": "ISO 10079-4:2021",
    "title": "Medical Suction Equipment General Requirements",
    "standards_body": "ISO",
    "status": "active",
    "stage_code": null,
    "edition": "2021",
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "ISO 10555-1 IS (1995)- Intravascular catheters General Requirements.pdf",
    "iso_reference": "ISO 10555-1:1995",
    "title": "Intravascular catheters General Requirements",
    "standards_body": "ISO",
    "status": "active",
    "stage_code": null,
    "edition": "1995",
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "ISO 10555-1 (2014) - Intravascular catheters General Requirements.pdf",
    "iso_reference": "ISO 10555-1:2014",
    "title": "Intravascular catheters General Requirements",
    "standards_body": "ISO",
    "status": "active",
    "stage_code": null,
    "edition": "2014",
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "ISO 10555-1 (2023) EN - Intravascular catheters General Requirements.pdf",
    "iso_reference": "ISO 10555-1:2023",
    "title": "Intravascular catheters General Requirements",
    "standards_body": "ISO",
    "status": "active",
    "stage_code": null,
    "edition": "2023",
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "ISO 10555-3 (2013) - Central venous catheters.pdf",
    "iso_reference": "ISO 10555-3:2013",
    "title": "Central venous catheters",
    "standards_body": "ISO",
    "status": "active",
    "stage_code": null,
    "edition": "2013",
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "ISO 10993-11 (2017) - Systemic Toxicity.pdf",
    "iso_reference": "ISO 10993-11:2017",
    "title": "Biological evaluation of medical devices — Part 11: Tests for systemic toxicity",
    "standards_body": "ISO",
    "status": "active",
    "stage_code": "90.92",
    "edition": "2017",
    "tc_committee": "ISO/TC 194",
    "created_by_upload": false
  },
  {
    "filename": "ISO 10993-12 (2012) - Biocompatability Sample Preparation.pdf",
    "iso_reference": "ISO 10993-12:2012",
    "title": "Biological evaluation of medical devices — Part 12: Sample preparation and reference materials",
    "standards_body": "ISO",
    "status": "withdrawn",
    "stage_code": "95.99",
    "edition": "2012",
    "tc_committee": "ISO/TC 194",
    "created_by_upload": false
  },
  {
    "filename": "ISO 10993-1 (2018) - Biological evaluation of medical devices Table.pdf",
    "iso_reference": "ISO 10993-1:2018",
    "title": "Biological evaluation of medical devices — Part 1: Evaluation and testing within a risk management process",
    "standards_body": "ISO",
    "status": "withdrawn",
    "stage_code": "95.99",
    "edition": "2018",
    "tc_committee": "ISO/TC 194",
    "created_by_upload": false
  },
  {
    "filename": "ISO 10993-1 (2018) - Biological evaluation of medical devices.pdf",
    "iso_reference": "ISO 10993-1:2018",
    "title": "Biological evaluation of medical devices — Part 1: Evaluation and testing within a risk management process",
    "standards_body": "ISO",
    "status": "withdrawn",
    "stage_code": "95.99",
    "edition": "2018",
    "tc_committee": "ISO/TC 194",
    "created_by_upload": false
  },
  {
    "filename": "ISO 10993-1 (2025) Biological evaluation of medical devices.pdf",
    "iso_reference": "ISO 10993-1:2025",
    "title": "Biological evaluation of medical devices — Part 1: Requirements and general principles for the evaluation of biological safety within a risk management process",
    "standards_body": "ISO",
    "status": "active",
    "stage_code": "60.60",
    "edition": "2025",
    "tc_committee": "ISO/TC 194",
    "created_by_upload": false
  },
  {
    "filename": "ISO 10993-2 (2006) - Animal welfare requirements.pdf",
    "iso_reference": "ISO 10993-2:2006",
    "title": "Biological evaluation of medical devices — Part 2: Animal welfare requirements",
    "standards_body": "ISO",
    "status": "withdrawn",
    "stage_code": "95.99",
    "edition": "2006",
    "tc_committee": "ISO/TC 194",
    "created_by_upload": false
  },
  {
    "filename": "ISO 10993-5 (2009) - In Vitro Cytotoxicity.pdf",
    "iso_reference": "ISO 10993-5:2009",
    "title": "Biological evaluation of medical devices — Part 5: Tests for in vitro cytotoxicity",
    "standards_body": "ISO",
    "status": "active",
    "stage_code": "90.93",
    "edition": "2009",
    "tc_committee": "ISO/TC 194",
    "created_by_upload": false
  },
  {
    "filename": "ISO 11070 (2014) - Introducers, dilators and guidewires.pdf",
    "iso_reference": "ISO 11070:2014",
    "title": "Introducers, dilators and guidewires",
    "standards_body": "ISO",
    "status": "active",
    "stage_code": null,
    "edition": "2014",
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "ISO 11339 (2022) - TPeel Test.pdf",
    "iso_reference": "ISO 11339:2022",
    "title": "TPeel Test",
    "standards_body": "ISO",
    "status": "active",
    "stage_code": null,
    "edition": "2022",
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "ISO 11607-1 (2014) - Medical device packaging Sterile barrier systems.pdf",
    "iso_reference": "ISO 11607-1:2014",
    "title": "Medical device packaging Sterile barrier systems",
    "standards_body": "ISO",
    "status": "active",
    "stage_code": null,
    "edition": "2014",
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "ISO 11607-2 (2014) - Medical device packaging Forming Sealing and Assembly.pdf",
    "iso_reference": "ISO 11607-2:2014",
    "title": "Medical device packaging Forming Sealing and Assembly",
    "standards_body": "ISO",
    "status": "active",
    "stage_code": null,
    "edition": "2014",
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "ISO 12417-1 (2024) - Vascular Device Drug Combination.pdf",
    "iso_reference": "ISO 12417-1:2024",
    "title": "Cardiovascular implants and extracorporeal systems — Vascular device-drug combination products — Part 1: General requirements",
    "standards_body": "ISO",
    "status": "active",
    "stage_code": "60.60",
    "edition": "2024",
    "tc_committee": "ISO/TC 150/SC 2",
    "created_by_upload": false
  },
  {
    "filename": "ISO 13314 (2011) - Compression test for porous metals.pdf",
    "iso_reference": "ISO 13314:2011",
    "title": "Mechanical testing of metals — Ductility testing — Compression test for porous and cellular metals",
    "standards_body": "ISO",
    "status": "active",
    "stage_code": "90.93",
    "edition": "2011",
    "tc_committee": "ISO/TC 164/SC 2",
    "created_by_upload": false
  },
  {
    "filename": "ISO 13485 (2016) - Medical Device QMS.pdf",
    "iso_reference": "ISO 13485:2016",
    "title": "Medical devices — Quality management systems — Requirements for regulatory purposes",
    "standards_body": "ISO",
    "status": "active",
    "stage_code": "90.93",
    "edition": "2016",
    "tc_committee": "ISO/TC 210",
    "created_by_upload": false
  },
  {
    "filename": "ISO 14155 (2020) - Clinical Evaluation.pdf",
    "iso_reference": "ISO 14155:2020",
    "title": "Clinical investigation of medical devices for human subjects — Good clinical practice",
    "standards_body": "ISO",
    "status": "withdrawn",
    "stage_code": "95.99",
    "edition": "2020",
    "tc_committee": "ISO/TC 194",
    "created_by_upload": false
  },
  {
    "filename": "ISO 14243-1-2009.pdf",
    "iso_reference": "ISO 14243-1:2009",
    "title": "Implants for surgery — Wear of total knee-joint prostheses — Part 1: Loading and displacement parameters for wear-testing machines with load control and corresponding environmental conditions for test",
    "standards_body": "ISO",
    "status": "active",
    "stage_code": "90.92",
    "edition": "2009",
    "tc_committee": "ISO/TC 150/SC 4",
    "created_by_upload": false
  },
  {
    "filename": "ISO 14243-2-2016.pdf",
    "iso_reference": "ISO 14243-2:2016",
    "title": "Implants for surgery — Wear of total knee-joint prostheses — Part 2: Methods of measurement",
    "standards_body": "ISO",
    "status": "active",
    "stage_code": "90.92",
    "edition": "2016",
    "tc_committee": "ISO/TC 150/SC 4",
    "created_by_upload": false
  },
  {
    "filename": "ISO 14243-3-2004 cor1-2006.pdf",
    "iso_reference": "ISO 14243-3:2004",
    "title": "Implants for surgery — Wear of total knee-joint prostheses — Part 3: Loading and displacement parameters for wear-testing machines with displacement control and corresponding environmental conditions for test",
    "standards_body": "ISO",
    "status": "withdrawn",
    "stage_code": "95.99",
    "edition": "2004",
    "tc_committee": "ISO/TC 150/SC 4",
    "created_by_upload": false
  },
  {
    "filename": "ISO 14243-3-2004.pdf",
    "iso_reference": "ISO 14243-3:2004",
    "title": "Implants for surgery — Wear of total knee-joint prostheses — Part 3: Loading and displacement parameters for wear-testing machines with displacement control and corresponding environmental conditions for test",
    "standards_body": "ISO",
    "status": "withdrawn",
    "stage_code": "95.99",
    "edition": "2004",
    "tc_committee": "ISO/TC 150/SC 4",
    "created_by_upload": false
  },
  {
    "filename": "ISO 14630 (2008) - Non-active surgical implants.pdf",
    "iso_reference": "ISO 14630:2008",
    "title": "Non-active surgical implants — General requirements",
    "standards_body": "ISO",
    "status": "withdrawn",
    "stage_code": "95.99",
    "edition": "2008",
    "tc_committee": "ISO/TC 150",
    "created_by_upload": false
  },
  {
    "filename": "ISO 14630 (2012) - Non-active surgical implants.pdf",
    "iso_reference": "ISO 14630:2012",
    "title": "Non-active surgical implants — General requirements",
    "standards_body": "ISO",
    "status": "withdrawn",
    "stage_code": "95.99",
    "edition": "2012",
    "tc_committee": "ISO/TC 150",
    "created_by_upload": false
  },
  {
    "filename": "ISO 14708-5 (2010) - Circulatory support devices.pdf",
    "iso_reference": "ISO 14708-5:2010",
    "title": "Implants for surgery — Active implantable medical devices — Part 5: Circulatory support devices",
    "standards_body": "ISO",
    "status": "withdrawn",
    "stage_code": "95.99",
    "edition": "2010",
    "tc_committee": "ISO/TC 150/SC 6",
    "created_by_upload": false
  },
  {
    "filename": "ISO 14971 (2019) - Risk management to medical devices.pdf",
    "iso_reference": "ISO 14971:2019",
    "title": "Medical devices — Application of risk management to medical devices",
    "standards_body": "ISO",
    "status": "active",
    "stage_code": "90.93",
    "edition": "2019",
    "tc_committee": "ISO/TC 210",
    "created_by_upload": false
  },
  {
    "filename": "ISO 15223-1 (2020) - Symbols to be used with medical device labels.pdf",
    "iso_reference": "ISO 15223-1:2020",
    "title": "Symbols to be used with medical device labels",
    "standards_body": "ISO",
    "status": "active",
    "stage_code": null,
    "edition": "2020",
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "ISO 15539 [IS] (2000) - Endovascular Prosthesis.pdf",
    "iso_reference": "ISO 15539:2000",
    "title": "Endovascular Prosthesis",
    "standards_body": "ISO",
    "status": "active",
    "stage_code": null,
    "edition": "2000",
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "ISO 16142-1 (2016) - Essential Principles of Medical Device Safety.pdf",
    "iso_reference": "ISO 16142-1:2016",
    "title": "Medical devices — Recognized essential principles of safety and performance of medical devices — Part 1: General essential principles and additional specific essential principles for all non-IVD medical devices and guidance on the selection of standards",
    "standards_body": "ISO",
    "status": "withdrawn",
    "stage_code": "95.99",
    "edition": "2016",
    "tc_committee": "ISO/TC 210",
    "created_by_upload": false
  },
  {
    "filename": "ISO 16269-6 (2014) - Statistical Tolerance Intervals.pdf",
    "iso_reference": "ISO 16269-6:2014",
    "title": "Statistical Tolerance Intervals",
    "standards_body": "ISO",
    "status": "active",
    "stage_code": null,
    "edition": "2014",
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "ISO 17665 (2024) - Sterilization - Moist Heat.pdf",
    "iso_reference": "ISO 17665:2024",
    "title": "Sterilization of health care products — Moist heat — Requirements for the development, validation and routine control of a sterilization process for medical devices",
    "standards_body": "ISO",
    "status": "active",
    "stage_code": "60.60",
    "edition": "2024",
    "tc_committee": "ISO/TC 198",
    "created_by_upload": false
  },
  {
    "filename": "ISO 20417 (2021) - Medical devices -Information to be Supplied by Manufacturer.pdf",
    "iso_reference": "ISO 20417:2021",
    "title": "Medical devices — Information to be supplied by the manufacturer",
    "standards_body": "ISO",
    "status": "withdrawn",
    "stage_code": "95.99",
    "edition": "2021",
    "tc_committee": "ISO/TC 210",
    "created_by_upload": false
  },
  {
    "filename": "ISO 22679 (2021) - Transcatheter cardiac occluders.pdf",
    "iso_reference": "ISO 22679:2021",
    "title": "Cardiovascular implants — Transcatheter cardiac occluders",
    "standards_body": "ISO",
    "status": "active",
    "stage_code": "60.60",
    "edition": "2021",
    "tc_committee": "ISO/TC 150/SC 2",
    "created_by_upload": false
  },
  {
    "filename": "ISO 24971 (2020) - Guidance on application of ISO14971.pdf",
    "iso_reference": "ISO 24971:2020",
    "title": "Guidance on application of ISO14971",
    "standards_body": "ISO",
    "status": "active",
    "stage_code": null,
    "edition": "2020",
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "ISO 25539-1 (2003) - Endovascular prostheses.pdf",
    "iso_reference": "ISO 25539-1:2003",
    "title": "Cardiovascular implants — Endovascular devices — Part 1: Endovascular prostheses",
    "standards_body": "ISO",
    "status": "withdrawn",
    "stage_code": "95.99",
    "edition": "2003",
    "tc_committee": "ISO/TC 150/SC 2",
    "created_by_upload": false
  },
  {
    "filename": "ISO 25539-1 (2017) - Endovascular Prosthesis.pdf",
    "iso_reference": "ISO 25539-1:2017",
    "title": "Cardiovascular implants — Endovascular devices — Part 1: Endovascular prostheses",
    "standards_body": "ISO",
    "status": "active",
    "stage_code": "90.93",
    "edition": "2017",
    "tc_committee": "ISO/TC 150/SC 2",
    "created_by_upload": false
  },
  {
    "filename": "ISO 25539-2 (2020) - Vascular Stents.pdf",
    "iso_reference": "ISO 25539-2:2020",
    "title": "Cardiovascular implants — Endovascular devices — Part 2: Vascular stents",
    "standards_body": "ISO",
    "status": "active",
    "stage_code": "90.60",
    "edition": "2020",
    "tc_committee": "ISO/TC 150/SC 2",
    "created_by_upload": false
  },
  {
    "filename": "ISO 261 (1998) - ISO Metric Threads General Plan.pdf",
    "iso_reference": "ISO 261:1998",
    "title": "Metric Threads General Plan",
    "standards_body": "ISO",
    "status": "active",
    "stage_code": null,
    "edition": "1998",
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "ISO 3746 (1979) - Sound Power Levels.pdf",
    "iso_reference": "ISO 3746:1979",
    "title": "Sound Power Levels",
    "standards_body": "ISO",
    "status": "active",
    "stage_code": null,
    "edition": "1979",
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "ISO 549-1 (1986) - Luer.PDF",
    "iso_reference": "ISO 549-1:1986",
    "title": "Luer",
    "standards_body": "ISO",
    "status": "active",
    "stage_code": null,
    "edition": "1986",
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "ISO 549-2 (1998) - Luer lock fittings.PDF",
    "iso_reference": "ISO 549-2:1998",
    "title": "Luer lock fittings",
    "standards_body": "ISO",
    "status": "active",
    "stage_code": null,
    "edition": "1998",
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "Graphical Symbols for Use on Equipment (ISO 7000).pdf",
    "iso_reference": "ISO 7000",
    "title": "Graphical Symbols for Use on Equipment",
    "standards_body": "ISO",
    "status": "active",
    "stage_code": null,
    "edition": null,
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "ISO 7000 (2004) - Graphical symbols for use on Equipment.pdf",
    "iso_reference": "ISO 7000:2004",
    "title": "Graphical symbols for use on Equipment",
    "standards_body": "ISO",
    "status": "active",
    "stage_code": null,
    "edition": "2004",
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "Symbol Index ISO 7010.pdf",
    "iso_reference": "ISO 7010",
    "title": "Symbol Index ISO 7010",
    "standards_body": "ISO",
    "status": "active",
    "stage_code": null,
    "edition": null,
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "ISO 7010 (2011) - Registered safety signs.pdf",
    "iso_reference": "ISO 7010:2011",
    "title": "Registered safety signs",
    "standards_body": "ISO",
    "status": "active",
    "stage_code": null,
    "edition": "2011",
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "ISO 80000-1 (2022) - Quantities and units Part 1 General.pdf",
    "iso_reference": "ISO 80000-1:2022",
    "title": "Quantities and units Part 1 General",
    "standards_body": "ISO",
    "status": "active",
    "stage_code": null,
    "edition": "2022",
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "ISO 80369-1 (2018) - Small Bore Connectors.pdf",
    "iso_reference": "ISO 80369-1:2018",
    "title": "Small-bore connectors for liquids and gases in healthcare applications — Part 1: General requirements",
    "standards_body": "ISO",
    "status": "withdrawn",
    "stage_code": "95.99",
    "edition": "2018",
    "tc_committee": "ISO/TC 210",
    "created_by_upload": false
  },
  {
    "filename": "ISO 80369-20 (2015)  - Common test methods for Small Bore Connectors.pdf",
    "iso_reference": "ISO 80369-20:2015",
    "title": "Small-bore connectors for liquids and gases in healthcare applications — Part 20: Common test methods",
    "standards_body": "ISO",
    "status": "withdrawn",
    "stage_code": "95.99",
    "edition": "2015",
    "tc_committee": "ISO/TC 210",
    "created_by_upload": false
  },
  {
    "filename": "ISO 80369-20 - Общие методы испытаний.pdf",
    "iso_reference": "ISO 80369-20:2015",
    "title": "Small-bore connectors for liquids and gases in healthcare applications — Part 20: Common test methods",
    "standards_body": "ISO",
    "status": "withdrawn",
    "stage_code": "95.99",
    "edition": "2015",
    "tc_committee": "ISO/TC 210",
    "created_by_upload": false
  },
  {
    "filename": "ISO 80369-7 (2017) - Small Bore Connectors - Intravascular Connectors (Luer).pdf",
    "iso_reference": "ISO 80369-7:2017",
    "title": "Small Bore Connectors - Intravascular Connectors (Luer)",
    "standards_body": "ISO",
    "status": "active",
    "stage_code": null,
    "edition": "2017",
    "tc_committee": null,
    "created_by_upload": true
  },
  {
    "filename": "ISO TS 37137-1 (2021) - Absorbable Medical Devices.pdf",
    "iso_reference": "ISO/TS 37137-1:2021",
    "title": "Biological evaluation of absorbable medical devices — Part 1: General requirements",
    "standards_body": "ISO",
    "status": "active",
    "stage_code": "90.93",
    "edition": "2021",
    "tc_committee": "ISO/TC 194",
    "created_by_upload": false
  },
  {
    "filename": "USP 788 - Particulate Matter in Injections.pdf",
    "iso_reference": "USP 788",
    "title": "Particulate Matter in Injections",
    "standards_body": "USP",
    "status": "active",
    "stage_code": null,
    "edition": null,
    "tc_committee": null,
    "created_by_upload": true
  }
]
""")


def _nfc(value: str) -> str:
    """Normalise a filename for comparison.

    macOS stores filenames decomposed (NFD); Linux and this file use NFC. A
    name like "Общие методы испытаний.pdf" therefore does not compare equal
    byte-for-byte after an scp from a Mac. Normalising both sides fixes it.
    """
    return unicodedata.normalize("NFC", value)


MAPPING_BY_FILENAME: dict[str, dict[str, Any]] = {
    _nfc(entry["filename"]): entry for entry in MAPPING
}


# ── Result accounting ────────────────────────────────────────────────────────


class Report:
    def __init__(self) -> None:
        self.matched: list[tuple[str, str]] = []          # (file, iso_reference)
        self.created: list[tuple[str, str]] = []          # (file, iso_reference)
        self.already_present: list[tuple[str, str]] = []  # (file, iso_reference)
        self.skipped_draft: list[tuple[str, str]] = []    # (file, iso_reference)
        self.unmapped: list[str] = []                     # on disk, not in MAPPING
        self.missing: list[str] = []                      # in MAPPING, not on disk
        self.failed: list[tuple[str, str]] = []           # (file, error)
        self.orphaned_objects: list[str] = []             # uploaded then DB failed
        self.purged_documents: int = 0
        self.purged_objects: int = 0
        self.purge_failures: list[tuple[str, str]] = []
        self.purchase_flags_cleared: list[str] = []
        self.purchased: list[str] = []

    @property
    def ingested(self) -> int:
        return len(self.matched) + len(self.created)


def log(message: str = "") -> None:
    print(message, flush=True)


def section(title: str) -> None:
    log()
    log(title)
    log("─" * len(title))


# ── Phase 1: preflight ───────────────────────────────────────────────────────


async def preflight(
    db: AsyncSession, args: argparse.Namespace, report: Report
) -> tuple[User, list[Path]]:
    section("1. Preflight")

    backend = settings.STORAGE_BACKEND.lower()
    log(f"  ENVIRONMENT      {settings.ENVIRONMENT}")
    log(f"  STORAGE_BACKEND  {backend}")
    if backend == "s3":
        prefix = settings.S3_PREFIX.strip("/")
        log(f"  S3_BUCKET_NAME   {settings.S3_BUCKET_NAME}")
        log(f"  S3_PREFIX        {prefix or '(none — bucket root)'}")
        log(f"  AWS_REGION       {settings.AWS_REGION}")
    else:
        log(f"  LOCAL_STORAGE    {settings.LOCAL_STORAGE_PATH}")
        if not args.allow_local_storage:
            raise SystemExit(
                "\nSTORAGE_BACKEND is not 's3'. This script is meant to load files into "
                "S3 on production.\nRe-run with --allow-local-storage if writing to local "
                "disk is genuinely what you want."
            )

    # Instantiating the backend also validates that boto3 is installed.
    storage = get_storage_backend()

    if backend == "s3":
        try:
            storage._s3.head_bucket(Bucket=settings.S3_BUCKET_NAME)  # noqa: SLF001
            log(f"  bucket access    OK ({settings.S3_BUCKET_NAME} reachable)")
        except Exception as exc:  # noqa: BLE001
            raise SystemExit(
                f"\nCannot reach the S3 bucket: {exc}\n"
                "Check the instance IAM role (or AWS_ACCESS_KEY_ID/SECRET) and the "
                "bucket name/region."
            ) from exc

    # Actor
    result = await db.execute(select(User).where(User.email == args.actor_email))
    actor = result.scalar_one_or_none()
    if actor is None:
        raise SystemExit(
            f"\nNo user with email {args.actor_email!r}. "
            "Pass --actor-email with an existing account (documents.uploaded_by is NOT NULL)."
        )
    log(f"  uploading as     {actor.email} ({actor.role.value if hasattr(actor.role, 'value') else actor.role})")

    # Source folder
    source = Path(args.source).expanduser().resolve()
    if not source.is_dir():
        raise SystemExit(f"\nSource folder not found: {source}")

    on_disk = sorted(p for p in source.iterdir() if p.is_file() and not p.name.startswith("."))
    log(f"  source folder    {source}")
    log(f"  files on disk    {len(on_disk)}")
    log(f"  mapping entries  {len(MAPPING)}")

    disk_names = {_nfc(p.name) for p in on_disk}
    report.unmapped = sorted(n for n in disk_names if n not in MAPPING_BY_FILENAME)
    report.missing = sorted(n for n in MAPPING_BY_FILENAME if n not in disk_names)

    if report.missing:
        log(f"\n  !! {len(report.missing)} mapped file(s) NOT found in the source folder:")
        for name in report.missing:
            log(f"       - {name}")
    if report.unmapped:
        log(f"\n  !! {len(report.unmapped)} file(s) in the folder with no mapping (will be skipped):")
        for name in report.unmapped:
            log(f"       - {name}")

    to_ingest = [p for p in on_disk if _nfc(p.name) in MAPPING_BY_FILENAME]
    if args.limit:
        to_ingest = to_ingest[: args.limit]
        log(f"\n  --limit {args.limit} → only the first {len(to_ingest)} file(s) will be ingested")

    if report.missing and not args.allow_missing:
        raise SystemExit(
            "\nRefusing to continue with missing files. Copy the whole Standards folder "
            "across, or pass --allow-missing to ingest what is present."
        )

    return actor, to_ingest


# ── Phase 2: purge existing documents ────────────────────────────────────────


async def purge_existing(
    db: AsyncSession, args: argparse.Namespace, report: Report, actor: User
) -> None:
    section("2. Purge existing documents")

    result = await db.execute(select(Document))
    documents = list(result.scalars().all())

    if not documents:
        log("  No documents in the database — nothing to purge.")
        return

    log(f"  {len(documents)} document row(s) will be deleted:")
    for doc in documents:
        log(f"    - {doc.filename}  (storage key: {doc.storage_path})")

    if not args.confirm:
        log("\n  [dry run] no rows or objects deleted")
        report.purged_documents = len(documents)
        report.purged_objects = len(documents)
        return

    storage = get_storage_backend()
    affected_standard_ids = {doc.standard_id for doc in documents}

    for doc in documents:
        try:
            storage.delete(doc.storage_path)
            report.purged_objects += 1
        except Exception as exc:  # noqa: BLE001
            # A missing object is fine — the row still has to go.
            report.purge_failures.append((doc.storage_path, str(exc)))
        await db.delete(doc)  # document_tags cascades
        report.purged_documents += 1

    await write_audit_log(
        db,
        action="document.bulk_purged",
        resource_type="document",
        actor_id=actor.id,
        payload={"count": report.purged_documents, "reason": "pre-ingest cleanup of test uploads"},
    )
    await db.commit()
    log(f"\n  deleted {report.purged_documents} row(s), {report.purged_objects} stored object(s)")
    if report.purge_failures:
        log(f"  {len(report.purge_failures)} object(s) could not be deleted (already gone?):")
        for key, err in report.purge_failures:
            log(f"    - {key}: {err}")

    if args.keep_purchase_flags:
        log("  --keep-purchase-flags: is_purchased left untouched")
        return

    # Clear is_purchased where the standard now has no document at all, so the
    # app's "purchase requires an uploaded document" rule stays true.
    for standard_id in affected_standard_ids:
        remaining = await db.execute(
            select(func.count()).select_from(Document).where(Document.standard_id == standard_id)
        )
        if remaining.scalar_one():
            continue
        standard = await db.get(Standard, standard_id)
        if standard is None or not standard.is_purchased:
            continue
        standard.is_purchased = False
        standard.purchased_at = None
        standard.purchased_by = None
        report.purchase_flags_cleared.append(standard.iso_reference)
    if report.purchase_flags_cleared:
        await db.commit()
        log(f"  cleared is_purchased on {len(report.purchase_flags_cleared)} standard(s) left with no document")


# ── Phase 3: ingest ──────────────────────────────────────────────────────────


async def _find_or_create_standard(
    db: AsyncSession, entry: dict[str, Any], args: argparse.Namespace, actor: User
) -> tuple[Standard | None, bool]:
    """Return (standard, was_created). Returns (None, False) in dry-run when absent."""
    reference = entry["iso_reference"]
    result = await db.execute(select(Standard).where(Standard.iso_reference == reference))
    standard = result.scalar_one_or_none()
    if standard is not None:
        return standard, False

    if not args.confirm:
        return None, True  # would be created

    standard = Standard(
        iso_reference=reference,
        title=entry["title"],
        standards_body=entry.get("standards_body"),
        edition=entry.get("edition"),
        tc_committee=entry.get("tc_committee"),
        status=StandardStatus(entry.get("status") or "active"),
        # The grouping key the Standards list and the dashboard KPIs are built
        # on. Derived with the same helper the feed ingest and the manual-create
        # API use, so a standard added here joins the existing family for its
        # number instead of becoming a permanent singleton group. The column
        # has no default and no event listener: omit it and only
        # scripts/backfill_base_reference.py can repair it afterwards.
        base_reference=_extract_base_reference(reference),
    )
    db.add(standard)
    await db.flush()
    await write_audit_log(
        db,
        action="standard.created",
        resource_type="standard",
        actor_id=actor.id,
        resource_id=standard.id,
        payload={"iso_reference": reference, "title": entry["title"], "source": "bulk ingest"},
    )
    return standard, True


async def ingest(
    db: AsyncSession,
    files: list[Path],
    args: argparse.Namespace,
    report: Report,
    actor: User,
) -> None:
    section(f"3. Ingest ({len(files)} file(s))")

    storage = get_storage_backend()
    width = len(str(len(files)))

    for index, path in enumerate(files, 1):
        entry = MAPPING_BY_FILENAME[_nfc(path.name)]
        reference = entry["iso_reference"]
        prefix = f"  [{index:>{width}}/{len(files)}] {reference:<34}"

        try:
            standard, was_created = await _find_or_create_standard(db, entry, args, actor)

            if standard is not None and is_draft_stage(standard.stage_code) and not args.allow_draft:
                report.skipped_draft.append((path.name, reference))
                log(f"{prefix} SKIP  draft stage {standard.stage_code} — documents are blocked "
                    f"for pre-publication standards (use --allow-draft to override)")
                await db.rollback()
                continue

            with path.open("rb") as fh:
                detected_mime = magic.from_buffer(fh.read(2048), mime=True)
                if detected_mime not in _ALLOWED_MIME_TYPES:
                    raise ValueError(f"file type not allowed: {detected_mime}")

                checksum = compute_sha256(fh)
                size_bytes = path.stat().st_size

                if standard is not None:
                    duplicate = await db.execute(
                        select(Document).where(
                            Document.standard_id == standard.id,
                            Document.sha256_checksum == checksum,
                        )
                    )
                    if duplicate.scalar_one_or_none() is not None:
                        report.already_present.append((path.name, reference))
                        log(f"{prefix} SKIP  identical file already attached")
                        await db.rollback()
                        continue

                if not args.confirm:
                    (report.created if was_created else report.matched).append((path.name, reference))
                    verb = "CREATE standard +" if was_created else "attach to existing,"
                    log(f"{prefix} plan: {verb} upload {size_bytes / 1024 / 1024:.1f} MB")
                    await db.rollback()
                    continue

                assert standard is not None

                max_version = await db.execute(
                    select(func.max(Document.version_number)).where(
                        Document.standard_id == standard.id
                    )
                )
                next_version = (max_version.scalar_one() or 0) + 1

                prior = await db.execute(
                    select(Document).where(
                        Document.standard_id == standard.id,
                        Document.is_current == True,  # noqa: E712
                    )
                )
                for old in prior.scalars().all():
                    old.is_current = False

                storage_key = f"{standard.id}/{next_version}_{path.name}"
                fh.seek(0)
                storage.upload(fh, storage_key)

            try:
                doc = Document(
                    standard_id=standard.id,
                    version_number=next_version,
                    filename=path.name,
                    storage_path=storage_key,
                    file_size_bytes=size_bytes,
                    sha256_checksum=checksum,
                    mime_type=detected_mime,
                    change_notes=args.change_notes,
                    uploaded_by=actor.id,
                    is_current=True,
                )
                db.add(doc)
                await db.flush()

                db.add(DocumentTag(document_id=doc.id, status=DocumentTagStatus.pending))

                if args.mark_purchased and not standard.is_purchased:
                    standard.is_purchased = True
                    standard.purchased_at = dt.datetime.now(dt.timezone.utc)
                    standard.purchased_by = actor.id
                    report.purchased.append(reference)

                await write_audit_log(
                    db,
                    action="document.uploaded",
                    resource_type="document",
                    actor_id=actor.id,
                    resource_id=doc.id,
                    payload={
                        "standard_id": str(standard.id),
                        "filename": path.name,
                        "version_number": next_version,
                        "sha256_checksum": checksum,
                        "file_size_bytes": size_bytes,
                        "source": "bulk ingest",
                    },
                )
                await db.commit()
            except Exception:
                # The object is already in storage but the row is not — record
                # the key so it can be cleaned up rather than silently orphaned.
                report.orphaned_objects.append(storage_key)
                raise

            (report.created if was_created else report.matched).append((path.name, reference))
            log(f"{prefix} OK    v{next_version} → {storage_key}")

            if args.enqueue_tagging:
                from app.tasks.documents import tag_document

                tag_document.delay(str(doc.id))

        except Exception as exc:  # noqa: BLE001
            await db.rollback()
            report.failed.append((path.name, f"{type(exc).__name__}: {exc}"))
            log(f"{prefix} FAIL  {type(exc).__name__}: {exc}")


# ── Phase 4: report ──────────────────────────────────────────────────────────


def write_report(path: Path, report: Report, args: argparse.Namespace) -> None:
    mode = "APPLIED" if args.confirm else "DRY RUN (nothing was written)"
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    def table(rows: list[tuple[str, str]]) -> str:
        if not rows:
            return "_none_\n"
        out = ["| # | File | Standard |", "|---|---|---|"]
        for i, (filename, reference) in enumerate(sorted(rows, key=lambda r: r[1]), 1):
            out.append(f"| {i} | `{filename}` | **{reference}** |")
        return "\n".join(out) + "\n"

    lines = [
        "# Standards folder ingest report",
        "",
        f"- Run: {now}",
        f"- Mode: **{mode}**",
        f"- Source: `{args.source}`",
        f"- Storage: `{settings.STORAGE_BACKEND}`"
        + (
            f" → bucket `{settings.S3_BUCKET_NAME}`"
            f", prefix `{settings.S3_PREFIX.strip('/') or '(root)'}`"
            if settings.STORAGE_BACKEND.lower() == "s3"
            else f" → `{settings.LOCAL_STORAGE_PATH}`"
        ),
        "",
        "| | Count |",
        "|---|---|",
        f"| Documents purged first | {report.purged_documents} |",
        f"| Attached to an existing standard | {len(report.matched)} |",
        f"| Standard created during ingest | {len(report.created)} |",
        f"| Already present (skipped) | {len(report.already_present)} |",
        f"| Skipped — draft stage | {len(report.skipped_draft)} |",
        f"| Skipped — no mapping | {len(report.unmapped)} |",
        f"| Mapped but missing from folder | {len(report.missing)} |",
        f"| Failed | {len(report.failed)} |",
        "",
        "---",
        "",
        f"## Attached to existing standards ({len(report.matched)})",
        "",
        table(report.matched),
        f"## Standards created during ingest ({len(report.created)})",
        "",
        table(report.created),
    ]

    if report.already_present:
        lines += [f"## Already present ({len(report.already_present)})", "", table(report.already_present)]
    if report.skipped_draft:
        lines += [f"## Skipped — draft stage ({len(report.skipped_draft)})", "", table(report.skipped_draft)]
    if report.unmapped:
        lines += [f"## Skipped — no mapping ({len(report.unmapped)})", ""]
        lines += [f"- `{n}`" for n in report.unmapped] + [""]
    if report.missing:
        lines += [f"## Mapped but missing from the folder ({len(report.missing)})", ""]
        lines += [f"- `{n}`" for n in report.missing] + [""]
    if report.failed:
        lines += [f"## Failed ({len(report.failed)})", "", "| File | Error |", "|---|---|"]
        lines += [f"| `{f}` | {e} |" for f, e in report.failed] + [""]
    if report.orphaned_objects:
        lines += [
            f"## Orphaned storage objects ({len(report.orphaned_objects)})",
            "",
            "Uploaded to storage but the database row failed. Delete these manually.",
            "",
        ]
        lines += [f"- `{k}`" for k in report.orphaned_objects] + [""]

    path.write_text("\n".join(lines), encoding="utf-8")


def print_summary(report: Report, args: argparse.Namespace, report_path: Path) -> None:
    section("4. Summary")
    if not args.confirm:
        log("  DRY RUN — nothing was written. Re-run with --confirm to apply.")
    log(f"  purged           {report.purged_documents} document(s)")
    log(f"  attached         {len(report.matched)} to existing standards")
    log(f"  created          {len(report.created)} new standards")
    log(f"  already present  {len(report.already_present)}")
    log(f"  skipped (draft)  {len(report.skipped_draft)}")
    log(f"  skipped (no map) {len(report.unmapped)}")
    log(f"  missing on disk  {len(report.missing)}")
    log(f"  purchased        {len(report.purchased)}")
    log(f"  FAILED           {len(report.failed)}")
    if report.orphaned_objects:
        log(f"  ORPHANED OBJECTS {len(report.orphaned_objects)} — see the report")
    log(f"\n  report written to {report_path}")
    if args.confirm and not args.enqueue_tagging and report.ingested:
        log("\n  AI tagging was not queued. document_tags rows are 'pending'; trigger them")
        log("  later with POST /api/v1/documents/{document_id}/retag.")
    if args.confirm and report.ingested:
        log("\n  Ingest complete — you can now delete the temporary Standards folder from the server.")


# ── Entry point ──────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="One-time bulk ingest of the Standards folder into storage + the documents table.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--source", required=True, help="Folder holding the standard PDFs")
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Actually write. Without this the script is a dry run.",
    )
    parser.add_argument(
        "--purge-existing",
        action="store_true",
        help="Delete every existing document row and stored object first (clears test uploads).",
    )
    parser.add_argument(
        "--keep-purchase-flags",
        action="store_true",
        help="During purge, leave is_purchased set even on standards left with no document.",
    )
    parser.add_argument(
        "--actor-email",
        default="admin@ists.local",
        help="Account recorded as the uploader (default: admin@ists.local)",
    )
    parser.add_argument(
        "--no-mark-purchased",
        dest="mark_purchased",
        action="store_false",
        help="Do not mark ingested standards as purchased (default: mark them).",
    )
    parser.add_argument(
        "--enqueue-tagging",
        action="store_true",
        help="Queue the AI tagging Celery task per document (default: off).",
    )
    parser.add_argument(
        "--allow-draft",
        action="store_true",
        help="Allow attaching documents to pre-publication (stage < 60) standards.",
    )
    parser.add_argument(
        "--allow-missing",
        action="store_true",
        help="Continue even if some mapped files are absent from the source folder.",
    )
    parser.add_argument(
        "--allow-local-storage",
        action="store_true",
        help="Permit running with STORAGE_BACKEND=local instead of s3.",
    )
    parser.add_argument("--limit", type=int, default=0, help="Only ingest the first N files (smoke test).")
    parser.add_argument("--change-notes", default="Bulk ingest of the Standards folder")
    parser.add_argument(
        "--report",
        default="standards_ingest_report.md",
        help="Where to write the markdown report (default: ./standards_ingest_report.md)",
    )
    return parser.parse_args()


async def run(args: argparse.Namespace) -> int:
    report = Report()

    log("=" * 78)
    log("  Standards folder → storage ingest")
    log("=" * 78)

    async with async_session_factory() as db:
        actor, files = await preflight(db, args, report)

        if args.purge_existing:
            await purge_existing(db, args, report, actor)
        else:
            section("2. Purge existing documents")
            log("  --purge-existing not passed — existing documents left untouched.")

        await ingest(db, files, args, report, actor)

    report_path = Path(args.report).expanduser().resolve()
    write_report(report_path, report, args)
    print_summary(report, args, report_path)

    return 1 if (report.failed or report.orphaned_objects) else 0


def main() -> None:
    args = parse_args()
    try:
        raise SystemExit(asyncio.run(run(args)))
    except KeyboardInterrupt:
        log("\nInterrupted. Re-run without --purge-existing to continue where it stopped.")
        raise SystemExit(130) from None


if __name__ == "__main__":
    main()
