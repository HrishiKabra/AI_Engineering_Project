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

## 1b. Claim a free domain (for HTTPS)

The stack serves a real `https://` site via Caddy, which needs a domain pointed at
the droplet. The Student Pack includes a **free Namecheap domain** (e.g. a `.me`).

Recommended: claim a personal domain (e.g. `hrishikabra.me`) and host this project on a
**subdomain** so your apex stays free for a portfolio:

1. Claim the domain from the pack (or use one you own).
2. After you create the droplet (next step) and have its IP, add a DNS **A record** for
   the subdomain: `f1  ->  <DROPLET_IP>` (host `f1`, value the droplet IP). This makes
   `f1.hrishikabra.me` resolve to the droplet. DNS can take a few minutes to propagate.
   Your apex (`hrishikabra.me`) is independent — point it wherever your portfolio lives.

> Want the app at the apex instead (`hrishikabra.me` itself)? Point the `@` A record at
> the droplet and set `DOMAIN=hrishikabra.me`. For a portfolio, the subdomain is cleaner.
>
> No domain yet? You can still run on `http://<DROPLET_IP>` by skipping the `caddy`
> service — but for a secure site, set the domain.

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
DOMAIN=f1.hrishikabra.me          # the domain whose A record points at this droplet
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
ufw allow OpenSSH && ufw allow 80/tcp && ufw allow 443/tcp && ufw --force enable
```

Once DNS has propagated, open **`https://<DOMAIN>`** — Caddy will have automatically
obtained a Let's Encrypt certificate on first request (give it ~30s the first time).
`http://` redirects to `https://`. Swagger is at `https://<DOMAIN>/docs`, the dashboard
at `https://<DOMAIN>/dashboard`.

> If the cert doesn't issue: confirm the A record points at the droplet IP, ports 80 and
> 443 are open, and check `docker compose -f docker-compose.prod.yml logs caddy`.

To update later: `git pull && make prod-up` (and `make prod-ingest` after new races, or
`make update GP=<slug>` — see the README).

## Hands-off auto-update (recommended): the watcher service

Install the always-on watcher once and never touch it again. It runs adaptively —
polling **fast while documents are actively being published** (a session is live) and
**backing off when quiet** — auto-starts on boot, and restarts on failure. No cron, no
calendar, no manual start.

```bash
# from the repo on the droplet (adjust WorkingDirectory in the unit if not /root/f1):
sudo cp scripts/f1-watcher.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now f1-watcher
journalctl -u f1-watcher -f          # watch it work
```

That's it — new races and in-session incidents appear on the live site on their own,
within a couple of minutes of the FIA publishing them. (The FIA has no push API, so
this is adaptive polling, not a webhook.) It defaults to the current calendar year and
rolls into future seasons automatically. Tunable via env in the unit file
(`MIN_INTERVAL`, `MAX_INTERVAL`, `SEASON`).

### Lighter alternatives

If you'd rather not run an always-on service:

**Weekly cron** — scrape + ingest once a week (good enough if you don't need in-session
latency):

```bash
crontab -e
# add, e.g., every Monday 06:00 UTC (adjust the repo path):
0 6 * * 1  /root/f1/scripts/cron-update.sh >> /var/log/f1-autoupdate.log 2>&1
```

`SEASON` defaults to the current calendar year, so it rolls into 2027+ on its own (the
scraper resolves each season from the FIA site). New races become searchable on the
live site automatically — no redeploy. Watch it with `tail -f /var/log/f1-autoupdate.log`.

> Note: this updates **data** only. Code/feature changes still ship via `git pull &&
> make prod-up`.

### Live watching during a race weekend

For near-real-time updates *while a session is running*, poll one Grand Prix on a
short interval and ingest documents as the stewards publish them — so an incident
becomes answerable a minute or two after the decision is posted:

```bash
make prod-watch GP=monaco SEASON=2026 INTERVAL=120   # runs until Ctrl-C
```

It re-checks the FIA page every `INTERVAL` seconds (default 120), downloads any new
documents, and ingests them into the live stack (idempotent — already-seen docs are
skipped). Start it before a session and stop it (Ctrl-C) after. The FIA has no push
API, so this is polling, not a webhook; ~1–2 min latency is the practical floor.
(`make watch …` is the same against the local dev stack.)

---

## What's hardened for public exposure

- **HTTPS by default:** a **Caddy** reverse proxy terminates TLS with an
  auto-provisioned, auto-renewing Let's Encrypt certificate and redirects http→https.
  Only Caddy is exposed (ports 80/443).
- **Postgres, the API, and nginx are not published to the internet** — they're only
  reachable on the internal Docker network. Caddy → nginx → API.
- **Rate limiting:** nginx caps `/ask` at 20 requests/min **per real client IP**
  (it reads `X-Forwarded-For` from Caddy).
- **Daily cost cap:** the app refuses `/ask` with HTTP 429 once `DAILY_REQUEST_CAP`
  requests have been served that day — a hard ceiling on OpenAI spend.
- **Secrets** live only in `.env` on the droplet (gitignored); the DB password is
  randomized via `POSTGRES_PASSWORD`.

## Cost notes

- Droplet: ~$12–18/mo, **$0 against the $200 credit** for ~12 months.
- OpenAI: ~$0.0004/query; the `DAILY_REQUEST_CAP` bounds the worst case (500/day ≈ $0.20/day).
- When done, **destroy the droplet** in DigitalOcean to stop billing against the credit.
