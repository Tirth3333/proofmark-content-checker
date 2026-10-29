# Deployment

Status as of 2026-10-29: the project is **prepared** for its own GitHub repository and deployment. No repository has been created and nothing has been deployed from this environment; there is no remote URL yet. Run the steps below and record the real URLs at the bottom of this file.

## 1. Create the GitHub repository

The project folder is already a git repository with an initial commit on `main`.

```bash
cd content-checker
# Create an empty repo on GitHub first (no README/.gitignore), e.g. named "proofmark-content-checker", then:
git remote add origin https://github.com/<your-username>/<repo-name>.git
git push -u origin main
```

Or with the GitHub CLI:

```bash
gh repo create <repo-name> --public --source . --remote origin --push
```

Before pushing, confirm no secrets are tracked: `git ls-files | grep -i env` should list only `.env.example`.

## 2. Option A: one service with Docker (recommended)

The root `Dockerfile` builds the React app and serves it from FastAPI on one port.

```bash
docker build -t proofmark .
docker run --rm -p 8000:8000 --env-file backend/.env proofmark   # --env-file optional
# open http://localhost:8000 ; health check: http://localhost:8000/api/health
```

> The Dockerfile has not been built in the development environment (no Docker daemon was available). Build it locally once before relying on it.

### Render (free tier, uses `render.yaml`)

1. Push the repo to GitHub.
2. In Render: **New → Blueprint**, pick the repo. Render reads `render.yaml` and creates a Docker web service with health check `/api/health`.
3. Optional: set `LLM_PROVIDER`, `LLM_API_KEY`, `LLM_MODEL`, `LLM_BASE_URL`, `SEARCH_PROVIDER`, `SEARCH_API_KEY` in the service's Environment tab. Leave `LLM_PROVIDER=none` for rule-based mode.
4. Deploy, then open the `.onrender.com` URL and run the demo.

Other Docker hosts (Railway, Fly.io, Google Cloud Run, Azure Container Apps) work the same way: deploy the Dockerfile, expose the `PORT` env var (default 8000), set the optional env vars.

## 3. Option B: split hosting (static UI + API)

**Backend** (Render / Railway web service without Docker):

- Root directory: `backend`
- Build: `pip install -r requirements.txt`
- Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Env: `CORS_ORIGINS=https://<your-frontend-domain>` plus any optional LLM/search keys

**Frontend** (Vercel / Netlify / Cloudflare Pages):

- Root directory: `frontend`
- Build: `npm ci && npm run build`, output directory `dist`
- Env (build time): `VITE_API_BASE_URL=https://<your-backend-domain>`

## 4. Post-deploy checks

```bash
curl https://<your-domain>/api/health
curl -X POST https://<your-domain>/api/analyze -H 'Content-Type: application/json' \
     -d '{"text":"Studies show our tool is the best and guaranteed to work."}'
```

Then in the browser: Load demo article → Analyze → accept a fix → Compare → Export each format.

## 5. Production notes

- Keep `ALLOW_PRIVATE_URLS=false` (SSRF protection for URL extraction).
- Put the API behind HTTPS (all suggested hosts do this by default).
- The app is stateless and stores no user content; free-tier instances that sleep only add a cold-start delay.
- Consider a rate limit at the platform/proxy level if the URL extraction endpoint is public.

## Deployment record

| Item | Value |
|---|---|
| GitHub repository URL | _not created yet_ |
| Live URL | _not deployed yet_ |
| Deployed commit | _n/a_ |
| AI provider enabled | _n/a_ |
