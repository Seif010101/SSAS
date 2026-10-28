# SSAS — Smart Student Attendance System

At the start of each lesson, the classroom board's camera takes attendance once. It runs for at most
a few minutes, then turns off and sends a text list (present / absent / needs review) to a small school
server. **Each board recognises the students of its own class itself.** It uses a model trained on the
admin laptop. No photo ever leaves the board, and the server never sees or analyses images.

```
 Admin laptop (Windows + NVIDIA)          USB stick                Classroom board (Android 13)          Lab PC (server)
 SSAS Studio                      ──────►  app + models   ──────►  SSAS Board                   ──────►  SSAS Server
 photos · training · timetable             + one folder            camera at lesson start               results (text only)
                                           per board               recognition on the board             admin pages, CSV
```

| Folder | What | Download |
|---|---|---|
| [`studio/`](studio) | **SSAS Studio**: capture student photos, train one model per class, enter the timetable, export to USB | `SSAS-Studio-Setup-<version>.exe` |
| [`board-app/`](board-app) | **SSAS Board**: the Android app for the classroom/lab boards | `ssas-board.apk` |
| [`server/`](server) | **SSAS Server**: receives the boards' results; admin login with password + authenticator code | `ssas-server.tar.gz` |
| [`web/`](web) | Teacher page (look only, not connected yet) | — |

Everything is built by GitHub Actions ([`build.yml`](.github/workflows/build.yml)). The files are on the
repository's **Releases** page.

## Guides (Arabic)

- [Plan](docs/PLAN.md)
- [Using SSAS Studio on the laptop](docs/studio-guide.md)
- [Installing the app on the boards](docs/board-install.md)
- [Turning the lab computer into the server, step by step](docs/server-setup.md)
- [File formats (for developers)](docs/data-format.md)

## Privacy rules

- Student photos stay on the admin laptop (`Documents\SSAS-Data`). They are never copied to the USB,
  the boards, the server, or this repository.
- The face models (InsightFace `buffalo_l`) are for **non-commercial use only**. They are not in the
  installer: Studio downloads them once from the official source and checks their SHA-256.
- The server is meant for the school's network only. Do not expose it to the internet.

## Developing

```bash
# Studio (Python 3.12)
cd studio && pip install -r requirements-dev.txt && pytest
python run_studio.py

# Board app: core logic runs on the JVM; :app needs the Android SDK
cd board-app && ./gradlew :core:test

# Server
cd server && pip install -r requirements-dev.txt && pytest
```

Set `SSAS_MODELS_DIR` to a folder with `det_10g.onnx`, `w600k_r50.onnx`, `2d106det.onnx` (and
optionally `rtmo-s.onnx`) to run the tests that use the real models.
