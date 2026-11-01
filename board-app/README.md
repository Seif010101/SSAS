# SSAS Board (Android app for the classroom boards)

- `core/` — pure Kotlin: face detection (SCRFD), alignment, recognition (ArcFace), body pose (RTMO),
  the attendance decision, the timetable and the file formats. Tested on the JVM with the same ONNX
  models as SSAS Studio (`ParityTest` compares with the Python results in `src/test/resources`).
- `app/` — the Android app: background camera service, Camera2 capture, USB import, screen.

```bash
# core tests (models from SSAS Studio's model folder)
SSAS_MODELS_DIR=/path/to/models ./gradlew :core:test
# the APK (needs the Android SDK)
./gradlew :app:assembleRelease   # -> app/build/outputs/apk/release/app-release.apk
```

No signing key is kept in this repository. The release build reads it from
`SSAS_KEYSTORE_FILE`, `SSAS_KEYSTORE_PASSWORD`, `SSAS_KEY_ALIAS` and `SSAS_KEY_PASSWORD`; CI fills these
from the GitHub Secrets described in `CONTRIBUTING.md`. Without them a local build is signed with the Android
debug key (testing only), and CI signs with a throw-away key that the release job refuses to publish.
