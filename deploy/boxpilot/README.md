# BoxPilot manifest

`verafact.yaml` is the catalog manifest for installing VeraFact through
BoxPilot's generic deployer. It is kept here, next to the image it describes,
and copied into BoxPilot's `catalog/` when a release is published.

The contract between the two is image + env + port + health check:

- **Image**: `ghcr.io/aes256afro/verafact`, built by the *VeraFact container*
  workflow on every push to `main`. The package must be public (a one-time
  switch in the package's settings) or no server can pull it. Pin the
  manifest's `image.reference` to a tag and digest once published.
- **Env**: `SEARXNG_SECRET` (generated), `SEARXNG_BASE_URL` (filled from the
  server's tailnet name and the port), the `FORK_*` model and source settings
  that `searx/fork/settings.py` reads from the environment.
- **Port**: 8080 in the container; `defaultExposure: tailnet` binds it to
  loopback and publishes it with Tailscale Serve.
- **Health**: the Dockerfile's `HEALTHCHECK` against `/healthz`.

Check the manifest against BoxPilot's schema from a BoxPilot checkout:

```sh
node --input-type=module -e "
import { readFileSync } from 'node:fs';
import { parse } from 'yaml';
import { validateManifest } from './server/catalog/schema.mjs';
console.log(validateManifest(parse(readFileSync(process.argv[1], 'utf8'))));
" /path/to/VeraFact/deploy/boxpilot/verafact.yaml
```
