# SSAS Studio — developer guide

SSAS Studio is the Windows program on the admin laptop. It photographs the students, trains one face model per
class, holds the timetable, and writes the USB folder the classroom boards import. The user guide (Arabic) is
[`docs/studio-guide.md`](../docs/studio-guide.md); file formats are in [`docs/data-format.md`](../docs/data-format.md).

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
│   ├── storage.py          School / classes / students / settings on disk (plain JSON + folders)
│   ├── models.py           the ONNX models: download, check, open (GPU when available)
│   ├── detect.py           SCRFD face detector        ─┐
│   ├── align.py            5-point face alignment      │ the same maths as the board app
│   ├── embed.py            ArcFace embedder            │ (board-app/core, checked by parity tests)
│   ├── landmarks.py        106 landmarks: head pose, blink
│   ├── quality.py          is a photo sharp / bright / big enough
│   ├── capture_logic.py    one student's capture: straight photos, ring parts, blink, one person only
│   ├── student_capture.py  a whole class: wait for a steady face, capture, "Done", next student
│   ├── augment.py          make laptop photos look like the classroom camera
│   ├── train.py            the classifier, cross-validation, thresholds (numpy only)
│   ├── pipeline.py         photos → embeddings (cached) → trained class model + report
│   ├── classmodel.py       the class-model file the board reads
│   └── export.py           the SSAS-USB folder
└── ui/                 Qt widgets only; the work is done by core/
    ├── main_window.py      the tabs
    ├── context.py          AppContext: shared state + signals (classes_changed, photos_changed, ...)
    ├── workers.py          run_job(): background work with callbacks on the GUI thread
    ├── common.py           small helpers (buttons, labels, dialogs, ClassPicker)
    ├── theme.py            colours and the style sheet (always light, also in Windows dark mode)
    ├── classes_tab.py · train_tab.py · schedule_tab.py · export_tab.py · settings_tab.py
    └── capture/            the Capture tab: tab.py (widgets), worker.py (camera thread), ring_view.py (painting)
```

## Data flow

1. **Classes tab** → `School.add_class/add_student` → `screens/<class>/class.json` and one folder per student.
2. **Capture tab** → `capture/worker.py` reads the camera; `StudentCapture.step()` decides per frame; photos are
   saved as JPEG crops in the student's folder.
3. **Train tab** → `pipeline.train_and_save()`: detect + align + augment + embed every photo (cached in
   `model/embeddings.npz`), train with cross-validation (`train.py`), write `model/class-model.json` + `report.json`.
4. **Export tab** → `export.export_usb()` → `SSAS-USB/` (APK, models, one folder per board, server keys).

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
- **Formats** that leave the laptop (class model, board file, USB folder) are versioned; change
  `docs/data-format.md` and the board app together.

## How to …

- **Add a setting:** a field with a default in `core/storage.py` → `Settings`; a widget in `ui/settings_tab.py`
  (`load`/`save`); if the board needs it, write it in `core/export.py` and read it in the board app.
- **Add a tab:** a `QWidget` subclass in `ui/`, added in `ui/main_window.py`. Use `ClassPicker` for the class
  drop-down and `run_job` for slow work. Refresh from disk in `showEvent`.
- **Change the capture steps:** `core/capture_logic.py` (poses) or `core/student_capture.py` (flow), with tests in
  `tests/test_capture_logic.py`; `tests/test_capture_flow.py` runs the real tab with a fake camera.
