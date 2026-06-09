# CSES HPM Upload Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the CSES HPM web workflow with an upload-session driven UI and backend data flow.

**Architecture:** Add a new upload-session backend service under the existing FastAPI app, keeping CSES HPM datasource APIs available. The frontend becomes a CSES HPM upload console that creates a session, displays backend-derived metadata/logs, and requests magnetic/orbit plots and exports by `upload_session_id`.

**Tech Stack:** FastAPI, h5py, numpy, matplotlib, React/Vite/TypeScript, local outputs under `<repo>/outputs`.

---

### Task 1: Backend Upload Session

**Files:**
- Create: `backend/app/services/cses_hpm_uploads.py`
- Create: `backend/app/api/routes_cses_hpm_uploads.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_cses_hpm_upload_session_api.py`

- [ ] Write tests for single upload metadata, duplicate upload dedupe, out-of-order sorting, and discontinuous segment detection.
- [ ] Implement upload persistence under `outputs/uploads/cses_hpm/<session_id>/`.
- [ ] Implement HPM_5/HPM_6 recognition, `/UTC_TIME` parsing, quality flag summaries, time sorting, duplicate file/sample removal, and segment ranges.
- [ ] Register the upload routes under `/api/cses-hpm`.

### Task 2: Upload Plot And Export

**Files:**
- Modify: `backend/app/services/cses_hpm_uploads.py`
- Test: `backend/tests/test_cses_hpm_upload_session_api.py`

- [ ] Implement magnetic plot generation per segment, using `/B_FGM` for HPM_5 and `/A211` for HPM_6.
- [ ] Implement interactive orbit HTML with latitude/longitude grid, segment colors, and segment time labels.
- [ ] Implement CSV/DAT/H5 export with manifest and CDF disabled response.

### Task 3: Frontend Upload Console

**Files:**
- Rewrite: `frontend/src/App.tsx`
- Modify: `frontend/src/api.ts`
- Rewrite/extend: `frontend/src/styles.css`
- Copy assets into: `frontend/public/mascots/`
- Test: `frontend/src/App.test.tsx`

- [ ] Replace date/file archive UI with upload-only controls.
- [ ] Track `upload_session_id`, selected plot type, crop range, generated artifact, export format, and run log.
- [ ] Disable spectrogram with a clear reason.
- [ ] Render magnetic PNG artifacts and interactive orbit HTML artifacts.

### Task 4: Docs And Verification

**Files:**
- Modify: `README.md`
- Modify: `DEMO.md`

- [ ] Document upload-driven flow, API examples, commands, tests, and known limitations.
- [ ] Verify backend unit tests.
- [ ] Verify frontend tests and build.
- [ ] Run real-file scenarios for HPM_5 single, duplicate upload, out-of-order upload, and discontinuous segments when available.
