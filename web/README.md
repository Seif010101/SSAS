# SSAS web app

Teacher page (UI preview). The admin dashboard will be added to the same app later.

> **Preview only:** sign-in is not connected, nothing is sent to a server, and the
> students shown come from `src/demo/fixtures.ts` (placeholder names). Status changes
> stay in the browser until the page is reloaded.

## Run it

```bash
cd web
npm install
npm run dev        # http://localhost:5173
npm run build      # type-check + production build into dist/
```

Pages: `#/login`, `#/class` (the class being taught now), `#/no-class` (between periods).

## Where to change things

| What | File |
|---|---|
| Status names, colours, descriptions, which ones a teacher can pick | `src/config/statuses.ts` |
| App name, how a class is written ("Grade 9 · Advanced · Section 4") | `src/config/school.ts` |
| Colours, spacing, fonts for the whole app | `src/styles/tokens.css` |
| Teacher screens | `src/features/teacher/` |
| Shared pieces (status dot, bottom sheet, icons) | `src/components/` |
| Preview data (remove when the server API is connected) | `src/demo/fixtures.ts` |
