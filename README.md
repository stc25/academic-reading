# Academic Reading — server handover

Target: `lcapps.langcen.cam.ac.uk`, installed at `/var/www/academic-reading`.
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

## 2. What to install on lcapps

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
  record plus TLS certificate for `lcapps.langcen.cam.ac.uk`.
- Add the deploying user to the `docker` group.

Resources are modest: ~1 GB RAM for both apps and both databases, ~2 GB disk for images.

## 3. What is in the transfer

Two archives. Send the second one over a secure channel; it contains secrets.

1. `academic-reading-handover.zip` — everything except secrets, virtualenvs and build junk.
   Unzips to an `academic-reading/` folder; its contents belong **at `/var/www/academic-reading`**:
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
   to `lcapps.langcen.cam.ac.uk`; the passwords are unchanged. Unzip it over the tree so
   each lands at `<app>/academic_reading_django/.env`. Delete the zip afterwards.

   Consider rotating `OLLAMA_API_KEY` once the new server is live.

## 4. Install

```bash
sudo mkdir -p /var/www && cd /var/www
unzip academic-reading-handover.zip          # creates /var/www/academic-reading
cd academic-reading
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
# old server — from /var/www/cnlp-docker-hosting (container names as in that compose)
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

**A. Bundled Caddy** (only if nothing else owns ports 80/443 on lcapps):

```bash
docker compose --profile caddy up -d
```

Uses `Caddyfile` with `DOMAIN` defaulting to `lcapps.langcen.cam.ac.uk`. Caddy gets a
Let's Encrypt certificate automatically — that needs the host reachable from the internet
on 80/443. If the University issues certificates instead, add `tls /path/cert.pem /path/key.pem`
inside the site block and mount the files.

**B. An existing nginx/Apache/Caddy on lcapps.** nginx equivalent:

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

Final URLs: `https://lcapps.langcen.cam.ac.uk/academic-reading/` and
`https://lcapps.langcen.cam.ac.uk/academic-reading-eng/`.

## 6. Configuration reference (`.env`, one per app)

| Variable | Notes |
|---|---|
| `SECRET_KEY` | Django secret. Keep the same value to preserve existing session cookies. |
| `PUBLIC_PATH`, `FORCE_SCRIPT_NAME`, `STATIC_URL` | The sub-path (`/academic-reading/`, `/academic-reading-eng/`). Only change if you change the proxy path. |
| `DJANGO_DEBUG` | `false` in production. |
| `DJANGO_ALLOWED_HOSTS` | Must include the public hostname — **a wrong value gives HTTP 400.** Set to `lcapps…` in the delivered files. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | `https://lcapps.langcen.cam.ac.uk`. Wrong value → form posts fail with 403. |
| `MARIADB_USER`, `MARIADB_PASSWORD`, `MARIADB_ROOT_PASSWORD` | Read by both the app and the MariaDB container. |
| `DATABASE_URL` | `mysql://user:pass@<db service name>:3306/<db>`. Service names are fixed in `docker-compose.yml`. |
| `OLLAMA_API_KEY` | Ollama Cloud key. |

Model names and per-language routing live in each app's `config.yaml` (baked into the image;
rebuild after editing). Prompts are in `prompts.yaml`.

**Gotcha:** MariaDB only applies `MARIADB_PASSWORD` / `MARIADB_ROOT_PASSWORD` when it creates
an *empty* data volume. If you later change those passwords in `.env`, the database keeps
the old ones — change them inside MariaDB too, or recreate the volume and re-import.

## 7. Operations cheat-sheet

```bash
cd /var/www/academic-reading
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

## 8. Using git

Each app is already its own git repository (`academic-reading/.git`, `academic-reading-eng/.git`;
full history is in the zip). Neither has a remote configured. Recommended:

1. Create two repos on the University GitLab/GitHub (or one repo per app), then on the old server:
   `git remote add origin <url> && git push -u origin main`
   (commit the one pending change first — `reading/static/reading/css/app.css` is modified but uncommitted in both).
2. On lcapps: `git clone` each into `/var/www/academic-reading/<app>`, then drop the `.env` files in.
   Updates become `git pull && docker compose up -d --build`.
3. Git already ignores `.env`, `db.sqlite3`, `.django-venv/`, `staticfiles/`. **Never commit `.env` or the SQL dumps** (reader history, secrets).
   The data and the secrets always travel separately, as above.

The top-level `docker-compose.yml`, `Caddyfile`, `deploy/` and this document are not in either
repo (they sit above both). Put them in a small third "deployment" repo, minus `deploy/*.sql`.

## 9. Things to know

- `db.sqlite3` files inside the app folders are stale local-dev leftovers; production uses MariaDB
  (selected whenever `DATABASE_URL` is set). Not shipped.
- No login/SSO on these apps. An auth + groups plan exists in `docs/AUTH_AND_GROUPS.md` (build paused).
- The shared reply cache is described in `docs/REPLY_CACHE.md`. It is stored in MariaDB (`reading_cachedreply`).
- Session cookies are named `are_sessionid` / `are_csrftoken`, scoped to the app path — moving host
  logs readers out once, which is harmless.
- On the old server these apps ran inside a larger shared compose (`cnlp-docker-hosting`) behind
  a shared Caddy. After cutover the two old containers + two MariaDB containers there can be
  removed, and the Caddyfile `/academic-reading*` blocks redirected to the new host.
