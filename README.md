# SSAS — Seif's Smart Attendance System

Website and downloads: **https://ssas.ae** (published from branch `main`).

At the start of each session, the camera of a smart screen takes attendance once. It runs for at most a few
minutes, then turns off and sends a text list (present / absent / needs review) to an optional server.
**Each screen recognises the people of its own group by itself**, with a small model trained on the admin's
laptop. No photo ever leaves the laptop, and the server never sees or analyses images.

It works for any organisation: a school (groups = classes), a company (teams, shifts), a factory, a training
centre (courses), a gym…

```
 Admin laptop (Windows)            USB stick                 Smart screen (Android 13)            Server (optional)
 SSAS Studio — Admin App   ─────►  app + models     ─────►   SSAS Board — Smart Screen App  ───►  SSAS Server
 photos · training · timetable     + one folder              camera at session start              results (text only)
                                   per screen                recognition on the screen            admin pages, CSV
                                                                                                  (local PC or VPS)
```

| Folder | What | Download |
|---|---|---|
| [`studio/`](studio) | **SSAS Studio** (Admin App): capture people's photos, train one model per group, enter the timetable, export to USB ([developer guide](studio/README.md)) | `SSAS-Studio-Setup-<version>.exe` |
| [`board-app/`](board-app) | **SSAS Board** (Smart Screen App): the Android app for the smart screens | `ssas-board.apk` |
| [`server/`](server) | **SSAS Server**: receives the screens' results; admin login with password + authenticator code | `ssas-server.tar.gz` |
| [`web/`](web) | early supervisor page mock-up (not connected) | — |

Everything is built by GitHub Actions ([`build.yml`](.github/workflows/build.yml)); the files are on the
repository's **Releases** page and on https://ssas.ae.

## Read first

- **[How SSAS works, from zero (Arabic)](docs/HOW-IT-WORKS.md)** — the whole system explained simply, plus the hackathon kit
- [Architecture, for the team](docs/ARCHITECTURE.md) · [Contributing](CONTRIBUTING.md) · [Security](docs/security.md)

## Guides (Arabic)

- [Using SSAS Studio on the laptop](docs/studio-guide.md)
- [Installing the app on the screens](docs/board-install.md)
- [Server on a VPS (Hostinger) with real HTTPS](docs/server-vps.md)
- [Server on a computer in your own network](docs/server-setup.md)
- [Roadmap](docs/ROADMAP.md)
- [File formats (for developers)](docs/data-format.md)

## Privacy rules

- Photos stay on the admin laptop (`Documents\SSAS-Data`). They are never copied to the USB, the screens,
  the server, or this repository.
- The face models (InsightFace `buffalo_l`) are for **non-commercial use only**. They are not in the
  installer: Studio downloads them once from the official source and checks their SHA-256.
- The server receives only names, ids and statuses, over HTTPS. On the internet, use the VPS setup
  (real certificate, TOTP, optional admin address allow-list).

## Developing

```bash
# Studio (Python 3.12)
cd studio && pip install -r requirements-dev.txt && pytest
python run_studio.py

# Screen app: core logic runs on the JVM; :app needs the Android SDK
cd board-app && ./gradlew :core:test

# Server
cd server && pip install -r requirements-dev.txt && pytest && python tools/pentest.py
```

Set `SSAS_MODELS_DIR` to a folder with `det_10g.onnx`, `w600k_r50.onnx`, `2d106det.onnx` (and
optionally `rtmo-s.onnx`) to run the tests that use the real models. More in [CONTRIBUTING.md](CONTRIBUTING.md).
