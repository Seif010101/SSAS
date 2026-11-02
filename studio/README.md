# SSAS Studio — developer guide

SSAS Studio is the **Admin App**: the Windows program on the admin's laptop. It photographs the people of each
group, trains one face model per group, holds the timetable, and writes the USB folder the smart screens import.
A group can be a class, a team, a shift or a course. The user guide (Arabic) is
[`docs/studio-guide.md`](../docs/studio-guide.md); file formats are in [`docs/data-format.md`](../docs/data-format.md);
the whole system is explained in [`docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md).

## Run it

```bash
cd studio
pip install -r requirements-dev.txt        # Windows build: requirements-windows.txt
python run_studio.py                       # the app
SSAS_MODELS_DIR=/path/to/models pytest     # tests; the folder holds det_10g.onnx, w600k_r50.onnx, 2d106det.onnx
ruff check . && ruff format --check .      # style (CI runs the same)
```

Without `SSAS_MODELS_DIR` the tests that need the face models are skipped. The installer is built by
`.github/workflows/build.yml` (PyInstaller `packaging/ssas-studio.spec` + Inno Setup `packaging/installer.iss`).

## Folder map

```
ssas_studio/
├── app.py              start-up: logging, theme, main window
├── logs.py             studio.log + crash log + "Something went wrong" dialog
├── resources.py        where things live on disk (data folder, models, bundled APK)
├── core/               no Qt here: plain Python + numpy + OpenCV + ONNX Runtime, all unit-tested
│   ├── storage.py          Organisation / groups / people / settings on disk (JSON + folders), 0.1 upgrade
│   ├── models.py           the ONNX models: download, SHA-256 check, open (GPU when available)
│   ├── detect.py           SCRFD face detector        ─┐
│   ├── align.py            5-point face alignment      │ the same maths as the screen app
│   ├── embed.py            ArcFace embedder            │ (board-app/core, checked by parity tests)
│   ├── landmarks.py        106 landmarks: head pose, blink
│   ├── quality.py          is a photo sharp / bright / big enough
│   ├── capture_logic.py    one person's capture: straight photos, ring parts, blink, one face only
│   ├── person_capture.py   a whole group: wait for a steady face, capture, "Done", next person
│   ├── augment.py          make laptop photos look like the screen's camera
│   ├── train.py            the classifier, cross-validation, thresholds (numpy only)
│   ├── pipeline.py         photos → embeddings (cached) → trained group model + report
│   ├── groupmodel.py       the group-model file the screen reads
│   ├── export.py           the SSAS-USB folder (checks the PIN and the server address first)
│   ├── attendance.py       the screen's decision rules in Python (same as board-app Attendance.kt)
│   └── live.py             the Live demo: recognise a group in a camera picture, the result a screen would send
└── ui/                 Qt widgets only; the work is done by core/
    ├── main_window.py      the tabs
    ├── context.py          AppContext: shared state + signals (groups_changed, photos_changed, ...)
    ├── workers.py          run_job(): background work with callbacks on the GUI thread
    ├── common.py           small helpers (buttons, labels, dialogs, GroupPicker)
    ├── theme.py            colours and the style sheet (always light, also in Windows dark mode)
    ├── groups_tab.py · train_tab.py · schedule_tab.py · export_tab.py · settings_tab.py
    ├── demo_tab.py         ▶ Live demo: the laptop plays the smart screen (no screen, no server needed)
    └── capture/            the Capture tab: tab.py (widgets), worker.py (camera thread), ring_view.py (painting)
```

## Data flow

1. **Groups tab** → `Organisation.add_group/add_person` → `groups/<code>/group.json` and one folder per person.
2. **Capture tab** → `capture/worker.py` reads the camera; `PersonCapture.step()` decides per frame; photos are
   saved as JPEG crops in the person's folder.
3. **Train tab** → `pipeline.train_and_save()`: detect + align + augment + embed every photo (cached in
   `model/embeddings.npz`), train with cross-validation (`train.py`), write `model/group-model.json` + `report.json`.
4. **Schedule tab** → working days, session times, shared rooms, each group's weekly timetable (`org.json`,
   `group.json`).
5. **Export tab** → `export.export_usb()` → `SSAS-USB/` (APK, models, one folder per screen, `server/boards.json`).

## Rules for changes

- **Threads.** Never touch a widget from a background thread. Use `run_job(fn, on_done=..., on_error=...)`: the
  callbacks always run on the GUI thread. Never connect a signal from a worker thread to a `lambda` (PySide runs a
  lambda on the thread that emitted the signal). Connect it to a method of a widget instead.
- **Thread lifetime.** Keep a reference to a `QThread` until it has finished (`thread.finished` → `wait()` → drop
  it). Dropping a running `QThread` kills the program.
- **`AppContext` signals** are emitted from the GUI thread only.
- **`core/` never imports Qt**, so it can be tested and reused. Put decisions there; keep `ui/` thin.
- **Errors** go to `logs.get_logger(...)`. The log is `%LOCALAPPDATA%\SSAS Studio\studio.log`
  (Settings → "Open log folder").
- **Formats** that leave the laptop (group model, board file, USB folder, boards.json) are versioned; change
  `docs/data-format.md`, the screen app and the server together.
- **Security.** Photos never leave the laptop. The screens' admin PIN has no default (6+ digits), the server
  address must be `https://`, and every downloaded model is checked against its pinned SHA-256
  (`docs/security.md`).

## How to …

- **Add a setting:** a field with a default in `core/storage.py` → `Settings`; a widget in `ui/settings_tab.py`
  (`load`/`save`); if the screen needs it, write it in `core/export.py` and read it in the screen app.
- **Add a tab:** a `QWidget` subclass in `ui/`, added in `ui/main_window.py`. Use `GroupPicker` for the group
  drop-down and `run_job` for slow work. Refresh from disk in `showEvent`.
- **Change the capture steps:** `core/capture_logic.py` (poses) or `core/person_capture.py` (flow), with tests in
  `tests/test_capture_logic.py`; `tests/test_capture_flow.py` runs the real tab with a fake camera.
