# SSAS data formats (version 2)

Every file SSAS writes is plain JSON (UTF-8) with a `format` name and an integer `version`.
A reader must reject a file whose `format` is wrong or whose `version` it does not know, and must
ignore keys it does not know. Bump `version` only for changes an old reader would misread; adding an
optional key does not need a bump.

Version 2 (SSAS 0.2) replaced the school words of version 1: class → **group**, student → **person**,
period/lesson → **session**, bell → **sessions**, lab → **shared room**. Version 1 files are refused
with "export again"; Studio converts a 0.1 data folder once by itself, and the server converts a 0.1
database once by itself.

| Format | Written by | Read by | Where |
|---|---|---|---|
| `ssas.org` v2 | Studio | Studio | `<data folder>/org.json` |
| `ssas.group` v2 | Studio | Studio | `<data folder>/groups/<code>/group.json` |
| `ssas.group-model` v2 | Studio | Screen app | `groups/<code>/model/group-model.json`, copied to the USB as `group-<code>.json` |
| `ssas.board` v2 | Studio | Screen app | `SSAS-USB/screens/<screen>/board.json` |
| `ssas.usb` v2 | Studio | Screen app | `SSAS-USB/ssas-usb.json` |
| `ssas.server-boards` v2 | Studio | Server | `SSAS-USB/server/boards.json` |
| `ssas.result` v2 | Screen app | Server | sent to `POST /api/v1/results`, also kept on the screen |

## 1. Laptop data folder (Studio)

```
Documents/SSAS-Data/
├── org.json                    name, working days, session times, shared rooms, settings, screen tokens
├── backup-0.1/                 only after an upgrade from Studio 0.1: copies of the old JSON files
└── groups/
    └── 9A1/
        ├── group.json          name, room, people, timetable
        ├── Ahmed Ali/          one folder per person: the photos (never leave the laptop)
        └── model/
            ├── group-model.json
            ├── report.json     training report shown in the Train tab
            └── embeddings.npz  cache; also used as "strangers" when training the other groups
```

`org.json`:

```json
{
  "format": "ssas.org", "version": 2,
  "name": "My organisation",
  "days": [1, 2, 3, 4, 5],
  "sessions": [{"number": 1, "start": "07:30", "end": "08:15", "kind": "session"},
               {"number": 0, "start": "09:55", "end": "10:15", "kind": "break"}],
  "shared_rooms": [{"code": "LAB1", "name": "Science lab"}],
  "settings": {"board_admin_pin": "493817", "server_url": "https://...", "server_cert_sha256": "", "...": "..."},
  "board_tokens": {"9A1": "<secret, one per screen>"}
}
```

- Days are ISO numbers: Monday = 1 … Sunday = 7.
- `kind` is `session` (attendance is taken), `break` or `other` (never counted).
  Attendance sessions are numbered 1, 2, 3… in time order; the other rows have number 0.

`group.json` → `people: [{"id": "9A1-001", "name": "...", "folder": "..."}]`. Ids are `<group>-NNN`
and are never reused, so a result always points to one person. `timetable[day][session]` is `"here"`
(the screen in the group's own room takes attendance), `"skip"` (the group is somewhere without a
screen) or a shared-room code (that room's screen takes attendance). A missing entry means `"here"`.

Codes (groups, shared rooms, screens) match `^[A-Za-z0-9][A-Za-z0-9_-]{0,15}$`; they are folder names
on the laptop, on the USB and on the screen.

## 2. `ssas.group-model` v2

One trained model per group. It holds no photos and no face pictures — only one row of 512 numbers
per person (the classifier the screen uses) and the thresholds.

```json
{
  "format": "ssas.group-model",
  "version": 2,
  "group_code": "9A1",
  "created_at": "2026-11-02T10:15:00+04:00",
  "studio_version": "0.2.0",
  "method": "head",
  "models": {"detector": {"file": "det_10g.onnx", "sha256": "..."},
             "embedder": {"file": "w600k_r50.onnx", "sha256": "..."}},
  "people": [{"id": "9A1-001", "name": "Ahmed Ali"}],
  "weights": {"dtype": "float32", "shape": [25, 512], "data": "<base64, little-endian>"},
  "thresholds": {"accept": 0.31, "strong": 0.45, "margin": 0.05},
  "metrics": {"accuracy": 0.995, "wrong_person_rate": 0.0, "stranger_accept_rate": 0.0008, "passed": true}
}
```

**Matching one face.** `e` = L2-normalised ArcFace embedding of the aligned 112×112 face.
`scores = W · e`. Let `top`, `second` be the two best scores.

- recognised as `people[argmax]` when `top ≥ accept` and `top − second ≥ margin`;
- the match is *strong* when also `top ≥ strong`;
- otherwise the face is *unknown*.

`method` is `head` (trained cosine classifier) or `prototype` (mean embedding per person);
the screen treats both the same way.

## 3. USB folder

```
SSAS-USB/
├── ssas-usb.json          {"format":"ssas.usb","version":2,"org_name","exported_at","studio_version","boards":[...],"app"}
├── ssas-board.apk         the screen app (optional)
├── models/
│   ├── det_10g.onnx  w600k_r50.onnx  [rtmo-s.onnx]
│   └── models.json        {"detector": {"file","sha256"}, "embedder": {...}, "pose": {...}}
├── screens/
│   └── 9A1/
│       ├── board.json
│       └── group-9A1.json  (a shared room's folder has one file per group that visits it)
└── server/boards.json
```

The screen copies everything it needs into its own storage and checks every SHA-256 before using
it, so the USB can be removed afterwards. Every file name it reads from the USB must match
`^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$` without `..`; anything else is refused.

**Keep the USB safe:** `board.json` contains each screen's server token in plain text.
Re-exporting a screen keeps its token. If a USB stick is lost, use Studio → Export → "New server
keys…", then upload the new `boards.json` to the server and import again on those screens.

## 4. `ssas.board` v2

```json
{
  "format": "ssas.board",
  "version": 2,
  "board_code": "9A1",
  "kind": "group",
  "name": "9A1",
  "org_name": "...",
  "exported_at": "2026-11-02T10:15:00+04:00",
  "studio_version": "0.2.0",
  "days": [1, 2, 3, 4, 5],
  "sessions": [{"number": 1, "start": "07:30", "end": "08:15", "kind": "session"}],
  "slots": [{"day": 1, "session": 1, "group_code": "9A1"}],
  "groups": [{"group_code": "9A1", "file": "group-9A1.json", "sha256": "...", "people": 25}],
  "capture": {"offset_min": 3, "window_min": 5, "shots_s": [0, 10, 25, 45, 75, 120, 180, 240], "min_valid_frames": 3},
  "models": {"detector": {"file": "det_10g.onnx", "sha256": "..."}},
  "server": {"url": "https://attendance.example.com", "cert_sha256": "", "token": "..."},
  "admin_pin_sha256": "sha256('<board_code>:<pin>')",
  "sound": true
}
```

- `kind`: `group` (the room of one group) or `shared` (a room several groups use; `name` is the room's name).
- `slots`: the only sessions this screen records. Each slot names the group expected in the room.
- The screen uses its own clock. A capture opens at `start + offset_min`. It stops after `window_min`,
  or earlier once everyone is recognised.
- `server.url` may be empty: results are then only kept on the screen and exported to USB from the
  hidden admin menu. When set, it must start with `https://`; the screen never sends over plain HTTP.
- `cert_sha256`: SHA-256 of the server's certificate (DER). When set, the screen trusts only that
  certificate (a server on the local network with its own certificate). When empty, the screen trusts
  the normal public certificate authorities (a server with a real domain, e.g. a VPS with Let's Encrypt).
- The admin PIN has 6 to 12 digits; Studio refuses to export without one. The screen locks the admin
  menu for 5 minutes after 5 wrong tries.

## 5. `ssas.result` v2

```json
{
  "format": "ssas.result",
  "version": 2,
  "board_code": "9A1",
  "group_code": "9A1",
  "date": "2026-11-02",
  "session": 3,
  "session_start": "2026-11-02T09:10",
  "captured_at": "2026-11-02T09:13:02",
  "frames": 8,
  "valid_frames": 8,
  "unknown_max": 0,
  "suspicious_max": 0,
  "camera_problem": null,
  "model_created_at": "2026-11-01T18:40:11+04:00",
  "app_version": "0.2.0",
  "people": [{"id": "9A1-001", "name": "Ahmed Ali", "status": "present", "score": 0.62}]
}
```

`status` is one of:

| Status | Meaning |
|---|---|
| `present` | recognised in 2 frames, or in 1 frame with a strong match |
| `absent` | not seen, **and** every face/body in the room was explained, **and** at least `min_valid_frames` good frames |
| `needs_review` | not recognised but cannot be called absent (unknown faces, bodies without a face, too few good frames) |
| `no_data` | the camera gave no usable picture (busy, dark, missing); the reason is in `camera_problem` |

`unknown_max` is the most unrecognised faces in one frame. `suspicious_max` is the most faces without
a body under them (a photo or a phone held up) in one frame.

## 6. Server API

All screen calls use `Authorization: Bearer <token>`. The server stores only `sha256(token)`.
Requests are limited to 256 KB.

| Call | Body | Answer |
|---|---|---|
| `POST /api/v1/results` | `ssas.result` v2 | `200` stored · `409` already stored (the screen counts this as sent) · `400` broken (wrong format/version, bad field): the screen sets it aside and never resends it · `401` unknown token · `403` for another screen, a group this screen does not record, or a person not registered for that group: the screen keeps it and tries again later |
| `POST /api/v1/heartbeat` | `{"board_code","app_version","armed","last_capture","last_error","next_capture","pending","time"}` (other keys are dropped) | `200 {"ok":true,"server_time"}` |
| `GET /api/v1/health` | — | `200 {"ok":true,"version"}` |

Only one result is kept per (group, date, session); the first one wins. The server stores the names
from its own registered list (from `boards.json`), never the names a screen sends.

## 7. `ssas.server-boards` v2

Uploaded on the server's **Boards** page (developer account only, at most 4 MB). It holds no photos
and no face data.

```json
{
  "format": "ssas.server-boards",
  "version": 2,
  "org_name": "...",
  "boards": [{
    "board_code": "LAB1", "kind": "shared", "name": "Physics lab",
    "groups": ["9A1", "10G2"],
    "token_sha256": "...",
    "people": {"9A1": [{"id": "9A1-001", "name": "Ahmed Ali"}]}
  }]
}
```

Every code, id, name and hash is checked on upload; a file that fails any check is not imported at all.
