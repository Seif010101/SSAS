# Contributing to SSAS

Read [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) first: it explains the three programs and where to change what.

## Branches

- **`main`** — the website only (`index.html`), published to https://ssas.ae by Hostinger on every push.
  Do not put app code there.
- **The apps branch** (`claude/smart-student-attendance-189mro`) — Studio, the screen app, the server, the docs.
  Work on a branch from it and open a pull request into it.

## Set up and run the checks

```bash
# Studio (Admin App) — Python 3.12
cd studio
pip install -r requirements-dev.txt
SSAS_MODELS_DIR=/path/to/models python -m pytest -q     # without the models, the model tests are skipped
ruff check . && ruff format --check .
python run_studio.py

# Screen app (Smart Screen App) — JDK 17; the APK also needs the Android SDK
cd board-app
SSAS_MODELS_DIR=/path/to/models ./gradlew :core:test
./gradlew :app:assembleRelease                           # signed with the debug key without the variables below

# Server — Python 3.12
cd server
pip install -r requirements-dev.txt
python -m pytest -q
ruff check . && ruff format --check .
python tools/pentest.py                                  # 27 attacks against a running server; all must pass
```

The models folder holds `det_10g.onnx`, `w600k_r50.onnx`, `2d106det.onnx` (from InsightFace `buffalo_l`) and
optionally `rtmo-s.onnx`. Studio downloads them into `%LOCALAPPDATA%\SSAS Studio\models`. **Never commit
models, photos, data folders, keys or tokens** — the repository is public.

## Before you push

- The three formats (board.json, group model, result, boards.json) are shared by three programs. If you change
  one, change all three and `docs/data-format.md` together.
- Face maths changed? Regenerate the parity fixtures with `studio/tools/make_parity.py` and run
  `./gradlew :core:test` (ParityTest).
- Server routes or templates changed? Run `tools/pentest.py`.
- Keep commits small, with a message that says why.

## Releasing a new version

1. Make sure CI is green on the apps branch.
2. GitHub → **Actions** → **Build** → **Run workflow**: choose the apps branch, tick **release**, type the
   version (for example `0.2.1`), **Run**.
3. The release job publishes `SSAS-Studio-Setup-<version>.exe`, `ssas-board.apk` and `ssas-server.tar.gz`.
   The website lists it by itself.

The release job **refuses to publish** an APK that was not signed with the private key, so the four secrets
below must exist first.

## The signing key (GitHub Secrets)

Android only installs an update when it is signed with the same key as the installed app. The key is
**not** in the repository; CI reads it from four repository secrets:

| Secret | Value |
|---|---|
| `ANDROID_KEYSTORE_BASE64` | the keystore file (`.p12`) encoded as base64 (one long line) |
| `ANDROID_KEYSTORE_PASSWORD` | the keystore password |
| `ANDROID_KEY_ALIAS` | the key alias (`ssas`) |
| `ANDROID_KEY_PASSWORD` | the key password |

To add them: GitHub → the repository → **Settings** → **Secrets and variables** → **Actions** →
**New repository secret** → name + value → **Add secret** (four times).

To make a new key (only if the old one is lost — every screen then needs the app uninstalled once):

```bash
keytool -genkeypair -storetype PKCS12 -keystore ssas-release.p12 -alias ssas -keyalg RSA -keysize 4096 \
  -validity 10950 -dname "CN=SSAS"
base64 -w0 ssas-release.p12        # the value of ANDROID_KEYSTORE_BASE64
```

Keep the `.p12` file and its password somewhere safe outside the repository (a password manager).

## Reporting a security problem

Please do not open a public issue. Contact the maintainer privately through the repository owner's GitHub
profile; see [`docs/security.md`](docs/security.md) for the security model.
