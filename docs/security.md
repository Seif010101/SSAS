# SSAS security

This page lists what SSAS protects, against whom, how, and how it was tested. A plain-language Arabic
version is in [`HOW-IT-WORKS.md`](HOW-IT-WORKS.md) §7.

## What we protect

| Asset | Where | Why it matters |
|---|---|---|
| People's photos | admin laptop only | biometric data; the most sensitive thing in the system |
| Group models (512 numbers per person + names) | laptop, USB stick, screens | lets a screen recognise its group |
| Screen tokens | `org.json` (laptop), `board.json` (USB, screen) | whoever holds one can post results for that screen |
| Attendance results | screens, server | personal data; must not be faked |
| Admin accounts | server | full view of attendance; developers can register screens |
| Android signing key | GitHub Secrets + the owner's safe storage | whoever has it can push an update to every screen |

## Who we defend against

- **Someone in the room:** holds up a photo or a phone, or tries to answer for an absent friend.
- **Someone at the screen:** tries the hidden admin menu, or plugs in a crafted USB stick.
- **Someone on the network or the internet:** probes the server, guesses passwords, sends forged results,
  injects scripts or Excel formulas, or tries cross-site attacks on an admin.
- **Someone who stole a USB stick or a screen token.**
- **Someone who wants to ship a fake screen app update.**

## Controls

**Privacy by design**
- Photos never leave the laptop; the USB, the screens and the server never receive one.
- Recognition runs on the screen. The camera opens only for minutes at the start of each session.
- The server receives only ids, names and statuses.

**Screen app (`board-app/`)**
- **USB stick:** every file name from the stick must match `^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$` without `..`
  (`SafeName`). Every file's SHA-256 is checked, and the old configuration is kept unless everything
  arrived intact.
- **Admin menu:** the PIN has 6 to 12 digits and no default. 5 wrong tries lock the menu for 5 minutes,
  and the lock survives a restart.
- **Sending results:**
  - only to `https://`, and only with a certificate the screen trusts (the pinned fingerprint, or the
    normal public CAs);
  - broken results are set aside (`rejected/`) and never resent.
- **Updates:** the APK is signed with a private key that is not in the repository. Android refuses an
  update signed with any other key, and CI refuses to publish a test-signed APK.

**Server (`server/`)**
- **Screen API:**
  - tokens are stored only as SHA-256;
  - a screen may post only as itself, only for its groups, and only for registered people;
  - names are taken from the registered list, never from the screen;
  - every field is type- and length-checked;
  - a date must be a real date and not in the future (more than one day ahead), and it is stored in one
    spelling only.
- **Admin sign-in:**
  - Argon2id password plus a TOTP code; a used code cannot be replayed;
  - 5 failures lock the account for 15 minutes;
  - at most 10 attempts per address in 10 minutes (429);
  - the session lives on the server (cookie `HttpOnly`, `SameSite=Strict`, `Secure`), with idle and total
    time-outs;
  - logout ends the session on the server.
- **Admin pages:**
  - parameterised SQL everywhere, and Jinja autoescape;
  - CSRF token on state-changing forms;
  - view-only supervisor role;
  - CSV cells cannot become Excel formulas (including full-width `＝`).
- **Every answer:**
  - CSP (`script-src 'none'`, `frame-ancestors 'none'`), `X-Frame-Options: DENY`, `nosniff`,
    `no-referrer`, `no-store` on pages, and HSTS over HTTPS;
  - request bodies are limited to 256 KB (4 MB for `boards.json`).
- **On the internet:**
  - `SSAS_ADMIN_ALLOW` limits the admin pages to listed addresses; the screens are not affected.
  - Behind Caddy, the client address is trusted only from Caddy's private Docker network (`SSAS_TRUSTED_PROXIES`).
  - Caddy gets and renews a Let's Encrypt certificate by itself. The app container has no published port.

**Studio (`studio/`)**
- Export is blocked until a valid PIN is set, and the server address must be `https://`.
- Every model file (InsightFace and RTMO) is checked against a pinned SHA-256 before use. CI checks the same hashes.
- `.npz` caches are loaded without pickle.

## Testing

**Attack script.** [`server/tools/pentest.py`](../server/tools/pentest.py) starts a real server with a throw-away
database, seeds two screens and two admin accounts, and attacks it over HTTP. It runs in CI on every push.

| Check | Severity | 0.1.x | 0.2.0 |
|---|---|---|---|
| admin pages need a sign-in (4 pages) | high | ✅ | ✅ |
| unknown screen token refused | high | ✅ | ✅ |
| a screen cannot post for another group (IDOR) | high | ✅ | ✅ |
| a screen cannot post as another screen | high | ✅ | ✅ |
| SQL injection in the sign-in form | high | ✅ | ✅ |
| results for people not registered on the screen refused | medium | ❌ 200 | ✅ 403 |
| a screen cannot rename a registered person | medium | — | ✅ |
| deeply nested JSON refused without a server error | medium | — | ✅ |
| session cookie `HttpOnly` + `SameSite=Strict` | medium | ✅ | ✅ |
| names from a screen shown escaped (stored XSS) | high | ✅ | ✅ |
| names always come from the registered list | medium | — | ✅ |
| heartbeat text shown escaped | high | ✅ | ✅ |
| CSV export cannot inject Excel formulas | medium | ❌ | ✅ |
| boards upload without the CSRF token refused | high | ✅ | ✅ |
| view-only supervisor cannot upload screens | high | ✅ | ✅ |
| logout ends the session on the server | medium | ✅ | ✅ |
| a used 6-digit code cannot be used again | high | ✅ | ✅ |
| many sign-in attempts from one address slowed down | medium | ❌ | ✅ 429 |
| security headers sent | medium | ❌ none | ✅ |
| oversized request refused | medium | ❌ 200 | ✅ 413 |
| oversized request without a length refused | medium | — | ✅ 413 |
| a huge password refused before hashing | low | — | ✅ |
| no path traversal through `/static` | high | ✅ | ✅ |
| **Total** | | **17 / 22** | **27 / 27** |

**Unit tests.**
- **Server:** v1 and future dates, two spellings of one date, unknown people, duplicates, the heartbeat
  field filter, the sign-in limit, the headers, both kinds of body limit, the allow-list, the CSV guard,
  the upgrade from 0.1.
- **Screen app:** unsafe USB names, a damaged file keeping the old configuration, v1 files refused, the
  CSV guard.
- **Studio:** PIN and https rules, the 0.1 data folder upgrade.

**End to end (manual, 0.2.0).**
- **Studio → screen → server:**
  - Studio trained a real group and exported it;
  - the screen code installed the package, recognised the faces and uploaded;
  - the server stored the result with the registered names.
- **The screen's uploader against a live server:**
  - pinned certificate accepted, wrong fingerprint refused;
  - `http://` refused;
  - broken results set aside, unregistered results kept for retry, duplicates counted as sent.
- **The VPS stack in Docker:**
  - HTTPS through Caddy, and http redirected to https;
  - a faked `X-Forwarded-For` does not get round the sign-in limit or the allow-list;
  - backups work.

**Code review.**
- The 0.2 changes were reviewed with the `security-review` checklist: no high- or medium-confidence
  findings.
- Its three hardening notes were applied:
  - trust forwarded addresses only from Caddy's network;
  - one spelling per date, and no future dates;
  - the full-width CSV guard.

**Dependencies.** `pip-audit` on the server and Studio pins: no known vulnerabilities (November 2026).

## Known limits

- **A stolen USB stick is a stolen key ring.**
  - `board.json` holds the screens' tokens.
  - The admin PIN is stored as a SHA-256, so it can be brute-forced offline from the stick.
  - Keep the stick locked away.
  - If it is lost: Studio → Export → **New server keys…**, upload the new `boards.json`, import again on
    those screens, and choose a new PIN.
- **A stolen token still allows fake results** for that screen's groups and registered people, until the
  key is replaced.
- **The local-network server uses its own certificate:** browsers warn about it. The screens trust only its
  pinned fingerprint.
- **The InsightFace models are for non-commercial use.**
- **Face recognition is not perfect.** Uncertain cases become `needs_review`, never `absent`, so a person
  decides.

## Reporting a problem

Please do not open a public issue. Contact the repository owner privately through their GitHub profile.
