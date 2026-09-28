# BhoomiAI — How to Use / Demo Guide

This guide is for the local SIH demonstration of BhoomiAI.

## 1. Start the application

Keep Docker Desktop running.

### Backend

From the project root:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload --host 127.0.0.1
```

The backend should be available at:

```text
http://127.0.0.1:8000
```

Health check:

```text
http://127.0.0.1:8000/health
```

### Frontend

Open a second terminal:

```powershell
cd frontend
npm run dev
```

Open:

```text
http://localhost:5173
```

For the local demo, `BHOOMIAI_LOCAL_DEMO=true` should be present in `backend/.env`.

---

## 2. Import the prepared Ghaziabad datasets

Run this once from the project root:

```powershell
.\backend\.venv\Scripts\python.exe backend\scripts\import_ghaziabad.py
```

This imports the prepared Ghaziabad district boundary, ESA WorldCover raster, and DILRMP spreadsheets already present in the repository.

The importer is designed to skip items that are already present.

---

## 3. AI Research

Open the **AI Research** tab.

Upload a PDF, XLSX, TXT, or MD file from the left panel.

A good first document already included in the repository is:

```text
datasets/government_reports/DoLR_Annual_Report_2024_25.pdf
```

Suggested metadata:

- Title: Department of Land Resources Annual Report 2024-25
- State: leave blank unless the document is state-specific
- District: leave blank unless the document is district-specific
- Source URL: add the official source URL when available

Wait until indexing reaches **100% — Ready to search**.

Suggested demo questions:

```text
What are the major initiatives related to land records modernization?
```

```text
What are the objectives of DILRMP?
```

The answer should include retrieved source passages and citations.

---

## 4. District Dashboard

Open the **District Dashboard** tab.

Choose:

```text
GHAZIABAD
```

The dashboard reads the actual Uttar Pradesh DILRMP Excel reports stored in the repository.

It includes:

- Computerization of Land Records
- Map Digitization
- Modern Record Rooms
- Survey / Re-Survey

Use **Show all source fields** to display original workbook cell references.

You can also select another Uttar Pradesh district under **Compare with**.

For the demo, a simple comparison such as:

```text
Ghaziabad vs Agra
```

is sufficient.

Use **Export sourced CSV** if you want to demonstrate traceable data export.

---

## 5. GIS Explorer

Open the **GIS Explorer** tab.

### Ghaziabad boundary

Locate the imported Ghaziabad district boundary and enable it on the map.

### ESA WorldCover

Under the satellite/raster section, locate:

```text
ESA WorldCover 2021 - Ghaziabad
```

Click **Show georeferenced preview**.

Then choose the Ghaziabad boundary in the boundary selector and click:

```text
Calculate Ghaziabad land cover
```

The application calculates approximate district land-cover area by ESA WorldCover class, such as:

- Tree cover
- Shrubland
- Grassland
- Cropland
- Built-up
- Bare / sparse vegetation
- Water
- Wetland

Results are shown in hectares and percentage share.

These are land-cover estimates from ESA WorldCover 2021, not cadastral or ownership records.

---

## 6. Research & Policy Hub

Open the **Research & Policy Hub** tab.

For a short demo, show only the main capabilities:

### Research Workspaces

Create a project such as:

```text
Title: Land Governance Modernization in Ghaziabad
Region: Ghaziabad, Uttar Pradesh
```

Research notes and evidence can be attached to a project.

### Policy Lab

Use the policy/scenario tools only as exploratory, assumption-based analysis.

Do not present the output as a real policy forecast or causal prediction.

### Satellite Lab

Use this section to manage local raster scenes.

Two-date Sentinel-2 NDVI comparison is optional and not required for the minimum demo.

### Evidence Graph

Show the links between documents, sources, regions, projects, and evidence records.

---

## 7. Data & Provenance

Open the **Data & Provenance** tab.

Use this section to demonstrate that BhoomiAI keeps source and provenance information rather than presenting unsupported AI output.

Useful items include:

- Data readiness
- Indicator coverage
- Source metadata
- Evidence relationships
- Provenance graph
- Source-attributed exports

---

## Recommended SIH demo sequence

Use this sequence during the presentation:

1. **AI Research** — ask one land-governance question and show citations.
2. **District Dashboard** — show Ghaziabad DILRMP statistics and source-cell references.
3. **GIS Explorer** — show the Ghaziabad boundary and ESA WorldCover land-cover analysis.
4. **Research & Policy Hub** — briefly show the research workspace and policy tools.
5. **Data & Provenance** — show traceability of datasets and evidence.

The story should be:

```text
Government documents
        ↓
AI evidence retrieval
        ↓
District statistics
        ↓
GIS and satellite analysis
        ↓
Research workspace
        ↓
Data provenance and export
```

## Minimum definition of a successful demo

BhoomiAI is ready for the SIH prototype demonstration when:

- the frontend and backend start without errors;
- at least one real document is indexed and searchable;
- the AI answer shows source passages;
- the Ghaziabad DILRMP dashboard loads;
- the Ghaziabad boundary appears in GIS Explorer;
- ESA WorldCover statistics can be calculated; and
- the main tabs can be navigated reliably.

Do not spend limited demo preparation time on public deployment, nationwide ingestion, or advanced Sentinel-2 processing unless the essential flow above is already stable.
