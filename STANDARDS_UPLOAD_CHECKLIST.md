# Standards Upload Checklist

Manual upload guide for the 106 PDFs in the `Standards/` folder.

**Why this has to be manual:** the standards were created on a local copy of the
database and given locally-generated IDs. Stored file paths are built from those
IDs, so the files cannot simply be copied to the server — production has to
create its own records as you upload.

## How to use this

Work down the tables; each row is one PDF.

- **Section 1 — already in the system.** Search the reference in the Standards
  library, open it, then **Documents → Upload Document**.
- **Section 2 — needs creating first.** Click **Add Standard**, copy the four
  fields from the table, save, then upload the PDF to it.
- Tick the box as you go.

Once a standard has a document attached, **Mark as Purchased** becomes available
on its detail page. It stays disabled until then, by design — and it is always
disabled for draft-stage standards (CD / WD / AWI, i.e. ISO stage below 60).

## Summary

| | Count |
|---|---|
| Already in the system — just upload | 32 |
| Need creating first, then upload | 70 |
| Too large to upload (Section 3) | 2 |
| No reference in the filename (Section 4) | 4 |
| **Total PDFs** | **106** |

---

## 1. Already in the system — 32 files

| ✓ | PDF file | Search for this reference |
|---|---|---|
| ☐ | `IEC 62366 (2007) - Usability engineering to medical devices_en.pdf` | **IEC 62366:2007** |
| ☐ | `IEC TR 80002-1 (2009) - Guidance on medical device software risk management.pdf` | **IEC/TR 80002-1:2009** |
| ☐ | `ISO 10993-1 (2018) - Biological evaluation of medical devices Table.pdf` | **ISO 10993-1:2018** |
| ☐ | `ISO 10993-1 (2018) - Biological evaluation of medical devices.pdf` | **ISO 10993-1:2018** |
| ☐ | `ISO 10993-1 (2025) Biological evaluation of medical devices.pdf` | **ISO 10993-1:2025** |
| ☐ | `ISO 10993-11 (2017) - Systemic Toxicity.pdf` | **ISO 10993-11:2017** |
| ☐ | `ISO 10993-12 (2012) - Biocompatability Sample Preparation.pdf` | **ISO 10993-12:2012** |
| ☐ | `ISO 10993-2 (2006) - Animal welfare requirements.pdf` | **ISO 10993-2:2006** |
| ☐ | `ISO 10993-5 (2009) - In Vitro Cytotoxicity.pdf` | **ISO 10993-5:2009** |
| ☐ | `ISO 12417-1 (2024) - Vascular Device Drug Combination.pdf` | **ISO 12417-1:2024** |
| ☐ | `ISO 13314 (2011) - Compression test for porous metals.pdf` | **ISO 13314:2011** |
| ☐ | `ISO 13485 (2016) - Medical Device QMS.pdf` | **ISO 13485:2016** |
| ☐ | `ISO 14155 (2020) - Clinical Evaluation.pdf` | **ISO 14155:2020** |
| ☐ | `ISO 14243-1-2009.pdf` | **ISO 14243-1:2009** |
| ☐ | `ISO 14243-2-2016.pdf` | **ISO 14243-2:2016** |
| ☐ | `ISO 14243-3-2004 cor1-2006.pdf` | **ISO 14243-3:2004** |
| ☐ | `ISO 14243-3-2004.pdf` | **ISO 14243-3:2004** |
| ☐ | `ISO 14630 (2008) - Non-active surgical implants.pdf` | **ISO 14630:2008** |
| ☐ | `ISO 14630 (2012) - Non-active surgical implants.pdf` | **ISO 14630:2012** |
| ☐ | `ISO 14708-5 (2010) - Circulatory support devices.pdf` | **ISO 14708-5:2010** |
| ☐ | `ISO 14971 (2019) - Risk management to medical devices.pdf` | **ISO 14971:2019** |
| ☐ | `ISO 16142-1 (2016) - Essential Principles of Medical Device Safety.pdf` | **ISO 16142-1:2016** |
| ☐ | `ISO 17665 (2024) - Sterilization - Moist Heat.pdf` | **ISO 17665:2024** ⚠️ **too large** |
| ☐ | `ISO 20417 (2021) - Medical devices -Information to be Supplied by Manufacturer.pdf` | **ISO 20417:2021** |
| ☐ | `ISO 22679 (2021) - Transcatheter cardiac occluders.pdf` | **ISO 22679:2021** |
| ☐ | `ISO 25539-1 (2003) - Endovascular prostheses.pdf` | **ISO 25539-1:2003** |
| ☐ | `ISO 25539-1 (2017) - Endovascular Prosthesis.pdf` | **ISO 25539-1:2017** |
| ☐ | `ISO 25539-2 (2020) - Vascular Stents.pdf` | **ISO 25539-2:2020** ⚠️ **too large** |
| ☐ | `ISO 80369-1 (2018) - Small Bore Connectors.pdf` | **ISO 80369-1:2018** |
| ☐ | `ISO 80369-20 (2015)  - Common test methods for Small Bore Connectors.pdf` | **ISO 80369-20:2015** |
| ☐ | `ISO 80369-20 - Общие методы испытаний.pdf` | **ISO 80369-20:2015** |
| ☐ | `ISO TS 37137-1 (2021) - Absorbable Medical Devices.pdf` | **ISO/TS 37137-1:2021** |

---

## 2. Need creating first — 70 files

Not in the database. **Add Standard** with these values, then upload the PDF.

Mostly non-ISO bodies (ASTM, ASME, ANSI, BS, USP, AAPM, IS) — your RSS feeds
only cover ISO and IEC, so these were never discovered automatically.

| ✓ | PDF file | Reference | Body | Edition | Title |
|---|---|---|---|---|---|
| ☐ | `AAPM Report 31 - Standard Methods for Measuring X Ray Exposures.pdf` | **AAPM 31** | AAPM | — | Standard Methods for Measuring X Ray Exposures |
| ☐ | `ANSI_SCTE_51_2018_R2024 Method for Determining Drop Cable Braid Coverage.pdf` | **ANSI/SCTE 51** | ANSI | — | Method for Determining Drop Cable Braid Coverage |
| ☐ | `ASME B1.13M-2005 - Metric Screw Threads.pdf` | **ASME B1.13M:2005** | ASME | 2005 | Metric Screw Threads |
| ☐ | `ASTM A313 - SS Wire Specification.pdf` | **ASTM A313** | ASTM | — | SS Wire Specification |
| ☐ | `ASTM D2240-15 - Durometer Hardness.pdf` | **ASTM D2240-15** | ASTM | — | Durometer Hardness |
| ☐ | `ASTM D4092-2013 - Plastics Dynamic Mechanical Properties Definition.pdf` | **ASTM D4092:2013** | ASTM | 2013 | Plastics Dynamic Mechanical Properties Definition |
| ☐ | `ASTM D4169-22 - Shipping Containers and Systems.pdf` | **ASTM D4169-22** | ASTM | — | Shipping Containers and Systems |
| ☐ | `ASTM D5279-21 - Dynamic Properties of Plastics Torsion.pdf` | **ASTM D5279-21** | ASTM | — | Dynamic Properties of Plastics Torsion |
| ☐ | `ASTM D638-14 - Plastics Tensile Properties.pdf` | **ASTM D638-14** | ASTM | — | Plastics Tensile Properties |
| ☐ | `ASTM D790-15 - Flexural Properties Reinforced Plastics.pdf` | **ASTM D790-15** | ASTM | — | Flexural Properties Reinforced Plastics |
| ☐ | `ASTM E8M-13a - Tension Testing of Metallic Materials.pdf` | **ASTM E8M-13** | ASTM | — | Tension Testing of Metallic Materials |
| ☐ | `ASTM E94-17 - Radiographic Examination Using Industrial Radiographic.pdf` | **ASTM E94-17** | ASTM | — | Radiographic Examination Using Industrial Radiographic |
| ☐ | `ASTM F1801-20 Corrosion Fatigue Metallic Implant.pdf` | **ASTM F1801-20** | ASTM | — | Corrosion Fatigue Metallic Implant |
| ☐ | `ASTM F2081-06 - Dimensional Attributes of Vascular Stents.pdf` | **ASTM F2081-06** | ASTM | — | Dimensional Attributes of Vascular Stents |
| ☐ | `ASTM F2503-20 - Medical Devices and Other Items for Safety in the Magnetic Resonance Environment.pdf` | **ASTM F2503-20** | ASTM | — | Medical Devices and Other Items for Safety in the Magnetic Resonance Environment |
| ☐ | `ASTM F2606-08 - Three point bending stent.pdf` | **ASTM F2606-08** | ASTM | — | Three point bending stent |
| ☐ | `ASTM F2924-14 - Specification for Additive Manufacturing Ti6Al4V.pdf` | **ASTM F2924-14** | ASTM | — | Specification for Additive Manufacturing Ti6Al4V |
| ☐ | `ASTM F3067-14 - Radial Loading of Stents.pdf` | **ASTM F3067-14** | ASTM | — | Radial Loading of Stents |
| ☐ | `ASTM F3306-19 - Ion Release Evaluation of Medical Implants.pdf` | **ASTM F3306-19** | ASTM | — | Ion Release Evaluation of Medical Implants |
| ☐ | `ASTM F640-23 - Radiopacity for Medical Use.pdf` | **ASTM F640-23** | ASTM | — | Radiopacity for Medical Use |
| ☐ | `ASTM F640-79 - Radiopacity of Plastics for Medical Use.pdf` | **ASTM F640-79** | ASTM | — | Radiopacity of Plastics for Medical Use |
| ☐ | `ASTM G5-13 - Potentiodynamic Anodic Polarization.pdf` | **ASTM G5-13** | ASTM | — | Potentiodynamic Anodic Polarization |
| ☐ | `ASTM G61-09 - Cyclic Potentiodynamic Polarization.pdf` | **ASTM G61-09** | ASTM | — | Cyclic Potentiodynamic Polarization |
| ☐ | `ASTM G71-03 - Galvanic Corrosion.pdf` | **ASTM G71-03** | ASTM | — | Galvanic Corrosion |
| ☐ | `ASTM-D4169-14 - Shipping Containers.pdf` | **ASTM D4169-14** | ASTM | — | Shipping Containers |
| ☐ | `BS 546 (1950) - Power Outlet.pdf` | **BS 546:1950** | BS | 1950 | Power Outlet |
| ☐ | `BS EN 13868 (2002) - Catheter Kink.pdf` | **BS EN 13868:2002** | BS EN | 2002 | Catheter Kink |
| ☐ | `BS EN 62366-1 (2015) - Usability.pdf` | **BS EN 62366-1:2015** | BS EN | 2015 | Usability |
| ☐ | `BS ISO 22679 (2021) - Cardiovascular occluders.pdf` | **BS ISO 22679:2021** | BS ISO | 2021 | Cardiovascular occluders |
| ☐ | `F3141-15.pdf` | **ASTM F3141:2015** | ASTM | 2015 | ASTM F3141:2015 |
| ☐ | `Graphical Symbols for Use on Equipment (ISO 7000).pdf` | **ISO 7000** | ISO | — | Graphical Symbols for Use on Equipment |
| ☐ | `IEC 60227-1 [SASO] - PVC insulated cables.pdf` | **IEC 60227-1** | IEC | — | PVC insulated cables |
| ☐ | `IEC 60320 - 1 IS (2001) Appliance couplers for household and similar general purposes.pdf` | **IEC 60320-1:2001** | IEC | 2001 | Appliance couplers for household and similar general purposes |
| ☐ | `IEC 60417 - Graphical Symbols for Use on Equipment.pdf` | **IEC 60417** | IEC | — | Graphical Symbols for Use on Equipment |
| ☐ | `IEC 60529 (2013) - Ingress Protection.pdf` | **IEC 60529:2013** | IEC | 2013 | Ingress Protection |
| ☐ | `IEC 60601-1 (2012) - Medical Electrical Equipments.pdf` | **IEC 60601-1:2012** | IEC | 2012 | Medical Electrical Equipments |
| ☐ | `IEC 60601-1-11 (2020) - ME for Home Healthcare.pdf` | **IEC 60601-1-11:2020** | IEC | 2020 | ME for Home Healthcare |
| ☐ | `IEC 60601-1-6 (2006) - Medical electrical equipment Usability.pdf` | **IEC 60601-1-6:2006** | IEC | 2006 | Medical electrical equipment Usability |
| ☐ | `IEC 60695-11-10 (2013) - Fire Hazard testing PREVIEW ONLY.pdf` | **IEC 60695-11-10:2013** | IEC | 2013 | Fire Hazard testing PREVIEW ONLY |
| ☐ | `IEC 60825-1 (2001) - Safety of laser products.pdf` | **IEC 60825-1:2001** | IEC | 2001 | Safety of laser products |
| ☐ | `IEC 60950-1 (2013) - Information technology equipment Safety.pdf` | **IEC 60950-1:2013** | IEC | 2013 | Information technology equipment Safety |
| ☐ | `IEC 62304 (2015) - Medical device software – Software life cycle processes.pdf` | **IEC 62304:2015** | IEC | 2015 | Medical device software – Software life cycle processes |
| ☐ | `IEC 62366 (2020) - Usability engineering to medical devices AMD ONLY.pdf` | **IEC 62366:2020** | IEC | 2020 | Usability engineering to medical devices AMD ONLY |
| ☐ | `IS 1293 (2005) - Plugs and Socket Outlets.pdf` | **IS 1293:2005** | IS | 2005 | Plugs and Socket Outlets |
| ☐ | `ISO 10079-1 (2015) - Electrically Powered Suction Equipment.pdf` | **ISO 10079-1:2015** | ISO | 2015 | Electrically Powered Suction Equipment |
| ☐ | `ISO 10079-2 (2014) - Manual Medical Suction Equipment.pdf` | **ISO 10079-2:2014** | ISO | 2014 | Manual Medical Suction Equipment |
| ☐ | `ISO 10079-3 IS (1999) - Suction Equipment Powered by Vacuum Source.pdf` | **ISO 10079-3:1999** | ISO | 1999 | Suction Equipment Powered by Vacuum Source |
| ☐ | `ISO 10079-4 (2021) - Medical Suction Equipment General Requirements.pdf` | **ISO 10079-4:2021** | ISO | 2021 | Medical Suction Equipment General Requirements |
| ☐ | `ISO 10555-1 (2014) - Intravascular catheters General Requirements.pdf` | **ISO 10555-1:2014** | ISO | 2014 | Intravascular catheters General Requirements |
| ☐ | `ISO 10555-1 (2023) EN - Intravascular catheters General Requirements.pdf` | **ISO 10555-1:2023** | ISO | 2023 | Intravascular catheters General Requirements |
| ☐ | `ISO 10555-1 IS (1995)- Intravascular catheters General Requirements.pdf` | **ISO 10555-1:1995** | ISO | 1995 | Intravascular catheters General Requirements |
| ☐ | `ISO 10555-3 (2013) - Central venous catheters.pdf` | **ISO 10555-3:2013** | ISO | 2013 | Central venous catheters |
| ☐ | `ISO 11070 (2014) - Introducers, dilators and guidewires.pdf` | **ISO 11070:2014** | ISO | 2014 | Introducers, dilators and guidewires |
| ☐ | `ISO 11339 (2022) - TPeel Test.pdf` | **ISO 11339:2022** | ISO | 2022 | TPeel Test |
| ☐ | `ISO 11607-1 (2014) - Medical device packaging Sterile barrier systems.pdf` | **ISO 11607-1:2014** | ISO | 2014 | Medical device packaging Sterile barrier systems |
| ☐ | `ISO 11607-2 (2014) - Medical device packaging Forming Sealing and Assembly.pdf` | **ISO 11607-2:2014** | ISO | 2014 | Medical device packaging Forming Sealing and Assembly |
| ☐ | `ISO 15223-1 (2020) - Symbols to be used with medical device labels.pdf` | **ISO 15223-1:2020** | ISO | 2020 | Symbols to be used with medical device labels |
| ☐ | `ISO 15539 [IS] (2000) - Endovascular Prosthesis.pdf` | **ISO 15539:2000** | ISO | 2000 | Endovascular Prosthesis |
| ☐ | `ISO 16269-6 (2014) - Statistical Tolerance Intervals.pdf` | **ISO 16269-6:2014** | ISO | 2014 | Statistical Tolerance Intervals |
| ☐ | `ISO 24971 (2020) - Guidance on application of ISO14971.pdf` | **ISO 24971:2020** | ISO | 2020 | Guidance on application of ISO14971 |
| ☐ | `ISO 261 (1998) - ISO Metric Threads General Plan.pdf` | **ISO 261:1998** | ISO | 1998 | Metric Threads General Plan |
| ☐ | `ISO 3746 (1979) - Sound Power Levels.pdf` | **ISO 3746:1979** | ISO | 1979 | Sound Power Levels |
| ☐ | `ISO 549-1 (1986) - Luer.PDF` | **ISO 549-1:1986** | ISO | 1986 | Luer |
| ☐ | `ISO 549-2 (1998) - Luer lock fittings.PDF` | **ISO 549-2:1998** | ISO | 1998 | Luer lock fittings |
| ☐ | `ISO 7000 (2004) - Graphical symbols for use on Equipment.pdf` | **ISO 7000:2004** | ISO | 2004 | Graphical symbols for use on Equipment |
| ☐ | `ISO 7010 (2011) - Registered safety signs.pdf` | **ISO 7010:2011** | ISO | 2011 | Registered safety signs |
| ☐ | `ISO 80000-1 (2022) - Quantities and units Part 1 General.pdf` | **ISO 80000-1:2022** | ISO | 2022 | Quantities and units Part 1 General |
| ☐ | `ISO 80369-7 (2017) - Small Bore Connectors - Intravascular Connectors (Luer).pdf` | **ISO 80369-7:2017** | ISO | 2017 | Small Bore Connectors - Intravascular Connectors (Luer) |
| ☐ | `Symbol Index ISO 7010.pdf` | **ISO 7010** | ISO | — | Symbol Index ISO 7010 |
| ☐ | `USP 788 - Particulate Matter in Injections.pdf` | **USP 788** | USP | — | Particulate Matter in Injections |

---

## 3. Too large to upload — 2 files

The app rejects files over **50 MB** (`MAX_UPLOAD_SIZE_MB`), and production nginx
caps request bodies at **55 MB** — so raising the app limit alone is not enough
for the first one. Create the standard record anyway; add the file later.

| PDF file | Size | Options |
|---|---|---|
| `ISO 17665 (2024) - Sterilization - Moist Heat.pdf` | 194.5 MB | Switch to S3 storage, or split the PDF |
| `ISO 25539-2 (2020) - Vascular Stents.pdf` | 53.4 MB | Raise MAX_UPLOAD_SIZE_MB above this size, or switch to S3 |

Setting `STORAGE_BACKEND=s3` removes this ceiling, because the upload no longer
has to pass through nginx as a single request body.

---

## 4. No reference in the filename — 4 files

No standards designation in the name, so no target was guessed — attaching these
to an arbitrary standard would put wrong data in the system. They look like
general symbol glossaries rather than published standards.

| PDF file |
|---|
| `Symbol-EN-Glossary-of-Standard-Symbols-English.pdf` |
| `Symbols-Glossary-0.pdf` |
| `Symbols-Glossary-1.pdf` |
| `Symbols-Glossary-2.pdf` |

Decide the right standard for these yourself, or leave them out.

---

## Judgement calls worth reviewing

- **Six files were created rather than matched to a similar existing record,
  because the edition differed.** Example: the file says `ISO 11607-1 (2014)` but
  the database only held `ISO 11607-1:2019`. Editions are separate records here,
  so putting a 2014 document on the 2019 record would misrepresent it. Same for
  `IEC 62304`, `ISO 11607-2`, `ISO 15223-1`, `ISO 80369-7`.
- **`ISO 80369-20 - Общие методы испытаний.pdf`** has no year in its name. It was
  assigned to the **2015** edition, because the English file beside it states 2015
  and the titles match ("Common test methods"). Change this if it is wrong.
- **Two files map to `ISO 10993-1:2018`** (the standard and its table). Uploading
  the second creates **version 2** of the same document — expected, not an error.
- Titles were derived from the filenames. Skim them; a few are terse.

