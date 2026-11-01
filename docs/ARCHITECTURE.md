# SSAS architecture (for the team)

SSAS — Seif's Smart Attendance System — takes attendance with the camera of a smart screen at the
start of each session, for any organisation: a school (groups = classes), a company (teams, shifts), a
training centre (courses). This page is the map: what runs where, how data moves, where to change what.
The plain-language explanation (Arabic) is [`HOW-IT-WORKS.md`](HOW-IT-WORKS.md).

## The three programs

| Program | Folder | Runs on | Language | Job |
|---|---|---|---|---|
| **SSAS Studio** — the *Admin App* | `studio/` | the admin's Windows laptop | Python 3.12, PySide6, ONNX Runtime | photos, training (one model per group), timetable, USB export |
| **SSAS Board** — the *Smart Screen App* | `board-app/` | Android smart screens (Android 13) | Kotlin, ONNX Runtime Android | camera at session start, recognition on the screen, result |
| **SSAS Server** (optional) | `server/` | a local PC, or a VPS behind Caddy | Python, FastAPI, SQLite | receives text results, admin pages, CSV |

The website (`index.html`, download page with the release list) lives on branch **`main`** and is
published to https://ssas.ae by Hostinger. All app code lives on the apps branch.

```
 Studio (laptop)                 USB stick (SSAS-USB)                Screen (Android)                 Server
 ───────────────                 ────────────────────                ────────────────                 ──────
 photos ──► embeddings ──► model  app + models + per-screen    ──►   import + SHA-256 checks
 timetable, settings      ──►     board.json + group-*.json          at session start: camera ──►
                                  server/boards.json ─────────────────────────────────────────────►  Boards page
                                                                     result JSON ── HTTPS + token ──►  /api/v1/results
                                                                                                      Today, CSV
```

**Photos never leave the laptop.** The USB carries only the models (public ONNX files) and, per group,
one 512-number row per person (`group-<code>.json`). The server receives only names, ids and statuses.

## Data flow, step by step

1. **Groups** (Studio, `core/storage.py`): `Organisation.add_group/add_person` → `groups/<code>/group.json`
   and one photo folder per person.
2. **Capture** (`core/capture_logic.py`, `core/person_capture.py`, `ui/capture/`): the camera stays on;
   each person steps in, looks straight, turns their head around a ring and blinks (liveness). ~40 aligned
   face crops are saved.
3. **Train** (`core/pipeline.py`, `core/train.py`): SCRFD detects the face, 5 landmarks align it to
   112×112, every photo gets ~10 camera-like variants (`core/augment.py`), ArcFace R50 turns each into a
   512-number embedding (cached in `model/embeddings.npz`). A cosine-margin head is trained per group, with
   the other groups' people as strangers, checked with grouped K-fold cross-validation over several seeds;
   thresholds are calibrated so strangers are accepted ≤ 0.1 %. Output: `model/group-model.json` +
   `report.json`.
4. **Schedule** (`ui/schedule_tab.py`): working days, session times, shared rooms, and per group a weekly
   grid: here / skip / in a shared room. `core/export.py:board_plans()` turns this into one plan per screen
   and reports clashes.
5. **Export** (`core/export.py`): `SSAS-USB/` with the APK, the models, `screens/<screen>/board.json` +
   `group-*.json`, and `server/boards.json` (token **hashes** and people lists only).
6. **Import on the screen** (`board-app/core/.../UsbPackage.kt`): every file name is checked
   (`SafeName`), every file's SHA-256 is checked, the old configuration is replaced only when everything
   arrived intact.
7. **Take attendance** (`app/.../AttendanceService.kt` + `core/.../FramePipeline.kt`, `Attendance.kt`):
   a foreground service wakes 3 min after each session starts, takes up to 8 pictures in 5 min, finds
   faces (SCRFD) and bodies (RTMO pose), drops faces without a body (photo/phone), recognises faces against
   the group model, and decides per person: present / absent / needs_review / no_data. The camera closes.
8. **Send** (`app/.../Uploader.kt`): the result JSON goes over HTTPS with the screen's bearer token (pinned
   certificate when a fingerprint is set). Answers decide: delete, set aside (400), or retry (401/403/5xx).
9. **Server** (`server/ssas_server/api.py`): checks the token, the group, every person against the
   registered list (names are taken from the list, never from the screen), stores one result per
   (group, date, session). Admin pages (`pages.py`): Today grid, session detail, Boards, CSV export.

## Formats

All files are versioned JSON — see [`data-format.md`](data-format.md). Version 2 = groups/people/sessions.
**Change a format in all three programs together**, bump `version` only when an old reader would misread,
and update `data-format.md` in the same change. Studio converts a 0.1 data folder once
(`storage.migrate_v1`); the server converts a 0.1 database once (`db._upgrade_from_v1`).

## Where to change what

| I want to… | Change |
|---|---|
| add a Studio setting | `studio/ssas_studio/core/storage.py` (`Settings`), `ui/settings_tab.py`; if the screen needs it: `core/export.py` + `board-app/core/.../BoardConfig.kt` |
| change how presence is decided | `board-app/core/.../Attendance.kt` (+ `AttendanceTest.kt`) and the table in `docs/board-install.md` |
| change matching / thresholds | `studio/ssas_studio/core/train.py` (calibration) and `board-app/core/.../GroupModel.kt` (`match`) — keep `groupmodel.identify` in Python identical |
| change face maths (detect / align / embed) | both `studio/ssas_studio/core/{detect,align,embed}.py` and `board-app/core/.../{Scrfd,Align,Embedder}.kt`; regenerate fixtures with `studio/tools/make_parity.py`; `ParityTest` must pass |
| add a server page | `server/ssas_server/pages.py` + a template; add it to `tests/test_server.py` |
| change what a screen may send | `server/ssas_server/api.py` (`check_result`) and `Uploader.kt` (how answers are handled) |
| change security headers / limits | `server/ssas_server/security.py`; rerun `python tools/pentest.py` |
| deploy differently | `server/docker-compose.yml` (local, own certificate) or `server/deploy/vps/` (Caddy + Let's Encrypt) |

## Rules that keep it working

- **Studio threads:** never touch a widget from a worker thread; use `ui/workers.run_job()` (callbacks on
  the GUI thread); never connect a worker signal to a lambda; keep `QThread` objects alive until finished.
  `core/` never imports Qt.
- **Screen app:** the camera is opened only by `AttendanceService` inside a capture window (plus the live
  preview while the app is visible); the heavy work runs on its own executor; all file names from the USB
  go through `SafeName`.
- **Server:** every SQL statement uses `?` parameters; templates rely on Jinja autoescape (never `|safe` on
  data); every new route is either under `/api/` (token) or calls `need_login()`; state-changing forms
  check `auth.check_csrf()`.
- **Secrets:** no signing keys, tokens, passwords or photos in the repository (it is public). The Android
  signing key comes from GitHub Secrets (see [`CONTRIBUTING.md`](../CONTRIBUTING.md)).
- **Models:** InsightFace models are non-commercial — never bundle them; Studio downloads them and checks
  their pinned SHA-256 (`core/models.py`).

## Tests and CI

`.github/workflows/build.yml` runs on every push:

| Job | What |
|---|---|
| models | downloads the ONNX models (cached) and checks their SHA-256 |
| studio-tests | ruff + pytest (real models, real Qt offscreen) + start-up smoke test |
| server-tests | ruff + pytest + `tools/pentest.py` (27 attacks against a running server) |
| android | `:core:test` (parity with Python, formats, USB safety) + release APK |
| studio-windows | PyInstaller + Inno Setup installer, started once on Windows |
| release | only on manual run with `release: true`: refuses a test-signed APK, publishes a GitHub Release |

Security model and the latest attack results: [`security.md`](security.md).
