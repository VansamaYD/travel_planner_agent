# Synology NAS production deployment

Target layout:

```text
/volume1/docker/travel_planner/
├── app/                 # repository checkout
├── config/
│   ├── compose.env      # non-secret paths and port
│   ├── bootstrap.env    # APP_MASTER_KEY, mode 0600
│   └── runtime/         # encrypted settings written by the application
└── data/                # SQLite, cached files and exports
```

The NAS must be AMD64 and have Container Manager with Docker Compose v2. The
deploying SSH account needs access to `/var/run/docker.sock`.

## One-time preparation

Run with an administrative account:

```bash
sudo /usr/syno/sbin/synogroup --memberadd docker o_dfore
sudo mkdir -p /volume1/docker/travel_planner/{app,config/runtime,data}
sudo chown -R o_dfore:users /volume1/docker/travel_planner/app /volume1/docker/travel_planner/config
sudo chown -R 10001:10001 /volume1/docker/travel_planner/data /volume1/docker/travel_planner/config/runtime
sudo chmod 750 /volume1/docker/travel_planner
sudo chmod 700 /volume1/docker/travel_planner/data /volume1/docker/travel_planner/config/runtime
```

Log out and back in after changing the Docker group.

Copy `compose.env.example` to `config/compose.env` and
`bootstrap.env.example` to `config/bootstrap.env`. Generate the master key on a
trusted machine, for example:

```bash
openssl rand -base64 48
chmod 600 /volume1/docker/travel_planner/config/bootstrap.env
```

Never change `APP_MASTER_KEY` after data has been created unless a documented
key-rotation migration is used. Changing it directly makes encrypted records
unreadable.

## Start and upgrade

From `/volume1/docker/travel_planner/app`:

```bash
/usr/local/bin/docker compose \
  --env-file ../config/compose.env \
  -f deploy/compose.yaml up -d --build
```

Inspect health without printing environment secrets:

```bash
/usr/local/bin/docker compose \
  --env-file ../config/compose.env \
  -f deploy/compose.yaml ps
```

Open port 8080 only on the LAN, or preferably publish it through Synology
Reverse Proxy with HTTPS. Production cookies are `Secure`, so normal login over
plain `http://192.168.0.106:8080` is intentionally not supported. After first
login, configure model, map, weather, XHS and SMTP values in **我的 → 模型与外部连接**,
then restart the API/Web stack once to apply them.

## Backup

Stop the API before taking a cold backup of `data/` and always back up
`config/bootstrap.env` together with `config/runtime/`. The encrypted database
and runtime integration file are not recoverable without the same master key.
