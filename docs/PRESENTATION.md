# SSAS — 3-minute hackathon presentation

Two parts:
1. **The prompt for Claude Design.** Copy everything inside the box into Claude Design and it builds the 7 slides.
2. **What to say.** A 3-minute script in English, slide by slide, plus the demo steps and answers for the judges.

Every number here is from the project itself (docs/HOW-IT-WORKS.md and docs/security.md). Check that Claude Design did
not change any of them.

---

## 1. The prompt for Claude Design

```text
Create a 7-slide pitch deck (16:9) for a 3-minute hackathon presentation. Put the speaker note I give for each
slide in that slide's notes.

PROJECT
SSAS — Seif's Smart Attendance System (website: ssas.ae).
One line: the smart screen that is already in the room takes attendance by itself in the first minutes of each
session, and no photo ever leaves the admin's laptop.

STYLE
- Clean, modern and confident. Light background (white or #f8fafc), dark text (#0f172a).
- Brand colour: teal #0f766e for accents, light teal #ccfbf1 for highlights. Use green #16a34a only for
  "present", amber #f59e0b only for "needs review", red #dc2626 only for "absent".
- Logo: a white check mark inside a teal rounded square, next to the word "SSAS".
- Font: Inter (or a similar clean sans-serif). Big headlines, very little text, one idea per slide, big numbers.
- Simple line icons and diagrams instead of paragraphs. No photos of real people's faces: use simple
  silhouettes for people.

SLIDES — use this text exactly. Do not invent any number, feature or claim.

Slide 1 — Title
- "SSAS"
- "Seif's Smart Attendance System"
- Tagline: "Attendance that takes itself — privately."
- "ssas.ae"
Speaker note: Hi, I'm Seif. This is SSAS: attendance that takes itself, privately.

Slide 2 — The problem
- Headline: "Roll call steals session time"
- Three points with icons:
  1. "Calling names takes minutes, every session" (small grey example under it:
     "e.g. 5 min × 6 sessions = 30 min a day, per group")
  2. "Mistakes, and friends answering for each other"
  3. "Fingerprint queues, shared cards, forwarded QR codes"
Speaker note: Every session starts with calling names. It wastes time and it is easy to cheat.

Slide 3 — The idea
- Headline: "The smart screen becomes an AI agent"
- A horizontal timeline for one session:
  "0:00 Session starts" → "0:03 Camera opens" → "Recognises the group on the screen itself" →
  "Decides: present · absent · needs review" → "Sends text only" → "Camera off (5 min at most)"
- Small line under it: "No new hardware. Works without internet."
Speaker note: The screen sees, decides and acts by itself, then turns the camera off.

Slide 4 — How it works
- Headline: "Three programs, one simple flow"
- Flow diagram with three boxes and a USB icon:
  "Admin App (Windows laptop): photos · training · timetable" → "USB stick" →
  "Smart Screen App (Android screen): recognition on the device" → "Server (optional): text results,
  Excel export — a local PC or a VPS"
- Under it, the AI pipeline as 5 small steps:
  "Find the face (SCRFD)" → "Line it up (5 points)" → "512-number face fingerprint (ArcFace)" →
  "One small model per group" → "Decision"
- Four number badges:
  "40 photos in ~20 s per person" · "10 camera-like copies of each photo" ·
  "Model must pass ≥ 98% in testing" · "Strangers accepted ≤ 0.1% in testing"
Speaker note: Photograph each person once, train a small model per group, carry it to the screen on a USB stick.

Slide 5 — Private and secure by design
- Headline: "Privacy first. Tested like an attacker."
- Left column "Privacy":
  "Photos never leave the admin's laptop" · "Recognition happens on the screen" ·
  "The server only gets names and statuses" · "The camera runs minutes, not all day"
- Right column "Security", with one big number: "27 / 27 attacks blocked" and under it
  "automatic attack test on every change", then: "HTTPS + certificate pinning" ·
  "Admin sign-in: password + 6-digit code" · "App signed with a private key"
- A thin row at the bottom "Anti-cheat": "A face must sit on a body — photos and phones are ignored" ·
  "Head turn + blink when photos are taken"
Speaker note: No pictures leave the laptop, and we attacked our own server 27 ways; every attack was blocked.

Slide 6 — Live demo
- Very big: "Live demo"
- Small: "This laptop plays the smart screen — Admin App → ▶ Live demo"
- Three status chips: "Present" (green) · "Needs review" (amber) · "Absent" (red)
- Small line: "When it is not sure, it says “needs review” — never a wrong absent."
Speaker note: Switch to the Admin App and show the Live demo tab.

Slide 7 — For everyone
- Headline: "Built for any organisation"
- A row of icons with labels: "Schools" · "Companies" · "Factories" · "Training centres" · "Gyms"
- Three badges: "No new hardware" · "Works offline" · "Photos stay private"
- Bottom: "Thank you — ssas.ae" and "Questions?"
Speaker note: Any place with groups and schedules can use it today at ssas.ae. Thank you.
```

**After it builds the slides, check:**
- Every number matches the prompt: 3 min, 5 min, 40 photos, ~20 s, 10 copies, ≥ 98%, ≤ 0.1%, 27/27.
- No real person's face anywhere.
- Slide 6 is easy to read from far away.

---

## 2. What to say (3 minutes, English)

Speak slowly. Short sentences are fine. About 140 words a minute.

**Slide 1 — Title (0:00–0:10)**
> Hi, I'm Seif. This is SSAS — Seif's Smart Attendance System. Attendance that takes itself, privately.

**Slide 2 — The problem (0:10–0:30)**
> Every session starts the same way: someone calls names. That takes minutes. Five minutes, six times a day, is
> half an hour lost for every group, every day. And it is easy to cheat: a friend answers for you, cards get
> shared, QR codes get forwarded.

**Slide 3 — The idea (0:30–0:55)**
> Most rooms already have a smart screen with a camera. SSAS turns it into an AI agent. Three minutes after the
> session starts, it opens the camera for a few minutes. It recognises the people of that group, on the screen
> itself. It decides who is present, sends a short text result, and turns the camera off. No new hardware, and
> it works without internet.

**Slide 4 — How it works (0:55–1:25)**
> There are three programs. The Admin App on a laptop photographs each person in about twenty seconds. They turn
> their head and blink, so a photo cannot fool it. Then it trains one small model for each group. Every photo
> becomes ten camera-like copies, and every model is tested honestly with cross-validation: a model only passes
> if it is at least ninety-eight percent correct, and strangers are accepted less than zero point one percent of
> the time. A USB stick carries the model to the screen. The server is optional.

**Slide 5 — Privacy and security (1:25–1:50)**
> Privacy is built in. Photos never leave the admin's laptop. The screen only sends names and statuses — no
> images. And we attacked our own server twenty-seven different ways: SQL injection, cross-site scripting, fake
> screens, password guessing. All twenty-seven were blocked, and that test runs automatically on every change.

**Slide 6 — Live demo (1:50–2:35)** *(switch to the Admin App)*
> Let me show you. This laptop is playing the smart screen. *[the camera is already on]* It recognises me —
> there's my name. *[ask a judge to stand next to you]* You are not in this group, so you are “unknown”. Watch
> what happens. *[press Take attendance]* About fifteen seconds… Here is the result. People it is not sure about
> are “needs review”, not “absent”, so nobody is marked absent by mistake. And this box is everything that goes
> to the server: just text.

**Slide 7 — For everyone (2:35–3:00)** *(back to the slides)*
> SSAS works for any organisation with groups and schedules: schools, companies, factories, training centres. No
> new hardware, it works offline, and photos stay private. It is live today at ssas.ae. Thank you — I'm happy to
> take your questions.

### Before you go on stage
- [ ] Admin App 0.2.1 is installed and the face models are downloaded.
- [ ] A **trained group with you in it** is ready. Your group 9A3 (seif + eyad) works.
- [ ] Before you start talking:
  - open **▶ Live demo**;
  - choose the group;
  - press **Start camera**, and leave it running behind the slides.
- [ ] Good light on your face. The laptop is charged.

### If the camera fails during the demo
1. Stay calm and stay on slide 6.
2. Say: "Here's what it does: present, needs review, absent — and only this text goes to the server."
3. If you have time, show the screenshots in docs/studio-guide.md, or the Train tab with its accuracy report.

### Short answers for the judges
| Question | Answer |
|---|---|
| Where is the AI? | Three neural networks: face finder, face fingerprint, and body pose. Plus a model we train for each group, with limits learned from the data. And the agent decides and acts by itself. |
| What about privacy? | Photos never leave the laptop. The screen sends only names and statuses. The camera runs a few minutes per session. The organisation collects consent first. |
| How accurate is it? | Every group model is tested with cross-validation. It must reach at least 98%, and strangers are accepted at most 0.1%. When it is unsure, it says "needs review". |
| Can someone hold up a photo or a phone? | No. A face must sit on a real body. And taking someone's photos needs a head turn and a blink. |
| What if the internet is down? | Recognition runs on the screen. Results wait and are sent later, or collected with a USB stick. |
| How much does it cost? | It uses the screens already in the room. The software is free. The server is optional. |
| What did you build yourselves? | The whole system: three apps, the training, the decision rules, the anti-cheat, the security and the deployment. The base face models are open source. Their licence is non-commercial, so we would license commercial models before selling. |
