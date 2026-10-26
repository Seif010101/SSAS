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

The release APK is signed with `keystore/ssas-public.jks` (a public test key) unless
`SSAS_KEYSTORE_FILE`, `SSAS_KEYSTORE_PASSWORD`, `SSAS_KEY_ALIAS` and `SSAS_KEY_PASSWORD` are set.
Anyone can sign an app with the public key, so use your own key for real deployments
(see docs/board-install.md).
