# Academic Reading — server handover

## Overview

Academic Reading is a pair of web apps that help language learners read authentic academic texts.
The learner opens a text (from a built-in library or their own upload) and works through ten guided
activities, from pre-reading to post-reading take-aways, with an AI tutor responding to each.

- **Academic Reading (v1)** — German, French, Italian and Chinese; the reader chooses their level and
  reply language.
- **Academic Reading v2 (`-eng`)** — texts in any language, with the tutor replying in English throughout.

Both are Django apps running in Docker with a MariaDB database each, using Ollama Cloud for the language
models. Sign-in (University SSO and email accounts) is built in but switched off by default; see `docs/LOGIN.md`. This repository holds both apps plus the Docker Compose stack, Caddy reverse
proxy configuration and scripts needed to run them together, and this document explains how to deploy them.

**Target:** any Linux server with Docker and the Compose plugin (written for Ubuntu 24.04), with the project
installed in a directory of your choice. Throughout this document `<install-dir>` is that directory
(for example `/var/www/academic-reading`) and `<hostname>` is the server's public hostname. The hostname appears in three places, so change
them together if you deploy somewhere else: the site address in `Caddyfile`, and `DJANGO_ALLOWED_HOSTS` and
`DJANGO_CSRF_TRUSTED_ORIGINS` in each app's `.env`. Commands below assume the project is in the current directory.

Written 2026-10-15. The stack in this folder was build-tested end to end on the
old server (databases restored from dumps, both apps built and passed `/health/`).

This is the **deployment README**. For what each app does and how to configure it, see
[`academic-reading/README.md`](academic-reading/README.md) (v1) and
[`academic-reading-eng/README.md`](academic-reading-eng/README.md) (v2).

## 1. What is being moved

Two sibling Django apps, each with its own MariaDB database, no user login:

| | v1 `academic-reading` | v2 `academic-reading-eng` |
|---|---|---|
| Public path | `/academic-reading/` | `/academic-reading-eng/` |
| Code | `academic-reading/academic_reading_django/` | `academic-reading-eng/academic_reading_django/` |
| Database | `academic_reading_v1` (service `mariadb_academic_reading_v1`) | `academic_reading_eng` (service `mariadb_academic_reading`) |
| Texts | bundled in `texts/` (baked into the image) | `sources/` + `source.cfg` (baked into the image) |

Each app is a `python:3.12-slim` image running gunicorn on port 8000, with
WhiteNoise serving static files. The LLM is **Ollama Cloud** (`OLLAMA_API_KEY`).
The `app.py`, `lib/`, `uv.lock`, `pyproject.toml` files at each app's top level
are the original Streamlit prototype and are **not** used by the Docker build.

## 2. What to install on the server

Only this. No Python, MariaDB, or Node on the host — everything runs in containers.

### Ubuntu 24.04 (noble) — apt packages

Option A, from Ubuntu's own repositories (simplest, recommended):

```bash
sudo apt update
sudo apt install -y docker.io docker-compose-v2 unzip curl git ca-certificates
sudo usermod -aG docker $USER      # then log out and back in
docker compose version             # verify
```

| Package | Why |
|---|---|
| `docker.io` | Docker Engine |
| `docker-compose-v2` | the `docker compose` plugin |
| `unzip` | unpack the transfer archives |
| `curl` | health checks |
| `git` | optional, for the git route (section 8) |
| `ca-certificates` | TLS to Docker Hub, PyPI and Ollama Cloud |

Option B, Docker's official repository (newer Docker): add the repo per
<https://docs.docker.com/engine/install/ubuntu/>, then install `docker-ce docker-ce-cli
containerd.io docker-buildx-plugin docker-compose-plugin` instead of `docker.io` and
`docker-compose-v2`. Do not install both sets — they conflict.
The same list is in `apt-packages.txt`.

### Other requirements

- **Docker Engine 26+** and the **Docker Compose v2 plugin** (`docker compose version`).
  Debian/Ubuntu: follow <https://docs.docker.com/engine/install/> (the `docker-ce`,
  `docker-compose-plugin` packages). The old server runs Docker 26.1 / Compose 2.26.
- `unzip` and `curl`; `git` if you take the git route (section 8).
- **Outbound HTTPS** from the host to `ollama.com` (Ollama Cloud), and to Docker Hub /
  PyPI during the first build (`python:3.12-slim`, `mariadb:11.4`, `caddy:2`, pip packages).
- **Inbound 80/443** to the host (or to whatever reverse proxy fronts it), and a DNS
  record plus TLS certificate for `<hostname>`.
- Add the deploying user to the `docker` group.

Resources are modest: ~1 GB RAM for both apps and both databases, ~2 GB disk for images.

### Running Docker without sudo (optional)

Docker's socket is root-owned, so the account that deploys the apps (below, `<username>`) cannot run
`docker compose` unless it is in the `docker` group or uses rootless Docker. Installing packages
with apt always needs an admin once. Pick one:

**Option 1 — `docker` group (simplest).** Note that membership is effectively root on that machine.

```bash
sudo usermod -aG docker <username>      # admin; then <username> logs out and back in
docker compose up -d --build
```

**Option 2 — rootless Docker (no extra privileges).** One-off, by an admin:

```bash
sudo apt install -y docker.io docker-compose-v2 uidmap dbus-user-session slirp4netns
sudo systemctl disable --now docker.service docker.socket    # optional: rootless only
sudo loginctl enable-linger <username>                       # keep containers running after logout
```

Then, as `<username>`:

```bash
dockerd-rootless-setuptool.sh install
echo 'export DOCKER_HOST=unix://$XDG_RUNTIME_DIR/docker.sock' >> ~/.bashrc && source ~/.bashrc
docker info | grep -i rootless
cd <install-dir> && docker compose up -d --build
```

Rootless caveats:
- A normal user cannot bind ports below 1024, so the bundled Caddy (80/443) will not start. Either an
  admin allows it (`sudo sysctl net.ipv4.ip_unprivileged_port_start=80`, persisted in
  `/etc/sysctl.d/99-unpriv-ports.conf`), or use the server's existing web server as the reverse proxy (section 5,
  option B) and skip `--profile caddy`.
- The apps publish on `127.0.0.1:8001` / `:8002`, so they work unchanged.
- Images and volumes, including the MariaDB data, live in `~/.local/share/docker` under that user's home:
  allow ~2 GB plus data, and include it in backups.
- Never run `docker compose down -v` unless you mean to delete the databases.
- Containers survive a reboot only with lingering enabled (above); the services use `restart: unless-stopped`.

**Option 3 — rootless Podman.** `sudo apt install -y podman podman-compose`, then `podman-compose up -d --build`.
Same 80/443 limitation; less proven with this compose file (only Docker has been tested).

## 3. What is in the transfer

Two archives. Send the second one over a secure channel; it contains secrets.

1. `academic-reading-handover.zip` — everything except secrets, virtualenvs and build junk.
   Unzips to an `academic-reading/` folder; its contents belong **in `<install-dir>`**:
   ```
   docker-compose.yml          standalone stack (apps, DBs, optional Caddy)
   Caddyfile                   optional bundled reverse proxy
   README.md                 this file
   deploy/                     backup-db.sh, restore-db.sh, SQL dumps
   academic-reading/           v1 app (its own .git repo)
   academic-reading-eng/       v2 app (its own .git repo)
   docs/                       design notes (reply cache, auth plan, etc.)
   ```
2. `academic-reading-secrets.zip` — the two `.env` files (they hold `SECRET_KEY`, the
   MariaDB passwords and `OLLAMA_API_KEY`). The hostnames in them are **already changed**
   to the hostname this was prepared for; edit them if yours differs (section 6). The passwords are unchanged. Unzip it over the tree so
   each lands at `<app>/academic_reading_django/.env`. Delete the zip afterwards.

   Consider rotating `OLLAMA_API_KEY` once the new server is live.

## 4. Install

```bash
unzip academic-reading-handover.zip          # creates an academic-reading/ folder: this is <install-dir>
cd academic-reading                          # i.e. cd <install-dir>
unzip -o ~/academic-reading-secrets.zip      # places the two .env files
chmod +x deploy/*.sh
chmod 600 */academic_reading_django/.env

# 1) start only the databases and load the data
deploy/restore-db.sh deploy/academic_reading_eng.sql deploy/academic_reading_v1.sql

# 2) build and start the apps
docker compose up -d --build

# 3) check
docker compose ps                                  # all "healthy"
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8001/health/   # v1 -> 200
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8002/health/   # v2 -> 200
```

The apps listen on `127.0.0.1:8001` (v1) and `127.0.0.1:8002` (v2) only — nothing is
public until you put a reverse proxy in front (next section). Override with
`ARV1_PORT` / `ARE_PORT` in the shell or a `.env` next to `docker-compose.yml`.

The entrypoint runs `migrate` and `collectstatic` on every start; restarts are safe.

### Data note — take a fresh dump at cutover

`deploy/*.sql` are the **2026-10-14 15:20** backups from the old server. They were taken
*before* the shared reply cache went live, so the cache table is empty in them and any
readers' history since then is missing. On cutover day, take fresh dumps on the old
server and restore those instead:

```bash
# source server — run where its compose stack runs; substitute its actual container names
docker exec cnlp-mariadb-academic-reading    sh -c 'mariadb-dump -uroot -p"$MARIADB_ROOT_PASSWORD" --single-transaction --default-character-set=utf8mb4 academic_reading_eng' > academic_reading_eng.sql
docker exec cnlp-mariadb-academic-reading-v1 sh -c 'mariadb-dump -uroot -p"$MARIADB_ROOT_PASSWORD" --single-transaction --default-character-set=utf8mb4 academic_reading_v1'  > academic_reading_v1.sql
```

Skipping the data is also safe: start without running `restore-db.sh`; the apps create
empty tables on first start and the reply cache refills as people use the library.
The only loss is cached model replies (re-generated on demand) and reader history.

Routine backups on the new server: `deploy/backup-db.sh` (writes `backups/*.sql`).

## 5. Reverse proxy (pick one)

Both apps are mounted on a **sub-path** and expect the proxy to **strip the prefix**
before forwarding (the app re-adds it via `FORCE_SCRIPT_NAME`). They must also receive
the original `Host` header.

**A. Bundled Caddy** (only if nothing else owns ports 80/443 on the server):

```bash
docker compose --profile caddy up -d
```

The site address in `Caddyfile` is a fixed hostname (it does not depend on the server's own hostname
or any environment variable) and serves `/academic-reading/` and `/academic-reading-eng/`. Edit it to your
`<hostname>` before starting. Caddy gets a
Let's Encrypt certificate automatically — that needs the host reachable from the internet
on 80/443. If the University issues certificates instead, add `tls /path/cert.pem /path/key.pem`
inside the site block and mount the files.

**B. An existing nginx/Apache/Caddy on the server.** nginx equivalent:

```nginx
location = /academic-reading      { return 308 /academic-reading/; }
location = /academic-reading-eng  { return 308 /academic-reading-eng/; }

location /academic-reading-eng/ {
    proxy_pass http://127.0.0.1:8002/;      # trailing slash strips the prefix
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_read_timeout 180s;                # LLM calls can be slow
}
location /academic-reading/ {
    proxy_pass http://127.0.0.1:8001/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_read_timeout 180s;
}
```

Keep the proxy timeout ≥ 180 s (gunicorn's `--timeout` is 180). Ollama Cloud latency
varies a lot, from seconds to minutes.

Final URLs: `https://<hostname>/academic-reading/` and
`https://<hostname>/academic-reading-eng/`.

## 6. Configuration reference (`.env`, one per app)

| Variable | Notes |
|---|---|
| `SECRET_KEY` | Django secret. Keep the same value to preserve existing session cookies. |
| `PUBLIC_PATH`, `FORCE_SCRIPT_NAME`, `STATIC_URL` | The sub-path (`/academic-reading/`, `/academic-reading-eng/`). Only change if you change the proxy path. |
| `DJANGO_DEBUG` | `false` in production. |
| `DJANGO_ALLOWED_HOSTS` | Must include the public hostname — **a wrong value gives HTTP 400.** Set it to your `<hostname>`. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | `https://<hostname>`. Wrong value → form posts fail with 403. |
| `MARIADB_USER`, `MARIADB_PASSWORD`, `MARIADB_ROOT_PASSWORD` | Read by both the app and the MariaDB container. The user name can be anything (the examples use `academic_reading` for v1 and `academic_reading_eng` for v2); use the same name in `DATABASE_URL`. |
| `DATABASE_URL` | `mysql://user:pass@<db service name>:3306/<db>`. Service names are fixed in `docker-compose.yml`. |
| `OLLAMA_API_KEY` | Ollama Cloud key. |

Sign-in settings (`AUTH_REQUIRED`, `AZURE_CLIENT_ID`/`AZURE_CLIENT_SECRET`, `EMAIL_*`) are documented in
`docs/LOGIN.md` and listed, all defaulting to off, in each app's `.env.production.example`.

Model names and per-language routing live in each app's `config.yaml` (baked into the image;
rebuild after editing). Prompts are in `prompts.yaml`.

**Gotcha:** MariaDB only applies `MARIADB_USER` / `MARIADB_PASSWORD` / `MARIADB_ROOT_PASSWORD` when it creates
an *empty* data volume. If you later change those values in `.env`, the database keeps
the old ones — change them inside MariaDB too, or recreate the volume and re-import.

## 7. Operations cheat-sheet

```bash
cd <install-dir>
docker compose ps
docker compose logs -f academic-reading-eng            # or academic-reading
docker compose up -d --build academic-reading-eng      # redeploy after code/config change
docker compose restart academic-reading                # restart only
docker compose down                                    # stop (data volumes survive)
```

Data lives in the Docker volumes `mariadb_academic_reading_data` and
`mariadb_academic_reading_v1_data` — never run `docker compose down -v` unless you mean it.

Note: the Docker build copies the app folder's code, config, prompts, and texts into the image,
so **editing a file on disk has no effect until you rebuild** that service.

Adding texts: v1 → drop files in `academic-reading/academic_reading_django/texts/…` and update
its `manifest.json`; v2 → drop `.txt`/`.md` into `academic-reading-eng/academic_reading_django/sources/`
(optionally describe in `source.cfg`; see `academic-reading-eng/README.md`). Then rebuild.

## 8. Deploying from git (both apps + Caddy)

The whole stack is in one public repository, <https://github.com/stc25/academic-reading>:
both apps (each with its full history), `docker-compose.yml`, `Caddyfile` and `deploy/`.
Git never holds secrets or data, so those are copied separately.

### First deployment

```bash
# 1) Prerequisites: Docker + Compose plugin (section 2), DNS and 80/443 open for <hostname>.
#    Port 80/443 must be free for the bundled Caddy; otherwise use your own proxy (section 5, option B).

# 2) Clone into place (the target folder must not already exist, or must be empty)
git clone https://github.com/stc25/academic-reading.git <install-dir>
cd <install-dir>

# 3) Secrets: place the two .env files (from academic-reading-secrets.zip, sent over a secure channel)
unzip -o ~/academic-reading-secrets.zip          # -> <app>/academic_reading_django/.env
chmod 600 */academic_reading_django/.env

# 4) Optional, only to carry over existing data: copy the SQL dumps in, then load them
#    (the .sql files are NOT in git; see "Data note" in section 4)
#    scp old-server:.../academic_reading_eng.sql old-server:.../academic_reading_v1.sql deploy/
#    deploy/restore-db.sh deploy/academic_reading_eng.sql deploy/academic_reading_v1.sql

# 5) Build and start both apps, both databases and Caddy in one go
docker compose --profile caddy up -d --build

# 6) Check
docker compose ps                                 # everything "healthy"
curl -s -o /dev/null -w '%{http_code}\n' https://<hostname>/academic-reading/
curl -s -o /dev/null -w '%{http_code}\n' https://<hostname>/academic-reading-eng/
```

The `--profile caddy` flag is what starts Caddy; without it only the apps and databases run
(bound to `127.0.0.1:8001` / `:8002`). Caddy gets a Let's Encrypt certificate automatically on the
first request, which needs the host reachable from the internet on 80/443. If the University
supplies certificates instead, see section 5.

If the deploying user cannot run Docker, see "Running Docker without sudo" in section 2.

### Updating after a change

```bash
cd <install-dir>
git pull
docker compose --profile caddy up -d --build     # rebuilds only what changed, restarts those services
```

Rebuild is needed for any change to code, `config.yaml`, `prompts.yaml`, texts or `sources/`, because
they are baked into the images. A changed `Caddyfile` needs `docker compose --profile caddy up -d --force-recreate caddy` (a plain `restart` can keep serving the old file, because `git pull` replaces the file and the container's bind mount still points at the old copy).
Use `--profile caddy` on every compose command that should include Caddy (`ps`, `logs`, `down`).
Databases and certificates live in Docker volumes, so `git pull` and rebuilds never touch them.

To redeploy one app only: `docker compose up -d --build academic-reading-eng` (or `academic-reading`).

### What stays out of git

`.env` files, `*.sql` dumps, `backups/`, zips, `db.sqlite3`, `.django-venv/` and `staticfiles/` are in `.gitignore`.
**Never commit `.env` or the SQL dumps** (secrets and reader history). Anything you edit on the server itself
(for example `.env`) is untouched by `git pull`; local edits to tracked files can block it, so change code in
the repo and pull rather than editing on the server.

### Also available as two separate repos

`academic-reading-eng` (v2) is also published alone at <https://github.com/stc25/academic-reading-eng>,
without the compose stack. Use the combined repo above for deployment.

## 9. Things to know

- `db.sqlite3` files inside the app folders are stale local-dev leftovers; production uses MariaDB
  (selected whenever `DATABASE_URL` is set). Not shipped.
- Sign-in (Entra SSO, email accounts) is built but **off by default**: setup and switch-over runbook in `docs/LOGIN.md`.
  Group-restricted texts are a separate, unbuilt plan (`docs/AUTH_AND_GROUPS.md`).
- The shared reply cache is described in `docs/REPLY_CACHE.md`. It is stored in MariaDB (`reading_cachedreply`).
- Session cookies are named `arm_sessionid` / `arm_csrftoken` (v1) and `are_sessionid` / `are_csrftoken` (v2), scoped to the app path — moving host
  logs readers out once, which is harmless.
- On the old server these apps ran inside a larger shared compose (`cnlp-docker-hosting`) behind
  a shared Caddy. After cutover the two old containers + two MariaDB containers there can be
  removed, and the Caddyfile `/academic-reading*` blocks redirected to the new host.
