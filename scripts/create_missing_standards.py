#!/usr/bin/env python3
"""
Create the standards that the Standards/ PDFs need but the database does not
have yet. Run this once, then upload the PDFs against the records it creates.

Why a script: these standards were identified on a local copy of the database.
Their local IDs mean nothing to another environment, so the records have to be
created natively wherever you are uploading. This does that in one pass instead
of 70 manual form submissions.

Usage
-----
  # against the production API
  API_BASE=https://your-domain.com/api/v1 \
  ADMIN_EMAIL=you@example.com ADMIN_PASSWORD='...' \
      python3 scripts/create_missing_standards.py

  # dry run — print what would be created, change nothing
  API_BASE=... ADMIN_EMAIL=... ADMIN_PASSWORD=... \
      python3 scripts/create_missing_standards.py --dry-run

Safe to re-run: a standard whose reference already exists is reported as
"exists" and skipped, never duplicated or overwritten.

Requires manager or admin credentials. Standard library only, no pip installs.
"""
import json
import os
import sys
import urllib.error
import urllib.request

API_BASE = os.environ.get("API_BASE", "http://localhost:8000/api/v1").rstrip("/")
EMAIL = os.environ.get("ADMIN_EMAIL", "admin@ists.local")
PASSWORD = os.environ.get("ADMIN_PASSWORD", "Admin1234!")
DRY_RUN = "--dry-run" in sys.argv

STANDARDS = json.loads(r"""
[
    {
        "iso_reference": "AAPM 31",
        "title": "Standard Methods for Measuring X Ray Exposures",
        "standards_body": "AAPM",
        "edition": null
    },
    {
        "iso_reference": "ANSI/SCTE 51",
        "title": "Method for Determining Drop Cable Braid Coverage",
        "standards_body": "ANSI",
        "edition": null
    },
    {
        "iso_reference": "ASME B1.13M:2005",
        "title": "Metric Screw Threads",
        "standards_body": "ASME",
        "edition": "2005"
    },
    {
        "iso_reference": "ASTM A313",
        "title": "SS Wire Specification",
        "standards_body": "ASTM",
        "edition": null
    },
    {
        "iso_reference": "ASTM D2240-15",
        "title": "Durometer Hardness",
        "standards_body": "ASTM",
        "edition": null
    },
    {
        "iso_reference": "ASTM D4092:2013",
        "title": "Plastics Dynamic Mechanical Properties Definition",
        "standards_body": "ASTM",
        "edition": "2013"
    },
    {
        "iso_reference": "ASTM D4169-14",
        "title": "Shipping Containers",
        "standards_body": "ASTM",
        "edition": null
    },
    {
        "iso_reference": "ASTM D4169-22",
        "title": "Shipping Containers and Systems",
        "standards_body": "ASTM",
        "edition": null
    },
    {
        "iso_reference": "ASTM D5279-21",
        "title": "Dynamic Properties of Plastics Torsion",
        "standards_body": "ASTM",
        "edition": null
    },
    {
        "iso_reference": "ASTM D638-14",
        "title": "Plastics Tensile Properties",
        "standards_body": "ASTM",
        "edition": null
    },
    {
        "iso_reference": "ASTM D790-15",
        "title": "Flexural Properties Reinforced Plastics",
        "standards_body": "ASTM",
        "edition": null
    },
    {
        "iso_reference": "ASTM E8M-13",
        "title": "Tension Testing of Metallic Materials",
        "standards_body": "ASTM",
        "edition": null
    },
    {
        "iso_reference": "ASTM E94-17",
        "title": "Radiographic Examination Using Industrial Radiographic",
        "standards_body": "ASTM",
        "edition": null
    },
    {
        "iso_reference": "ASTM F1801-20",
        "title": "Corrosion Fatigue Metallic Implant",
        "standards_body": "ASTM",
        "edition": null
    },
    {
        "iso_reference": "ASTM F2081-06",
        "title": "Dimensional Attributes of Vascular Stents",
        "standards_body": "ASTM",
        "edition": null
    },
    {
        "iso_reference": "ASTM F2503-20",
        "title": "Medical Devices and Other Items for Safety in the Magnetic Resonance Environment",
        "standards_body": "ASTM",
        "edition": null
    },
    {
        "iso_reference": "ASTM F2606-08",
        "title": "Three point bending stent",
        "standards_body": "ASTM",
        "edition": null
    },
    {
        "iso_reference": "ASTM F2924-14",
        "title": "Specification for Additive Manufacturing Ti6Al4V",
        "standards_body": "ASTM",
        "edition": null
    },
    {
        "iso_reference": "ASTM F3067-14",
        "title": "Radial Loading of Stents",
        "standards_body": "ASTM",
        "edition": null
    },
    {
        "iso_reference": "ASTM F3141:2015",
        "title": "ASTM F3141:2015",
        "standards_body": "ASTM",
        "edition": "2015"
    },
    {
        "iso_reference": "ASTM F3306-19",
        "title": "Ion Release Evaluation of Medical Implants",
        "standards_body": "ASTM",
        "edition": null
    },
    {
        "iso_reference": "ASTM F640-23",
        "title": "Radiopacity for Medical Use",
        "standards_body": "ASTM",
        "edition": null
    },
    {
        "iso_reference": "ASTM F640-79",
        "title": "Radiopacity of Plastics for Medical Use",
        "standards_body": "ASTM",
        "edition": null
    },
    {
        "iso_reference": "ASTM G5-13",
        "title": "Potentiodynamic Anodic Polarization",
        "standards_body": "ASTM",
        "edition": null
    },
    {
        "iso_reference": "ASTM G61-09",
        "title": "Cyclic Potentiodynamic Polarization",
        "standards_body": "ASTM",
        "edition": null
    },
    {
        "iso_reference": "ASTM G71-03",
        "title": "Galvanic Corrosion",
        "standards_body": "ASTM",
        "edition": null
    },
    {
        "iso_reference": "BS 546:1950",
        "title": "Power Outlet",
        "standards_body": "BS",
        "edition": "1950"
    },
    {
        "iso_reference": "BS EN 13868:2002",
        "title": "Catheter Kink",
        "standards_body": "BS EN",
        "edition": "2002"
    },
    {
        "iso_reference": "BS EN 62366-1:2015",
        "title": "Usability",
        "standards_body": "BS EN",
        "edition": "2015"
    },
    {
        "iso_reference": "BS ISO 22679:2021",
        "title": "Cardiovascular occluders",
        "standards_body": "BS ISO",
        "edition": "2021"
    },
    {
        "iso_reference": "IEC 60227-1",
        "title": "PVC insulated cables",
        "standards_body": "IEC",
        "edition": null
    },
    {
        "iso_reference": "IEC 60320-1:2001",
        "title": "Appliance couplers for household and similar general purposes",
        "standards_body": "IEC",
        "edition": "2001"
    },
    {
        "iso_reference": "IEC 60417",
        "title": "Graphical Symbols for Use on Equipment",
        "standards_body": "IEC",
        "edition": null
    },
    {
        "iso_reference": "IEC 60529:2013",
        "title": "Ingress Protection",
        "standards_body": "IEC",
        "edition": "2013"
    },
    {
        "iso_reference": "IEC 60601-1-11:2020",
        "title": "ME for Home Healthcare",
        "standards_body": "IEC",
        "edition": "2020"
    },
    {
        "iso_reference": "IEC 60601-1-6:2006",
        "title": "Medical electrical equipment Usability",
        "standards_body": "IEC",
        "edition": "2006"
    },
    {
        "iso_reference": "IEC 60601-1:2012",
        "title": "Medical Electrical Equipments",
        "standards_body": "IEC",
        "edition": "2012"
    },
    {
        "iso_reference": "IEC 60695-11-10:2013",
        "title": "Fire Hazard testing PREVIEW ONLY",
        "standards_body": "IEC",
        "edition": "2013"
    },
    {
        "iso_reference": "IEC 60825-1:2001",
        "title": "Safety of laser products",
        "standards_body": "IEC",
        "edition": "2001"
    },
    {
        "iso_reference": "IEC 60950-1:2013",
        "title": "Information technology equipment Safety",
        "standards_body": "IEC",
        "edition": "2013"
    },
    {
        "iso_reference": "IEC 62304:2015",
        "title": "Medical device software – Software life cycle processes",
        "standards_body": "IEC",
        "edition": "2015"
    },
    {
        "iso_reference": "IEC 62366:2020",
        "title": "Usability engineering to medical devices AMD ONLY",
        "standards_body": "IEC",
        "edition": "2020"
    },
    {
        "iso_reference": "IS 1293:2005",
        "title": "Plugs and Socket Outlets",
        "standards_body": "IS",
        "edition": "2005"
    },
    {
        "iso_reference": "ISO 10079-1:2015",
        "title": "Electrically Powered Suction Equipment",
        "standards_body": "ISO",
        "edition": "2015"
    },
    {
        "iso_reference": "ISO 10079-2:2014",
        "title": "Manual Medical Suction Equipment",
        "standards_body": "ISO",
        "edition": "2014"
    },
    {
        "iso_reference": "ISO 10079-3:1999",
        "title": "Suction Equipment Powered by Vacuum Source",
        "standards_body": "ISO",
        "edition": "1999"
    },
    {
        "iso_reference": "ISO 10079-4:2021",
        "title": "Medical Suction Equipment General Requirements",
        "standards_body": "ISO",
        "edition": "2021"
    },
    {
        "iso_reference": "ISO 10555-1:1995",
        "title": "Intravascular catheters General Requirements",
        "standards_body": "ISO",
        "edition": "1995"
    },
    {
        "iso_reference": "ISO 10555-1:2014",
        "title": "Intravascular catheters General Requirements",
        "standards_body": "ISO",
        "edition": "2014"
    },
    {
        "iso_reference": "ISO 10555-1:2023",
        "title": "Intravascular catheters General Requirements",
        "standards_body": "ISO",
        "edition": "2023"
    },
    {
        "iso_reference": "ISO 10555-3:2013",
        "title": "Central venous catheters",
        "standards_body": "ISO",
        "edition": "2013"
    },
    {
        "iso_reference": "ISO 11070:2014",
        "title": "Introducers, dilators and guidewires",
        "standards_body": "ISO",
        "edition": "2014"
    },
    {
        "iso_reference": "ISO 11339:2022",
        "title": "TPeel Test",
        "standards_body": "ISO",
        "edition": "2022"
    },
    {
        "iso_reference": "ISO 11607-1:2014",
        "title": "Medical device packaging Sterile barrier systems",
        "standards_body": "ISO",
        "edition": "2014"
    },
    {
        "iso_reference": "ISO 11607-2:2014",
        "title": "Medical device packaging Forming Sealing and Assembly",
        "standards_body": "ISO",
        "edition": "2014"
    },
    {
        "iso_reference": "ISO 15223-1:2020",
        "title": "Symbols to be used with medical device labels",
        "standards_body": "ISO",
        "edition": "2020"
    },
    {
        "iso_reference": "ISO 15539:2000",
        "title": "Endovascular Prosthesis",
        "standards_body": "ISO",
        "edition": "2000"
    },
    {
        "iso_reference": "ISO 16269-6:2014",
        "title": "Statistical Tolerance Intervals",
        "standards_body": "ISO",
        "edition": "2014"
    },
    {
        "iso_reference": "ISO 24971:2020",
        "title": "Guidance on application of ISO14971",
        "standards_body": "ISO",
        "edition": "2020"
    },
    {
        "iso_reference": "ISO 261:1998",
        "title": "Metric Threads General Plan",
        "standards_body": "ISO",
        "edition": "1998"
    },
    {
        "iso_reference": "ISO 3746:1979",
        "title": "Sound Power Levels",
        "standards_body": "ISO",
        "edition": "1979"
    },
    {
        "iso_reference": "ISO 549-1:1986",
        "title": "Luer",
        "standards_body": "ISO",
        "edition": "1986"
    },
    {
        "iso_reference": "ISO 549-2:1998",
        "title": "Luer lock fittings",
        "standards_body": "ISO",
        "edition": "1998"
    },
    {
        "iso_reference": "ISO 7000",
        "title": "Graphical Symbols for Use on Equipment",
        "standards_body": "ISO",
        "edition": null
    },
    {
        "iso_reference": "ISO 7000:2004",
        "title": "Graphical symbols for use on Equipment",
        "standards_body": "ISO",
        "edition": "2004"
    },
    {
        "iso_reference": "ISO 7010",
        "title": "Symbol Index ISO 7010",
        "standards_body": "ISO",
        "edition": null
    },
    {
        "iso_reference": "ISO 7010:2011",
        "title": "Registered safety signs",
        "standards_body": "ISO",
        "edition": "2011"
    },
    {
        "iso_reference": "ISO 80000-1:2022",
        "title": "Quantities and units Part 1 General",
        "standards_body": "ISO",
        "edition": "2022"
    },
    {
        "iso_reference": "ISO 80369-7:2017",
        "title": "Small Bore Connectors - Intravascular Connectors (Luer)",
        "standards_body": "ISO",
        "edition": "2017"
    },
    {
        "iso_reference": "USP 788",
        "title": "Particulate Matter in Injections",
        "standards_body": "USP",
        "edition": null
    }
]
""")


def request(method, path, token=None, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{API_BASE}{path}", data=data,
                                 method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode()
            return resp.status, (json.loads(body) if body else {})
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode(errors="replace")
        try:
            return exc.code, json.loads(raw)
        except ValueError:
            return exc.code, {"detail": raw[:300]}
    except urllib.error.URLError as exc:
        print(f"\nCannot reach {API_BASE} — {exc.reason}", file=sys.stderr)
        sys.exit(1)


def main():
    print(f"target   : {API_BASE}")
    print(f"standards: {len(STANDARDS)}")
    if DRY_RUN:
        print("mode     : DRY RUN (nothing will be created)\n")
        for s in STANDARDS:
            print(f"  would create  {s['iso_reference']:28} {s['title'][:60]}")
        return

    status, resp = request("POST", "/auth/login",
                           payload={"email": EMAIL, "password": PASSWORD})
    if status != 200 or "access_token" not in resp:
        print(f"Login failed (HTTP {status}): {resp.get('detail')}", file=sys.stderr)
        sys.exit(1)
    token = resp["access_token"]
    print("mode     : live\n")

    created = exists = failed = 0
    for s in STANDARDS:
        code, body = request("POST", "/standards", token, s)
        if code == 201:
            created += 1
            print(f"  created  {s['iso_reference']:28} {s['title'][:55]}")
        elif code == 409:
            exists += 1
            print(f"  exists   {s['iso_reference']:28} (skipped)")
        else:
            failed += 1
            print(f"  FAILED   {s['iso_reference']:28} HTTP {code}: "
                  f"{str(body.get('detail'))[:90]}")

    print(f"\ncreated {created}   already existed {exists}   failed {failed}")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()

