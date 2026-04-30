# OpenCR Architectural Overhaul v2

## Why The Approved Plan Needs Expansion
The approved ARQ + Redis + SQLite plan fixes the biggest operational problem: the current app keeps job state in memory and loses it on restart. That is necessary, but it is not sufficient for the system you described.

The current codebase still has four structural gaps:

1. `ocr_pipeline/routers/jobs.py` keeps the full control plane in a process-local `jobs` dict and streams directly from in-memory queues.
2. `ocr_pipeline/routers/ui.py` and `ocr_pipeline/models/metadata.py` expose raw filesystem paths instead of durable artifact identifiers.
3. `ocr_pipeline/services/output_writer.py` only emits `.md` and `.meta.json`; there is no dataset/export layer and no Parquet contract.
4. `ocr_pipeline/static/js/app.js` infers progress client-side, assumes one active job, auto-downloads results, and spreads the workflow across tabs instead of a direct operator console.

The redesign therefore needs three first-class outcomes:

- durable OCR jobs
- trainable Parquet dataset export
- a cleaner operator UI/control panel

This document replaces the earlier plan with a fuller architecture that covers all three.

## Current-State Findings

### Backend
- OCR orchestration is concentrated in `BatchProcessor`, which is a good base for refactoring.
- Job execution is launched with `asyncio.create_task`, so queued/running work is not persistent.
- The API accepts user-visible file paths as identifiers, which makes storage brittle and hard to evolve.
- Output generation stops at Markdown and metadata JSON, which is useful for inspection but not for downstream training pipelines.

### Data Model
- `DocumentMetadata` and `PageMetadata` already capture enough signal to seed a dataset export layer: validation status, script direction, token counts, page dimensions, and language hints.
- There is no normalized persistent model for jobs, documents, pages, artifacts, or exports.

### UI / Control Panel
- The UI is serviceable for a demo, but not for operating a queue.
- Progress is estimated in the browser instead of being emitted by the backend as a contract.
- The tab split forces the operator to jump between upload, progress, and results instead of following one clear flow.
- Results are document-centric only; there is no concept of dataset export or export history.

### Test Coverage
- Existing tests only cover text cleaning, script detection, and validation.
- There are no route tests, no job lifecycle tests, no output artifact tests, no dataset export tests, and no browser-level UI tests.

## Target Product Direction
OpenCR should become a small OCR operations platform:

1. ingest PDFs
2. run durable OCR jobs
3. persist document/page/artifact records
4. preview outputs and quality
5. export OCRed content into training-ready Parquet bundles

That should work from both the API and the control panel.

## Target Architecture

### 1. Control Plane
Keep the earlier stack choice:

- FastAPI for API/UI
- ARQ + Redis for durable queued work
- SQLite via SQLAlchemy for persistent job and artifact state

Why this still fits:
- Redis + ARQ solves restart safety and worker decoupling without overbuilding.
- SQLite is enough for a single-node or small deployment and keeps the operational footprint low.
- The data model can be migrated to Postgres later without changing the API contracts.

### 2. Domain Model
Add persistent entities instead of relying on filenames and directories as the system of record.

Recommended tables:

- `jobs`
  - `id`, `status`, `stage`, `progress_percent`, `requested_formats`, `error_message`, timestamps
- `documents`
  - `id`, `job_id`, `source_filename`, `source_sha256`, `page_count`, `status`, summary metrics
- `pages`
  - `id`, `document_id`, `page_number`, `status`, `ocr_text`, `validation_status`, `token_count`, page metrics
- `artifacts`
  - `id`, `owner_type`, `owner_id`, `artifact_type`, `path`, `mime_type`, `size_bytes`, `sha256`
- `dataset_exports`
  - `id`, `job_id`, `status`, `profile`, `row_count`, `granularity`, `bundle_path`, timestamps
- `job_events`
  - append-only progress/event log used for SSE replay and auditability

Important change:
- APIs should return IDs and artifact descriptors, not direct local paths.

### 3. Storage Layout
Introduce a storage service and manifest-driven artifact layout.

Suggested structure:

```text
/data/storage/
  jobs/{job_id}/
    source/{document_id}.pdf
    pages/{document_id}/page-0001.png
    ocr/{document_id}.md
    ocr/{document_id}.meta.json
    datasets/{dataset_export_id}/documents.parquet
    datasets/{dataset_export_id}/pages.parquet
    datasets/{dataset_export_id}/manifest.json
```

Rules:
- source documents get UUID-backed names
- page renders can be optionally persisted when Parquet export is requested
- artifacts are registered in the database as soon as they are created
- raw paths stay internal to the service

### 4. OCR Pipeline Refactor
Refactor `BatchProcessor` into staged services rather than one monolith.

Suggested service split:

- `IngestService`
  - validates uploads, hashes files, stores source PDFs, creates `documents`
- `OCRPipeline`
  - analyze PDF, render page, OCR, clean, validate, collect metadata
- `ArtifactWriter`
  - writes markdown, metadata JSON, page images when needed
- `DatasetExporter`
  - converts persisted OCR outputs into Parquet datasets
- `ProgressPublisher`
  - writes canonical progress updates to DB and publishes them to Redis/SSE

This lets the worker do:

1. mark job `running`
2. process each document/page
3. persist outputs and events
4. optionally export dataset artifacts
5. mark job `completed` or `failed`

### 5. Progress Contract
The backend should become the single source of truth for progress.

Each event should include:

- `job_id`
- `stage`
- `status`
- `progress_percent`
- `document_id`
- `document_name`
- `page_number`
- `message`
- `stats` when relevant

Canonical stages:

- `queued`
- `ingesting`
- `ocr`
- `packaging`
- `exporting`
- `completed`
- `failed`

This removes client-side progress estimation entirely.

## Trainable Parquet Export

### Export Goal
The system must be able to return OCRed documents as training-ready Parquet, not just human-readable Markdown.

The export should support:

- page-level datasets
- document-level datasets
- optional combined export of both

### Minimum Dataset Profiles
Support two export profiles first:

1. `corpus`
   - generic OCR corpus for downstream model training, retrieval, or evaluation
2. `instruction`
   - OCR content packaged for instruction/SFT style downstream work

If only one profile is implemented in the first pass, start with `corpus`.

### Recommended Parquet Outputs

#### `pages.parquet`
One row per OCRed page.

Required columns:

- `dataset_export_id`
- `job_id`
- `document_id`
- `document_name`
- `page_id`
- `page_number`
- `source_pdf_sha256`
- `page_image_path`
- `ocr_text`
- `ocr_markdown`
- `validation_status`
- `validation_issues`
- `script_direction`
- `primary_script`
- `detected_languages`
- `token_count_cl100k`
- `text_length_chars`
- `text_length_words`
- `dpi_used`
- `has_embedded_text`
- `is_image_only`
- `pipeline_version`
- `model_used`
- `split`

#### `documents.parquet`
One row per document.

Required columns:

- `dataset_export_id`
- `job_id`
- `document_id`
- `document_name`
- `source_pdf_sha256`
- `page_count`
- `ocr_markdown`
- `ocr_text_joined`
- `pages_pass`
- `pages_warn`
- `pages_fail`
- `pages_empty`
- `dominant_script`
- `dominant_direction`
- `languages_detected`
- `total_tokens_cl100k`
- `pipeline_version`
- `model_used`
- `split`

### Split Strategy
To make the exports immediately usable for training, the exporter should support deterministic split assignment:

- default: stable hash split by `document_id`
- output values: `train`, `validation`, `test`
- default ratio: `90 / 5 / 5`

This should be configurable at export time.

### Artifact Strategy For Training
For training workflows, the Parquet files should not be the only deliverable.

Each export bundle should contain:

- `pages.parquet`
- `documents.parquet` when requested
- referenced page PNGs when image-backed training is requested
- `manifest.json` with schema version, split ratios, column definitions, and source job IDs

### Implementation Choice
Use `pyarrow` for writing Parquet.

Add dependencies:

- `pyarrow`
- `sqlalchemy`
- `aiosqlite`
- `arq`
- `redis`
- `pytest-asyncio`
- `fakeredis` for tests

`polars` is optional later for analysis, but it is not required to ship the export path.

## API Redesign

### Jobs
Unify single-document and multi-document extraction under one job API.

Proposed endpoints:

- `POST /api/jobs`
  - accepts uploads or stored document IDs, OCR options, and export options
- `GET /api/jobs`
  - list jobs with filters
- `GET /api/jobs/{job_id}`
  - job summary, stages, output artifacts, export artifacts
- `GET /api/jobs/{job_id}/events`
  - replayable event stream or paginated event log
- `GET /api/jobs/{job_id}/stream`
  - SSE for live updates

### Documents
- `GET /api/documents`
- `GET /api/documents/{document_id}`
- `GET /api/documents/{document_id}/content`
- `GET /api/documents/{document_id}/metadata`

### Dataset Exports
- `POST /api/datasets`
  - build a dataset export from a completed job or selected documents
- `GET /api/datasets`
  - list exports
- `GET /api/datasets/{dataset_export_id}`
  - export summary and artifacts
- `GET /api/datasets/{dataset_export_id}/download`
  - downloadable bundle or direct Parquet file access

## UI / Control Panel Redesign

### Product Principle
The UI should feel like an operator console, not a demo viewer.

It should prioritize:

- what is ready
- what is running
- what failed
- what can be exported

### Layout Recommendation
Replace the current three-tab flow with one dashboard made of clear sections:

1. `Intake`
   - upload PDFs
   - select existing inputs
   - choose run profile
2. `Run`
   - OCR options
   - output formats
   - Parquet export toggles
   - one primary action button
3. `Jobs`
   - queued, running, completed, failed jobs
   - canonical progress bars from backend percentages
   - current stage and active document
4. `Outputs`
   - document preview
   - metadata preview
   - dataset export history
   - download actions

The event log should move behind a secondary "details" drawer instead of occupying primary screen space.

### Interaction Changes
- Remove automatic result downloads.
- Support multiple recent jobs instead of a single `activeJobId`.
- Show dataset export status next to OCR status.
- Present export options before job start:
  - Markdown
  - Metadata JSON
  - Parquet dataset
- Show concise outcome cards after completion:
  - documents processed
  - pages passed/warned/failed
  - datasets exported

### Visual Direction
Keep the interface clean and direct:

- restrained palette with high contrast
- one primary accent color
- dense but readable tables/cards
- explicit typography hierarchy
- no decorative motion beyond lightweight status transitions

The redesign should preserve the zero-build static frontend unless that becomes a delivery bottleneck. Alpine.js can stay if the state model is cleaned up; a framework rewrite is not required for this overhaul.

## Test Strategy

### 1. Unit Tests
Add unit tests for:

- `StorageService`
  - UUID naming, path safety, artifact registration
- `DatasetExporter`
  - correct column set
  - deterministic split assignment
  - row counts for page/document exports
- `ProgressPublisher`
  - canonical progress percentages and stage transitions
- refactored OCR pipeline stages
  - event emission
  - failure propagation
  - export trigger behavior

### 2. API / Integration Tests
Use FastAPI test clients and mocked worker dependencies for:

- creating jobs
- querying job status
- SSE event shape and ordering
- listing documents and artifacts
- creating dataset exports
- downloading export bundles

Important fixtures:

- small sample PDF
- mocked OCR engine returning stable text
- fake Redis or `fakeredis`
- temp SQLite database

### 3. Artifact Tests
Add tests that read produced files and assert:

- Markdown output exists and contains expected pages
- metadata JSON matches persisted DB records
- Parquet files are readable with `pyarrow`
- Parquet schema matches the documented contract
- manifest references only existing artifacts

### 4. End-to-End UI Tests
Add browser-level tests for the operator flow.

Recommended coverage:

1. upload/select a PDF
2. start OCR with Parquet export enabled
3. watch job move through stages
4. open completed document preview
5. download or inspect exported dataset

Playwright is the most direct choice for this because the UI is static HTML/JS and needs real browser verification.

## Delivery Phases

### Phase 0. Contract First
- define schema version for events and Parquet exports
- define DB models
- define storage layout
- add sample fixtures for tests

### Phase 1. Durable Jobs
- add Redis, ARQ, SQLAlchemy, SQLite
- introduce persistent `jobs`, `documents`, `job_events`
- move job execution out of process-local memory

### Phase 2. Artifact Registry
- add `StorageService` and `ArtifactWriter`
- replace path-based API responses with IDs and artifact descriptors
- persist markdown and metadata outputs as registered artifacts

### Phase 3. Dataset Export
- add `DatasetExporter`
- support `pages.parquet`, `documents.parquet`, and `manifest.json`
- expose dataset export APIs and artifact downloads

### Phase 4. UI / Control Panel
- rebuild the current tab UI into an operator dashboard
- simplify progress handling to backend percentages and stage labels
- add outputs and datasets views

### Phase 5. Hardening
- add API, artifact, and UI test coverage
- add retry and failure-path tests
- validate restart/recovery behavior with queued and running jobs

## Migration Notes
- Existing `.md` and `.meta.json` outputs can remain valid artifacts during the transition.
- The current `/api/extract` route should become a compatibility wrapper around `POST /api/jobs` before being retired.
- The new system should keep support for local `input/` and `output/` directories during migration, but those directories should stop being the public API surface.

## Recommended Acceptance Criteria
This redesign is complete when the following are true:

1. a job survives API restarts because state is persisted outside process memory
2. job progress is emitted by the backend as canonical percentages and stages
3. completed OCR jobs can produce training-ready Parquet exports with deterministic splits
4. operators can preview documents and dataset exports from one clean control panel
5. backend, artifact, and UI tests cover the happy path and the most important failure cases

## Final Recommendation
Proceed with the earlier ARQ + Redis + SQLite direction, but expand the scope from "durable OCR jobs" to "durable OCR jobs plus dataset export plus operator console."

If we only implement the approved plan as written, we will still be missing the feature you explicitly asked for: returning OCRed documents as trainable Parquet files through a clean, testable product workflow.
