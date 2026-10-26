# SSAS data formats

Every file SSAS writes is plain JSON (UTF-8) with a `format` name and an integer `version`.
A reader must reject a file whose `format` is wrong or whose `version` is newer than it knows,
and must ignore keys it does not know. Bump `version` only for changes an old reader would
misread; adding an optional key does not need a bump.

| Format | Written by | Read by | Where |
|---|---|---|---|
| `ssas.class-model` v1 | Studio | Board | `screens/<class>/model/class-model.json`, copied to the USB as `class-<class>.json` |
| `ssas.board` v1 | Studio | Board | `SSAS-USB/screens/<board>/board.json` |
| `ssas.usb` v1 | Studio | Board | `SSAS-USB/ssas-usb.json` |
| `ssas.server-boards` v1 | Studio | Server | `SSAS-USB/server/boards.json` |
| `ssas.result` v1 | Board | Server | sent to `POST /api/v1/results`, also kept on the board |

## 1. Laptop data folder (Studio)

```
Documents/SSAS-Data/
├── school.json                 school name, school days, bell times, labs, settings, board tokens
└── screens/
    └── 9A1/
        ├── class.json          class info, students, timetable
        ├── Ahmed Ali/          one folder per student: the photos (never leave the laptop)
        └── model/
            ├── class-model.json
            ├── report.json     training report shown in the Train tab
            └── embeddings.npz  cache; also used as "strangers" when training other classes
```

`class.json` → `students: [{"id": "9A1-001", "name": "...", "folder": "..."}]`.
Ids are `<class>-NNN` and are never reused, so a result always points to one person.
`timetable[day][period]` is `"here"` (take attendance in this room), `"skip"` (PE, break …)
or a lab code (the lab's board takes attendance for this class in that period).

## 2. `ssas.class-model` v1

One trained model per class. It holds no photos and no face embeddings of students — only one
512-number weight row per student, which is the classifier the board uses.

```json
{
  "format": "ssas.class-model",
  "version": 1,
  "class_code": "9A1",
  "created_at": "2026-10-26T10:15:00",
  "studio_version": "0.1.0",
  "method": "head",
  "models": {"detector": {"file": "det_10g.onnx", "sha256": "..."},
             "embedder": {"file": "w600k_r50.onnx", "sha256": "..."}},
  "students": [{"id": "9A1-001", "name": "Ahmed Ali"}],
  "weights": {"dtype": "float32", "shape": [25, 512], "data": "<base64, little-endian>"},
  "thresholds": {"accept": 0.31, "strong": 0.45, "margin": 0.05},
  "metrics": {"accuracy": 0.995, "wrong_student_rate": 0.0, "stranger_accept_rate": 0.0008, "passed": true}
}
```

**Matching one face.** `e` = L2-normalised ArcFace embedding of the aligned 112×112 face.
`scores = W · e`. Let `top`, `second` be the two best scores.

- recognised as `students[argmax]` when `top ≥ accept` and `top − second ≥ margin`;
- the match is *strong* when also `top ≥ strong`;
- otherwise the face is *unknown*.

`method` is `head` (trained cosine classifier) or `prototype` (mean embedding per student);
the board treats both the same way.

## 3. USB folder

```
SSAS-USB/
├── ssas-usb.json          {"format":"ssas.usb","version":1,"school_name","exported_at","studio_version","boards":[...],"app"}
├── ssas-board.apk         the board app (optional)
├── models/
│   ├── det_10g.onnx  w600k_r50.onnx  [rtmo-s.onnx]
│   └── models.json        {"detector": {"file","sha256"}, "embedder": {...}, "pose": {...}}
├── screens/
│   └── 9A1/
│       ├── board.json
│       └── class-9A1.json  (a lab folder has one class file per class that visits it)
└── server/boards.json
```

The board copies everything it needs into its own storage and checks every SHA-256 before
using it, so the USB can be removed afterwards.

**Keep the USB safe:** `board.json` contains each board's server token in plain text.
Re-exporting a board keeps its token. If a USB stick is lost, use Studio → Export → "New server keys…", then upload the
new `boards.json` to the server and import again on those boards.

## 4. `ssas.board` v1

```json
{
  "format": "ssas.board",
  "version": 1,
  "board_code": "9A1",
  "kind": "class",
  "name": "9A1",
  "school_name": "...",
  "exported_at": "2026-10-26T10:15:00",
  "studio_version": "0.1.0",
  "school_days": [7, 1, 2, 3, 4],
  "bell": [{"period": 1, "start": "07:30", "end": "08:15", "kind": "class"}],
  "slots": [{"day": 1, "period": 1, "class_code": "9A1"}],
  "classes": [{"class_code": "9A1", "file": "class-9A1.json", "sha256": "...", "students": 25}],
  "capture": {"offset_min": 3, "window_min": 5, "shots_s": [0, 10, 25, 45, 75, 120, 180, 240], "min_valid_frames": 3},
  "models": {"detector": {"file": "det_10g.onnx", "sha256": "..."}},
  "server": {"url": "https://192.168.1.10", "cert_sha256": "...", "token": "..."},
  "admin_pin_sha256": "sha256('<board_code>:<pin>')",
  "sound": true
}
```

- Days: ISO numbers, Monday = 1 … Sunday = 7.
- `kind`: `class` (a classroom board) or `lab`.
- `slots`: the only periods this board records. Each slot names the class expected in the room.
- The board uses its own clock. A capture opens at `start + offset_min`. It stops after `window_min`,
  or earlier once every student is recognised.
- `server.url` may be empty. Results are then only kept on the board and exported to USB from the
  hidden admin menu.
- `cert_sha256`: SHA-256 of the server certificate (DER). The board trusts only that certificate.

## 5. `ssas.result` v1

```json
{
  "format": "ssas.result",
  "version": 1,
  "board_code": "9A1",
  "class_code": "9A1",
  "date": "2026-10-26",
  "period": 3,
  "lesson_start": "09:10",
  "captured_at": "2026-10-26T09:13:02",
  "frames": 8,
  "valid_frames": 8,
  "unknown_max": 0,
  "suspicious_max": 0,
  "camera_problem": null,
  "model_created_at": "2026-10-25T18:40:11",
  "app_version": "0.1.0",
  "students": [{"id": "9A1-001", "name": "Ahmed Ali", "status": "present", "score": 0.62}]
}
```

`status` is one of:

| Status | Meaning |
|---|---|
| `present` | recognised in 2 frames, or in 1 frame with a strong match |
| `absent` | not seen, **and** every face/body in the room was explained, **and** at least `min_valid_frames` good frames |
| `needs_review` | not recognised but cannot be called absent (unknown faces, bodies without a face, too few good frames) |
| `no_data` | the camera gave no usable picture (busy, dark, missing); the reason is in `camera_problem` |

`unknown_max` is the most unrecognised faces in one frame. `suspicious_max` is the most bodies
without a recognised face in one frame.

## 6. Server API

All board calls use `Authorization: Bearer <token>`. The server stores only `sha256(token)`.

| Call | Body | Answer |
|---|---|---|
| `POST /api/v1/results` | `ssas.result` | `200` stored · `409` already stored (the board counts this as sent) · `401` unknown token · `403` result for another board, or for a class this board does not record · `400` bad payload |
| `POST /api/v1/heartbeat` | `{"board_code","app_version","armed","last_capture","last_error","next_capture","pending"}` | `200 {"ok":true,"server_time"}` |
| `GET /api/v1/health` | — | `200 {"ok":true,"version"}` |

Only one result is kept per (class, date, period). The first one wins.

## 7. `ssas.server-boards` v1

Uploaded on the server's **Boards** page (developer account only).

```json
{
  "format": "ssas.server-boards",
  "version": 1,
  "school_name": "...",
  "boards": [{
    "board_code": "LAB1", "kind": "lab", "name": "Physics lab",
    "classes": ["9A1", "10G2"],
    "token_sha256": "...",
    "students": {"9A1": [{"id": "9A1-001", "name": "Ahmed Ali"}]}
  }]
}
```
