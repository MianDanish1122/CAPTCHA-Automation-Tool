# Putting the CAPTCHA Inspector online (live link for reviewers)

Two parts, both free or low cost to start:

| Part | Where | Why |
|---|---|---|
| **Backend API** (FastAPI, Chromium, Tesseract) | **Render** (Docker web service) | Needs a long-running Python process with a browser and Tesseract; Vercel cannot run that. |
| **Frontend** (Next.js) | **Vercel** | Free and built for Next.js. |

Both read the same GitHub repository: `https://github.com/MianDanish1122/CAPTCHA-Automation-Tool`.

## 1. Deploy the backend on Render
1. Sign in to https://render.com with GitHub.
2. **New + → Blueprint** → choose this repository. Render reads `render.yaml` and proposes the `captcha-inspector-api` service.
3. When asked for the secret values, enter:
   - `REVIEW_USER` and `REVIEW_PASSWORD`: the reviewer login you will give the employer (the password is only stored in Render).
   - `CORS_ALLOWED_ORIGINS`: leave blank for now; you will fill it in at step 3.
   `JWT_SECRET_KEY` and `AUDIT_HMAC_KEY` are generated automatically.
4. Deploy. When it is live, open `https://<your-service>.onrender.com/api/health`. It should answer `ok`. Note this URL.

Notes
- The database is SQLite inside the container. On the free/starter plans it is **reset on every redeploy or restart**; the reviewer login is re-created automatically at each start, but old scan history disappears. For a persistent demo add a Render Disk mounted at `/app/data`.
- The first request after idle time can take about a minute on free plans.

## 2. Deploy the frontend on Vercel
1. Sign in to https://vercel.com with GitHub and **Add New → Project** → import the repository.
2. Set **Root Directory** to `frontend`.
3. Add the environment variable `NEXT_PUBLIC_API_BASE_URL` = the Render URL from step 1 (no trailing slash).
4. Deploy and note the Vercel URL (for example `https://captcha-inspector.vercel.app`).

## 3. Connect them
In Render, open the service → **Environment** → set `CORS_ALLOWED_ORIGINS` to the exact Vercel URL (no trailing slash) and save; the service restarts. Then open the Vercel URL and log in with the reviewer account.

## 4. What works on the hosted version
| Feature | Hosted behaviour |
|---|---|
| OCR Laboratory, benchmark | Works. |
| Verification (test keys + failure scenarios) | Works (needs outbound internet from Render, which it has). |
| Evaluation, Reports, Human Review | Work. |
| URL Inspector / Batch on external websites | **Disabled by default** (`ENABLE_LIVE_SCAN=false`). To allow it, set `ENABLE_LIVE_SCAN=true` and `ALLOWED_DOMAINS` to the exact domains you are authorised to test. Chromium needs more memory than the smallest plan. |
| Local fixtures / localhost targets | Disabled in production by design. |

## 5. Security reminders
- Use a password that is not trivial for a public deployment; remove or change the reviewer account when the review is over.
- Keep `ALLOWED_DOMAINS` as small as possible.
- The API enforces rate limits per client address; behind Render's proxy set `TRUSTED_PROXIES` only if you know the proxy address.
