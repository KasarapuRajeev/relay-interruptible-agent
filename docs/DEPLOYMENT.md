# Relay Deployment

Relay uses a split deployment so the public frontend can use Vercel's Git previews
while the interruption runtime remains in one stateful Python process.

```text
Browser
  |
  v
Vercel static dashboard
  |  /api/* proxy
  v
Render Python service
  |
  +-- Gemini provider
  +-- Open-Meteo weather
  +-- MediaWiki research
```

## 1. Deploy the stateful backend on Render

1. In Render, create a Blueprint from
   `KasarapuRajeev/relay-interruptible-agent`.
2. Render reads `render.yaml` and creates `relay-interruptible-agent-api`.
3. Enter `GEMINI_API_KEY` in the Render dashboard when prompted. Never place its
   value in GitHub, `render.yaml`, screenshots, or documentation.
4. Wait until `/api/status` passes the configured health check.
5. Copy the generated service URL.

Production backend: [relay-interruptible-agent-api.onrender.com](https://relay-interruptible-agent-api.onrender.com)

Verified on September 30, 2026: `GET /api/status` returned HTTP 200 with the
Gemini provider and build `2026.10.01.1`.

The process binds to Render's `PORT` on `0.0.0.0`. The local workflow remains
unchanged because it defaults to `127.0.0.1:8000`.

## 2. Connect the Vercel frontend

The repository now includes the following production rewrite in `vercel.json`:

```json
{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "outputDirectory": "web",
  "rewrites": [
    {
      "source": "/api/:path*",
      "destination": "https://relay-interruptible-agent-api.onrender.com/api/:path*"
    }
  ]
}
```

Import the same GitHub repository in Vercel. Keep the project root as the
repository root and deploy it as a static site with `web` as the output directory.
The browser continues using relative `/api/...` URLs, so no Gemini key is exposed in
frontend JavaScript.

Production frontend: [relay-interruptible-agent.vercel.app](https://relay-interruptible-agent.vercel.app)

Verified on September 30, 2026: the stable Vercel URL loaded the dashboard, reached
the Render backend through the rewrite, reported Gemini, listed five capabilities,
and completed the calculator smoke test with grounded evidence.

## 3. Edit the UI after deployment

- Change `web/index.html`, `web/style.css`, or `web/app.js`.
- Push a feature branch to receive a Vercel preview URL.
- Merge into `main` only after testing the preview.
- Vercel then updates the production deployment automatically.
- Backend changes in `relay/` redeploy automatically on Render from `main`.

## 4. Production checks

1. Confirm the Vercel URL loads the Relay dashboard.
2. Confirm the provider badge reports Gemini and build `2026.10.01.1`.
3. Run the Delhi-to-Jaipur interruption scenario.
4. Confirm the old call is cancelled and no late Delhi result enters Jaipur.
5. Test weather, calculation, and cited research.
6. Do not create `v1.0.0-submission` until the video link and presentation artifact
   are in the repository.
