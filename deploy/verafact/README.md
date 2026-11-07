# Running VeraFact on its own

This folder runs VeraFact as a plain Docker Compose stack, outside BoxPilot.
The BoxPilot manifest (planned in `docs/fork/FEATURES.md` §5) is the long-term
way to install it; this is the way to try it today.

## On the box

```sh
git clone https://github.com/AES256Afro/VeraFact.git /opt/verafact/src
cd /opt/verafact/src && git checkout fork/docs-foundation   # or main once merged
deploy/verafact/build.sh                 # produces the verafact:dev image

cp -r deploy/verafact /opt/verafact/app
cd /opt/verafact/app
cp .env.example .env                     # set SEARXNG_SECRET and SEARXNG_BASE_URL
docker compose up -d
```

The app listens on `127.0.0.1:8899` only. Publish it to the tailnet:

```sh
tailscale serve --bg --https=8899 http://127.0.0.1:8899
```

and open `https://<host>.<tailnet>.ts.net:8899`. `SEARXNG_BASE_URL` in `.env`
must be that same address or links and the preferences cookie will be wrong.

## Updating

```sh
cd /opt/verafact/src && git pull && deploy/verafact/build.sh
cd /opt/verafact/app && docker compose up -d
```

`config/settings.yml` is bind-mounted, so edits apply on the next restart.
Nothing in this folder is BoxPilot-specific; when the manifest lands, the same
image and settings move under the generic deployer.
