# Deploying to a DigitalOcean droplet (free with student credit)

The whole stack is a single `docker compose` project, so hosting it is: get a small
Linux VM, clone the repo, set one secret, run two commands. Below uses DigitalOcean
because the **GitHub Student Developer Pack** gives **$200 of DigitalOcean credit**
(≈ a year of the droplet below), but any Ubuntu VM works the same way.

Estimated time: ~20 minutes. Estimated cost with credit: **$0**.

---

## 1. Get the credit

1. Apply for the **GitHub Student Developer Pack**: <https://education.github.com/pack>
   (use your `@tulane.edu` email; approval is usually quick).
2. In the pack, find **DigitalOcean** and claim the **$200 / 12-month** credit. It
   takes you to DigitalOcean to create an account and apply the code.

> Alternative with no credit card: **Azure for Students** ($100, no card) — create an
> Ubuntu VM there instead and skip to step 3.

## 2. Create the droplet

In DigitalOcean: **Create → Droplets**.

- **Image:** Ubuntu 24.04 LTS. (Optional shortcut: the **Marketplace → "Docker on
  Ubuntu"** image comes with Docker preinstalled — pick it to skip step 3a.)
- **Size:** Basic → Regular → **2 GB RAM / 1–2 vCPU** (~$12–18/mo, covered by credit).
  2 GB matters: building the image and running Postgres + the agent needs the headroom.
- **Authentication:** add your **SSH key** (recommended) or a password.
- Create, then copy the droplet's **public IP**.

## 3. Set up the droplet

SSH in: `ssh root@<DROPLET_IP>`

**a. Install Docker** (skip if you used the Docker Marketplace image):

```bash
curl -fsSL https://get.docker.com | sh
```

**b. Clone the repo** (or your fork) and enter it:

```bash
git clone <YOUR_REPO_URL> f1-rule-interpreter
cd f1-rule-interpreter
```

**c. Create the secrets file** `.env` (NOT committed):

```bash
cat > .env <<'EOF'
OPENAI_KEY=sk-...                 # your OpenAI key
POSTGRES_PASSWORD=<a-long-random-string>
DAILY_REQUEST_CAP=500             # max OpenAI-backed requests/day (caps spend)
EOF
```

## 4. Launch + load the corpus

```bash
make prod-up         # build + start db + api + web (web on port 80)
make prod-migrate    # create the schema
make prod-ingest     # parse + embed the FIA corpus (~a few minutes, ~$0.003)
```

(No `make`? The equivalent commands are in `docker-compose.prod.yml`'s header.)

## 5. Open the firewall + visit

```bash
ufw allow OpenSSH && ufw allow 80/tcp && ufw --force enable
```

Open **`http://<DROPLET_IP>`** — the web UI. Swagger is at `http://<DROPLET_IP>/docs`,
the dashboard at `http://<DROPLET_IP>/dashboard`.

To update later: `git pull && make prod-up` (and `make prod-ingest` after new races, or
`make update GP=<slug>` — see the README).

---

## What's hardened for public exposure

- **Postgres and the API are not published to the internet** — only the web/nginx
  service (port 80) is. nginx proxies the API over the internal Docker network.
- **Rate limiting:** nginx caps `/ask` at 20 requests/min per IP.
- **Daily cost cap:** the app refuses `/ask` with HTTP 429 once `DAILY_REQUEST_CAP`
  requests have been served that day — a hard ceiling on OpenAI spend.
- **Secrets** live only in `.env` on the droplet (gitignored); the DB password is
  randomized via `POSTGRES_PASSWORD`.

## Optional: HTTPS with a domain

`http://<IP>` works but shows "not secure". For a clean `https://` link:

1. The Student Pack includes a **free Namecheap `.me` domain** (or use any domain).
   Point an `A` record at the droplet IP.
2. Put **Caddy** in front for automatic Let's Encrypt TLS — replace the `web` service's
   port mapping and add a one-line `Caddyfile` (`yourdomain.com { reverse_proxy web:3000 }`).
   Ask and I'll wire this up.

## Cost notes

- Droplet: ~$12–18/mo, **$0 against the $200 credit** for ~12 months.
- OpenAI: ~$0.0004/query; the `DAILY_REQUEST_CAP` bounds the worst case (500/day ≈ $0.20/day).
- When done, **destroy the droplet** in DigitalOcean to stop billing against the credit.
