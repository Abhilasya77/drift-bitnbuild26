# Tawashir — frontend (vanilla HTML/CSS/JS)

No build step, no framework. Open it with a local server (not `file://`, since
`fetch`/module-style asset loading needs `http://`) and edit directly.

## Run it

**Option A — VS Code Live Server (recommended)**
1. Install the "Live Server" extension (by Ritwick Dey) from the Extensions tab.
2. Right-click `index.html` → "Open with Live Server".
3. It opens at `http://127.0.0.1:5500` and reloads on every save.

**Option B — any static server**
```
npx serve .
```
or
```
python3 -m http.server 5500
```

## Pages

- `index.html` — landing page (hero + stats fit one viewport, with How It
  Works / For Organizations sections below for the nav links to scroll to)
- `login.html`, `signup.html` — auth screens
- `dashboard.html` — authenticated app shell

## Demo login (for judges)

```
Email:    demo@tawashir.io
Password: Tawashir@2026
```
There's a "Fill demo credentials" button on the login screen so judges don't
have to type it. Sign up also works in demo mode — any email/password creates
a local session and drops you straight into the dashboard.

This is `sessionStorage`-based, client-side only — good enough for a hackathon
demo, not real auth. Swap `auth.js` for real calls to P2/P4's API once it's ready.

## Adding a real background video (optional)

The moving background is currently a lightweight animated canvas (no external
asset needed). If you get a licensed/owned looping clip, drop it at:

```
assets/bg-loop.mp4
```

It'll fade in over the canvas automatically — no code changes needed. Keep it
short, muted, and subtle (the CSS holds it at 50% opacity behind the UI).

## Structure

```
index.html
login.html
signup.html
dashboard.html
styles.css      — shared design tokens, layout, animations
main.js         — backdrop, mobile menu, scroll reveal, stats count-up
auth.js         — demo login/signup/dashboard-guard logic
assets/         — drop bg-loop.mp4 here if you have one
```
