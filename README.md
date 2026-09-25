# BhoomiAI — Stage 1: Local Research Assistant

Free-tools-only SIH starter. Includes a FastAPI backend, PostgreSQL + pgvector, local embedding model, local Ollama LLM, PDF/TXT/MD ingestion and a React frontend. **This is a development prototype, not the complete national platform.** GIS, policy simulation, collaboration and the innovation portal come in later stages.

## Prerequisites
Windows 11, Python 3.11 or 3.12, Node.js 20+, Docker Desktop (WSL 2), Ollama. Download dependencies and models while online. No paid API is required.

## 1. Start PostgreSQL
From the repository root:
```powershell
docker compose up -d
docker compose ps
```
PostgreSQL is mapped to localhost:5433; the password is development-only. Never expose this service publicly.

## 2. Download the local LLM
```powershell
ollama pull gemma3:4b
ollama run gemma3:4b
```
If your laptop runs out of memory, try `ollama pull gemma3:1b` and set `OLLAMA_MODEL=gemma3:1b` in backend/.env.

## 3. Start the Python backend
Open a PowerShell terminal at the repository root:
```powershell
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload
```
If Python 3.11 is not installed but 3.12 is, replace `py -3.11` with `py -3.12`. If PowerShell blocks activation: `Set-ExecutionPolicy -Scope Process Bypass`. The embedding model downloads on first use.

API docs: http://localhost:8000/docs
Health: http://localhost:8000/health

## 4. Start the frontend
In a second terminal, from repository root:
```powershell
cd frontend
npm install
npm run dev
```
Open http://localhost:5173 . Upload sample_documents/demo_only_land_research.txt and ask a question about the example note.

## API endpoints
- GET /health: check DB connection
- POST /documents: upload PDF/TXT/MD (15 MB maximum)
- GET /documents: list indexed docs
- GET /search?q=...: vector similarity retrieval
- POST /chat with JSON {"question":"..."}: locally generated source-grounded answer

## Safety and current limitations
The example document is fictional. Verify cited material. The app only stores extracted text, not original PDFs; retain permitted source copies separately. Scanned PDF OCR, access control, data licensing review, GIS, policy simulations and large-scale indexing are not included yet. Do not expose this development prototype publicly or upload personal landowner information.

## Next stages
1. Add document metadata and state/district filters.
2. Integrate PostGIS, Leaflet and open-licensed geospatial datasets.
3. Add a transparent scenario-based land-use analytics module.
4. Add collaboration and access controls.
5. Add evidence-linked retrieval and research-gap analysis.


## Stage 1.1: Source metadata and research collection

The updated upload form accepts optional document title, state, district and official source URL. The sidebar supports metadata filtering and deleting document indexes. Questions can be filtered by state or district; documents without matching metadata are excluded when filters are applied. The RAG model now requests evidence-based explanatory answers.

**Begin with these public, official source portals** (download and check reuse conditions before uploading):
- Department of Land Resources: annual reports, including 2024–25 and 2025–26: https://dolr.gov.in/en/annual-reports/
- Department of Land Resources: DILRMP guidelines and technical manuals: https://dolr.gov.in/en/document-category/program-dilrmp/
- Ministry of Housing and Urban Affairs: URDPFI urban and regional planning guidelines: https://mohua.gov.in/upload/uploadfiles/files/URDPFI%20Guidelines%20Vol%20I%283%29.pdf

**Suggested first upload:** One DILRMP report. Set title to its actual title, leave state and district blank if national in scope, and paste the official page URL. Add a second document for a state or district only if the document truly concerns that geography. Never label national statistics as district-level data.

Test after pulling the update: upload a new report, observe indexing stages, confirm it appears without refreshing, filter by metadata, then ask a substantive question. Cite claims using the linked sources and manually verify their page references. For regional questions, using the corresponding state/district filter restricts retrieval to explicitly tagged documents.

Stage 1.1 limits: Metadata is manually entered, not automatically inferred. Existing indexed documents retain empty metadata until reimported; the delete action removes a document and its vector index. The development app has no user authentication yet; use only public non-sensitive files and do not expose it to the internet.

## Stage 2 — Local GIS Explorer (prototype)

Stage 2 adds a **separate, local PostGIS 16** development container at localhost:5434, a GeoJSON ingestion API, layer listing/deletion, and an interactive React Leaflet map. The original pgvector database remains at localhost:5433 with its existing volume intact.

After pulling the update, run from the repository root:

```powershell
docker compose up -d
docker compose ps
cd frontend
npm install
npm run dev
```

In a separate terminal, activate backend/.venv and run `uvicorn app.main:app --reload`. **Stage 2 requires the geo_db container to be healthy before the backend starts.** Open `http://127.0.0.1:8000/gis/health` and `http://127.0.0.1:5173`, then select GIS Explorer.

Import `sample_data/SYNTHETIC_demo.geojson` under the layer name **Synthetic demo (not real land use)**. Check the corresponding layer checkbox and inspect the map. To display the optional OpenStreetMap basemap, enable its checkbox while online. Avoid bulk automated tile downloads; respect OSM tile usage policy. The blank local background plus GeoJSON overlays works without basemap requests.

### GIS API
- GET /gis/health: verify PostGIS connectivity.
- POST /gis/layers: GeoJSON file (EPSG:4326), name, optional source_url, licence, description; 10 MB and 5,000-feature import cap.
- GET /gis/layers: layer metadata and counts.
- GET /gis/layers/{id}/features?limit=1000: GeoJSON overlay with a per-request limit.
- DELETE /gis/layers/{id}: remove a layer and its features.

### Next GIS steps
Import genuinely public and appropriately licensed geographic datasets. Our synthetic sample is only a UI test: **it is not an actual Ghaziabad boundary or land-use survey**. To import shapefiles or GeoTIFF/COG later, preprocess locally with free QGIS or GDAL, record CRS, source URL, date and licence, and introduce a raster processing/tiling pipeline. This stage does not yet derive real land-use trends or integrate live government systems. Development-only instance: no authentication or public deployment yet.

## Integrated Stage 3–6 prototype (development version)

This repository now includes **source-based monitoring indicators, a transparent
land-conversion scenario calculator, research workspaces, shared evidence review,
an innovation challenge portal, a region/document evidence graph, related-document
discovery, Markdown research exports, local GeoTIFF ingestion and exploratory
NDVI comparisons**. These are functional prototype components, not a validated
nationwide production platform or an autonomous policy-recommendation system.

### One-time local setup (Windows PowerShell)

Install dependencies using the existing Python 3.12 virtual environment and
Node.js. Install Docker Desktop. Generate random secrets:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48)); print(secrets.token_urlsafe(48))"
```

Place the first generated string into `SESSION_SECRET` and the second into
`BOOTSTRAP_KEY` in `backend/.env`. **Do not commit your .env file.**
Add `GEO_DATABASE_URL` from `backend/.env.example` to an existing .env
if it is absent. The development credentials in docker-compose.yml are **not**
appropriate for exposed or production deployment.

Then run:

```powershell
# From repository root
docker compose up -d
docker compose ps
cd backend
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
uvicorn app.main:app --reload
```

In another PowerShell terminal:

```powershell
cd frontend
npm install
npm run dev
```

Visit http://127.0.0.1:5173 . Click "First-time setup" once and supply your
bootstrap key to create the administrator. Sign in. The server requires a
session for all document, chat, GIS, satellite, and collaboration endpoints.
The token is stored in browser sessionStorage and expires after 8 hours.
**This login flow is development-grade:** add HTTPS, rate limiting, automated
backup, password resets, stronger audit coverage, automated access-control
tests, and professionally managed secrets before any real deployment. Use
public, non-sensitive land datasets only.

### Platform tabs

- **AI Research**: existing RAG pipeline with provenance, basic regional filters.
- **GIS Explorer**: import GeoJSON in EPSG:4326; list/inspect overlays.
- **Research & Policy Hub > Overview**: local document coverage and sourced
  indicator charts. Enter real data rather than fabricated metrics.
- **Research Workspaces**: create projects, add evidence notes, have another
  researcher confirm/reject notes, share projects, export Markdown reports.
- **Policy Lab**: enter source-attributed state/district/year indicators and
  compare *user-specified* conversion assumptions using an explicit formula.
- **Innovation Portal**: admin posts challenges, researchers submit proposals.
- **Satellite Lab**: import a local, appropriately licensed GeoTIFF up to 40 MB;
  preview bands; compare registered overlapping rasters with a simple NDVI
  delta. Choose red/NIR bands correctly; no automated cloud, snow, seasonal,
  atmospheric, multi-sensor or legal land-cover classification yet.
- **Evidence Graph**: explicit region/document/project relationships, limited
  visual graph, corpus-coverage table, embedding-based related publications.

### Free and lawful data

Use freely accessible **official-source** government publications and licensed
geospatial data. An accessible web map is not necessarily an open dataset.
Record dataset name, original publication URL, acquisition year, district,
coordinate reference system and reuse terms. Satellite uploads use original
files on the local disk, not an internet API. Basemap is optional and requires
internet, but local map features and the research assistant do not require
a cloud subscription.

The existing `sample_data/SYNTHETIC_demo.geojson` and fictional example TXT
are labelled as demonstrations, **never official survey records**.

### Evaluation before the SIH presentation

1. `python -m compileall -q backend/app` and `cd frontend; npm run build`.
2. Run the included unit tests. Docker, Python, Node, PostgreSQL, Ollama,
   and both database containers must be healthy.
3. Upload real licensed documents and GeoJSON; verify progress, deletion,
   metadata filters and citations without manually refreshing.
4. Create two accounts, share a project, create/confirm/reject notes and export.
5. Insert a sourced historical indicator; inspect dashboard/chart and explain
   what the indicator does **not** imply causally.
6. Try the scenario input; independently verify every calculated quantity.
7. Upload two truly compatible, cloud-free overlapping reflectance images;
   compare their NDVI and report all limitations.
8. Verify role-based permissions and audit records. Do not expose the server
   publicly until the security review is complete.

**Known gaps:** No production government API connectors, nationwide coverage,
automated access to cadastral/landowner records, validated causal policy
simulation, robust optical/SAR fusion, automatic legal land-use classification,
exhaustive document citation verification or enterprise security certification.


## Advanced source provenance, CSV indicators and data readiness

The **Data & Provenance** tab exposes additive Stage 3–5 functionality:
- Import up to 1,000 user-supplied sourced indicator observations from UTF-8 CSV;
  download a blank template, export indexed indicators and inspect metadata completeness.
- Descriptive year-on-year changes for exact state, district and indicator matches.
  Calculations are suppressed for duplicate year observations or inconsistent units.
- A provenance graph containing only recorded document tags, source URLs, and
  explicit research notes from authorized projects, including their review status.

New authenticated endpoints:
`GET /advanced/data-readiness`,
`GET /advanced/provenance-graph`,
`GET /advanced/indicators/template`,
`POST /advanced/indicators/import-csv` (administrator only),
`GET /advanced/indicators/export`, and
`GET /advanced/indicators/trends?state=...&district=...&indicator=...`.

These tools help expose *coverage and missing metadata within our own repository*.
They do not automatically establish scientific research gaps, authenticate linked
sources, validate policy effectiveness or derive real land-use statistics. Check
original publications and reuse rights independently. Run `python -m pytest -q backend/tests`
in an environment with the backend dependencies installed.


## Integrating the pushed real Ghaziabad data (development workflow)

The `datasets/` directory added in the September 2026 upload contains a real
Survey of India district boundary, a locally clipped ESA WorldCover 2021
GeoTIFF, four Ghaziabad DILRMP XLSX reports, state-level DILRMP reports and
several government PDF publications. **Committing files does not put them into
the running PostgreSQL, PostGIS or local RAG index.** Use the importer below to
register the files on your own computer.

1. Pull the current main branch **after this feature has been merged**. In
   PowerShell at the repository root, start the two local database containers:
   `docker compose up -d`.
2. Install the new spreadsheet dependency:
   `cd backend; .\\.venv\\Scripts\\Activate.ps1; python -m pip install -r requirements.txt`.
   Run `uvicorn app.main:app --reload` and ensure your administrator account
   is already configured. Keep this terminal running.
3. In a second terminal opened at the repository root, preview the files:
   `python backend/scripts/import_ghaziabad.py --dry-run`.
   Then run `python backend/scripts/import_ghaziabad.py`. Enter the **local
   BhoomiAI administrator email and password** at the prompts; credentials
   are not stored in the repository.
4. The importer registers the Ghaziabad Survey of India GeoJSON and clipped
   ESA WorldCover 2021 raster, then indexes four Ghaziabad XLSX workbooks for
   grounded local search. It skips already-imported dataset names/filenames.
   National PDFs and state-wide reports can be uploaded individually using
   the AI Research UI, with their actual geography and source metadata.
5. Open the GIS Explorer tab, select the imported Ghaziabad boundary under
   **Land-cover statistics by district**, then click **Calculate Ghaziabad land
   cover** beside the ESA WorldCover scene. The backend classifies the
   district-clipped raster by the original ESA categorical codes and estimates
   each class area in hectares using a projected equal-area grid.

This analysis measures **land cover**, not cadastral land use, property
ownership or historical change. A single 2021 classification cannot establish
a trend; Sentinel-2 access and registration can be completed later.
Government PDF and XLSX text is indexed as a retrieved source, not silently
converted into verified numeric indicators. Avoid importing screenshots or
scanned PDFs as text without an explicit OCR and verification workflow.
The 2021 annual WorldCover composite is stored with 2021-12-31 in the existing
required `capture_date` column **as a year-end placeholder, not as a scene
acquisition date**. Check original government and ESA terms before reuse.
