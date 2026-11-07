# Feature design

Companion to `ARCHITECTURE.md` (where things hook in) and `NAMING.md`. Each
section gives the module, the configuration keys, what the UI shows, and
what will go wrong. The product name is written as *Verisift* below pending
the decision in `NAMING.md`; nothing here depends on it.

All fork settings live under one `fork:` section, validated by a
`msgspec.Struct` (`searx/fork/settings.py: SettingsFork`) registered in
`searx/settings_defaults.py: SCHEMA`. Defaults are **everything off**: a
fresh install behaves like stock SearXNG with a different name and an
extra category tab.

```yaml
fork:
  factcheck:
    enabled: true
    offer_on_heuristic: true      # show the "check this as a claim?" banner
    google_api_key: ""            # ${FORK_FACTCHECK_GOOGLE_API_KEY}
    enrich_top: 5                 # fetch ClaimReview JSON-LD for the top N results without a verdict
  ocr:
    enabled: false
    backend: tesseract_http       # tesseract_http | vision_llm
    url: http://ocr:8884          # ${FORK_OCR_URL}
    max_upload_mb: 8
    languages: [eng]
  llm:
    backend: disabled             # disabled | openai_compat | anthropic | openai
    base_url: ""                  # ${FORK_LLM_BASE_URL}; openai_compat only
    model: ""                     # ${FORK_LLM_MODEL}
    api_key: ""                   # ${FORK_LLM_API_KEY}; never in settings.yml on disk
    timeout: 20
    max_tokens: 400
    allow_images: false           # let the OCR backend send screenshots to this model
    summarise_factchecks: true
    extract_claims: true
  modelfit:
    enabled: true
```

---

## 1. Fact-check mode

### What it is

A query that is a *claim* gets routed to fact-checking sources instead of
the general web, and the page lays results out as **claim → verdict →
source**. It is a mode of the search, visible in the URL (`mode=factcheck`)
and in the header, never an invisible rewrite of what the user asked.

### Ways in

| Trigger | Where | Behaviour |
| --- | --- | --- |
| Mode switch on the home page and results header (a two-state control: *Search* / *Check a claim*) | `simple_search.html`, `search.html` → hidden `mode` field | explicit; parsed in `webadapter.parse_mode()` |
| `!fc` or `!factcheck` bang | existing `BangParser`, because the new `fact check` category gets those bangs for free | explicit |
| Heuristic | `searx/fork/factcheck/trigger.py: looks_like_claim(q)` | **offers** only: a banner above normal results, "This reads like a claim. Check it against fact-checkers?" with one button. Off with `offer_on_heuristic: false`. |

The heuristic is deliberately dumb and cheap: leading "is it true", "did
… really", "fact check", "debunk", "hoax"; a quoted sentence; or a sentence
of 12+ words containing a verb-ish token and ending with a full stop. False
positives cost one banner, false negatives cost nothing, so precision
matters more than recall.

### Sources

Three tiers, best first. Every result carries its source's own words
(`verdict_raw`); the normalised verdict only drives the badge.

**Tier 1: Google Fact Check Tools API** (`searx/fork/factcheck/engines/google_factcheck.py`).
`GET https://factchecktools.googleapis.com/v1alpha1/claims:search?query=…&languageCode=…&pageSize=20&key=…`.
Aggregates ClaimReview markup published by IFCN signatories (Snopes,
PolitiFact, FactCheck.org, Full Fact, AFP Fact Check, Reuters, AP, Lead
Stories, Correctiv, Maldita and many more), with structured
`claims[].text / claimant / claimDate / claimReview[].publisher.name / url /
title / reviewDate / textualRating`. Needs a free API key from a Google
Cloud project; the engine is `inactive` until `google_api_key` is set, and
the preferences page says so in one line. Writing a dedicated engine rather
than a `json_engine` instance because the verdict is nested one level down
and we want a `ClaimReview` result, not a `MainResult`.

**Tier 2: direct site search of the big fact-checkers**, one `xpath` or
small Python engine per site, all in category `fact check`:

| Source | Search URL (to verify at implementation time, these sites redesign) | Notes |
| --- | --- | --- |
| PolitiFact | `https://www.politifact.com/search/?q={query}` | server-rendered; ratings appear in listing markup |
| FactCheck.org | `https://www.factcheck.org/?s={query}` | WordPress; no rating in listing, needs enrichment |
| Full Fact | `https://fullfact.org/search/?q={query}` | server-rendered; verdict in listing summary |
| AFP Fact Check | `https://factcheck.afp.com/search?q={query}` | Drupal; language sub-sites |
| Snopes | `https://www.snopes.com/search/?q={query}` | historically client-rendered; if the listing is empty without JS, fall to Tier 3 |
| Lead Stories | `https://leadstories.com/cgi-bin/mt/mt-search.cgi?search={query}` | Movable Type search |
| Correctiv (de), Maldita (es), Pagella Politica (it) | per-site | add as locale-gated engines (`language:` on the engine) |

**Tier 3: site-scoped fallback** (`searx/fork/factcheck/engines/site_scoped.py`).
A wrapper engine that takes `base_engine: duckduckgo` (any general engine
with a `request()`/`response()`) and `site: snopes.com`, prepends
`site:snopes.com` to the query, and relabels results. Used when a Tier 2
engine is suspended or returns nothing, and for sites that have no usable
search page.

**Enrichment** (`searx/fork/factcheck/claimreview.py`). Fact-checkers
embed schema.org `ClaimReview` as JSON-LD in each article. For the top
`enrich_top` results that have a URL but no verdict (Tier 2 listings
without ratings, every Tier 3 result), fetch the page once, parse
`<script type="application/ld+json">`, take `claimReviewed`,
`reviewRating.alternateName` / `ratingValue` / `bestRating` /
`worstRating`, `itemReviewed.author.name`, `itemReviewed.datePublished`,
`author.name`, `datePublished`. Cache by URL (`searx.cache`, 7 days).
Bounded: N fetches, 3 s each, in the existing engine thread pool, after
the main search so it never delays the first paint. A result that cannot
be enriched is still shown, with an *unrated* badge.

### Result type and normalisation

`searx/fork/result_types/claim_review.py`:

```python
class ClaimReview(MainResult, kw_only=True):
    template: str = "fork/claim_review.html"
    claim: str                    # what was claimed
    claimant: str = ""            # who said it, if known
    claim_date: str = ""
    verdict_raw: str              # the reviewer's own rating text
    verdict: Verdict = "unrated"  # normalised, see below
    reviewer: str                 # Snopes, PolitiFact, …
    review_date: str = ""
```

`Verdict = Literal["true", "mostly-true", "mixed", "mostly-false", "false",
"misleading", "unproven", "satire", "outdated", "unrated"]`. The mapping
from source strings to these lives in `searx/fork/factcheck/verdicts.yml`
(data, not code): "Pants on Fire", "Four Pinocchios", "False" → `false`;
"Half True", "Mixture" → `mixed`; "Miscaptioned", "Misleading",
"Missing context" → `misleading`; "Unproven", "Research in progress", "No
evidence" → `unproven`; "Labeled Satire" → `satire`; unknown strings →
`unrated` with the raw text shown. Numeric `ratingValue` with
`bestRating`/`worstRating` maps by quintile.

### Ranking and the claim summary

`searx/fork/factcheck/plugin.py` (`Plugin`, `id = "factcheck"`, always
active when the mode is on, not user-toggleable):

- `on_result`: in fact-check mode, drop results whose host is not a known
  fact-checker (list in `verdicts.yml`) unless the user also picked another
  category.
- `post_search`: cluster `ClaimReview` results whose `claim` texts are
  near-duplicates (normalised, token Jaccard ≥ 0.6), order clusters by
  number of reviewers, and add a plain `Answer` with no model involved:
  "4 fact-checkers reviewed this claim: 3 rate it false, 1 mostly false."
  That line is the product's verdict when the LLM is off.

### UI

`results.html` gets one include, `fork/factcheck_header.html`, rendered
when `mode == "factcheck"`: the claim as typed (editable), the source
count, the no-model summary, and the OCR panel (§2) and model panel (§3)
when present. Each `ClaimReview` renders via `fork/claim_review.html`:
badge (colour by `verdict`, text is `verdict_raw`), reviewer favicon and
name, review date, the claim in quotes, the article title as the link,
snippet. Clusters render as one card with a row of reviewer badges.
Mockups: see the artifact linked from the session (all four themes).

### Where it fails

- Claims nobody has fact-checked yet return nothing from all tiers; the
  page must say "no fact-check found" and offer the general search and the
  Wikipedia infobox, never an invented verdict.
- Paraphrase: the user's wording differs from the reviewed claim.
  Tier 1 handles paraphrase reasonably; Tier 2 site searches are keyword
  matches. Showing the reviewed claim next to the user's claim is what
  lets the user judge the match.
- Sites redesign; the `xpath` engines will break. The Tier 3 fallback and
  the engine suspension machinery exist for that.
- Non-English: Tier 1 has `languageCode`; Tier 2 is mostly English.

---

## 2. Image and screenshot input

### What it is

Paste or drop a screenshot of a social post. The server extracts the
text, pulls out checkable claims, and runs fact-check mode on the one the
user confirms. Nothing about the image is stored.

### Flow

1. `client/simple/src/js/plugin/fork_image_input.ts`: paste handler and a
   drop zone on the search box; posts `multipart/form-data` to
   `POST /fork/ocr` with the image only (no query, no cookies needed
   beyond the preferences cookie).
2. `searx/fork/ocr/route.py`: size and type checks (`max_upload_mb`,
   PNG/JPEG/WebP by magic bytes), re-encode through Pillow to strip
   metadata and defuse decoder exploits, then call the backend.
3. `searx/fork/ocr/backends/tesseract_http.py`: `POST {url}/tesseract`
   to a sidecar running Tesseract behind a tiny HTTP wrapper (the
   `hertzg/tesseract-server` image or our own 40-line Flask wrapper in
   `container/ocr/`). Preprocessing before OCR: upscale small images 2×,
   grayscale, invert when the median is dark (dark-mode screenshots),
   light denoise. Returns text with line boxes.
4. `searx/fork/ocr/clean.py`: strip social-UI chrome by pattern
   (`@handle`, `· 3h`, `12.4K`, "Replying to", "Show this thread",
   "Retweet", "Like", view counts, timestamps), join wrapped lines, keep
   paragraph breaks.
5. `searx/fork/ocr/claims.py`: rule-based first (sentence split; keep
   sentences with a subject and a verb and at least one of: a number, a
   proper noun, a date, a named entity-ish capitalised bigram; drop
   questions, imperatives, first-person feelings). With the LLM on and
   `extract_claims: true`, the model is asked to return the checkable
   claims as a JSON list, and the rule-based list is shown if the model
   fails or times out.
6. Response: JSON `{text, claims[]}`; the front end shows an **OCR panel**
   with the text in an editable box and the claims as buttons. Clicking
   one submits `/search?mode=factcheck&q=<claim>&ocr=<text>` (text only
   round-trips so the panel stays visible; the image is gone).

`backend: vision_llm` sends the image to the configured LLM backend
instead of Tesseract, only when `llm.allow_images` is also true. It reads
dark-mode and stylised text better and returns cleaner paragraphs, and it
is **off by default** because a remote backend would mean uploading
someone's screenshot to a third party.

### Honest reliability

- **Tesseract is good on clean, high-contrast, large text**: a tweet
  screenshot at native phone resolution reads nearly perfectly. It
  degrades fast on reposted-and-recompressed images, thin fonts on dark
  backgrounds (inversion helps, not always), emoji (dropped or turned into
  punctuation), meme text with outlines, text over photos, rotated or
  skewed crops, and mixed scripts. Expect wrong words in roughly one line
  in ten on an average Facebook screenshot, and a garbage result on an
  Instagram story.
- **Column order**: a thread or quote-tweet is two blocks; Tesseract may
  interleave them. The cleaning step cannot always tell which text is the
  post and which the quoted post.
- **Vision models hallucinate**: a small local VLM fills in plausible
  words where pixels are ambiguous, and it does so fluently, which is
  worse than Tesseract's visible garbage. That is why the OCR text is
  always shown and editable before anything is searched.
- **Claim extraction is the weak link**: most posts contain no checkable
  claim (opinion, joke, rhetorical question, "they don't want you to know").
  The rule-based extractor over-selects; the model under-explains. The UI
  lets the user pick or type the claim.
- **A screenshot proves nothing about the post**: OCR checks the words,
  not whether the account said them or whether the screenshot is
  doctored. The OCR panel carries that sentence permanently.
- **Privacy**: image in memory only; never written to disk or cache;
  never sent anywhere but the configured OCR sidecar on the Docker
  network, unless the owner turned on `allow_images` for a model backend,
  in which case the preferences page names the destination.

---

## 3. The LLM layer

### What it is

An optional model that **summarises the sources already found** and
states a verdict **with citations**. It is a reader of the fact-check
results, not a search engine and not an oracle. Off by default. It never
runs on an ordinary search.

### Backends

`searx/fork/llm/__init__.py` exposes one call:

```python
def complete(messages: list[Message], *, json_schema: dict | None = None,
             images: list[bytes] = (), timeout: float) -> Completion
```

| `backend` | Module | Talks to | Notes |
| --- | --- | --- | --- |
| `disabled` | `backends/disabled.py` | nothing | raises `LlmDisabled`; callers skip the feature |
| `openai_compat` | `backends/openai_compat.py` | `{base_url}/chat/completions` | LM Studio (`:1234/v1`), llama.cpp server (`:8080/v1`), Ollama (`:11434/v1`), vLLM. Streams off; `response_format: json_schema` when the server advertises it, otherwise a "reply with JSON only" instruction plus a strict parser. |
| `anthropic` | `backends/anthropic.py` | `https://api.anthropic.com/v1/messages` | default model `claude-haiku-5-5`; tool-use for the JSON schema |
| `openai` | `backends/openai.py` | `https://api.openai.com/v1/chat/completions` | same wire format as `openai_compat` with a fixed base URL |

All backends use `searx.network` (so outgoing proxies and timeouts apply)
and read the key from `FORK_LLM_API_KEY`. The settings page shows the
backend, model and base URL, and a "Test" button that sends one short
prompt and reports latency.

### The rule: no verdict without sources

Enforced in code, in `searx/fork/factcheck/plugin.py: post_search`, not
in the prompt:

1. If there are zero `ClaimReview` results, the LLM is **not called**. The
   page shows the no-model summary ("no fact-check found").
2. The prompt contains only the numbered sources (reviewer, rating, date,
   reviewed claim, title, snippet, URL) and the user's claim. No web
   access, no tools.
3. The output must match `LlmVerdict` (`verdict: Verdict`,
   `confidence: low|medium|high`, `summary: str ≤ 3 sentences`,
   `citations: list[int]`, `caveat: str`). Output with an empty
   `citations` list, or an index not in the source list, or a `verdict`
   stronger than every cited source, is discarded and the panel says
   "model summary unavailable" with the reason in the log.
4. The panel header names the backend and model ("Summary by
   qwen2.5-3b-instruct, local") so nobody mistakes it for a human
   fact-checker's words.

### Default small model

When `backend: openai_compat` points at a local server and `model` is
empty, the preferences page runs the model-fit helper (§4) and
**suggests** a model in the 1–4B instruction-tuned class at Q4_K_M
(examples at the time of writing: Qwen2.5-3B-Instruct, Llama-3.2-3B-
Instruct, Gemma-3-4B-it, Phi-4-mini; for `vision_llm` OCR: Qwen2.5-VL-3B
or MiniCPM-V). It suggests; the owner loads the model in LM Studio /
Ollama and types its id. The fork downloads nothing.

Why small: the task is summarising five short sources into three
sentences with citations. A 3B instruct model at Q4 does that acceptably
on a CPU-only box in a few seconds; a 7B is noticeably better at refusing
to over-claim; anything larger buys little here. The tier table in §4
says which is realistic.

---

## 4. Model-fit helper

### What it is

`searx/fork/modelfit/` reads the host's hardware and prints a ceiling
(parameters × quantisation × context) plus a checklist of what to look
for when choosing a model. Fully offline, no downloads, no telemetry; it
never names a URL.

### Reads

| Resource | How | Fallback |
| --- | --- | --- |
| CPU | `/proc/cpuinfo` (model name, cores, `avx2`/`avx512`/`amx` flags), `os.cpu_count()` | `platform.processor()` |
| RAM | `/proc/meminfo` `MemTotal`, `MemAvailable` | `os.sysconf('SC_PHYS_PAGES')` |
| NVIDIA | `nvidia-smi --query-gpu=name,memory.total,memory.used --format=csv,noheader,nounits` | absent → no GPU |
| AMD | `rocm-smi --showmeminfo vram --json` | absent → no GPU |
| Apple | `system_profiler SPHardwareDataType` (unified memory; usable ≈ 70 % of RAM) | — |
| Intel Arc | `xpu-smi` if present | absent → no GPU |

Inside the container the GPU tools exist only when BoxPilot passed the
device through (its manifest can ask for a GPU reservation), so the
helper also accepts an override file (`/etc/searxng/hardware.json`) that
BoxPilot can write from the host.

### The arithmetic

Weights: bytes ≈ parameters × bytes-per-parameter, with GGUF rules of
thumb Q4_K_M 0.60, Q5_K_M 0.72, Q6_K 0.82, Q8_0 1.07, F16 2.0 (GB per
billion parameters, including the small unquantised tensors).

KV cache: bytes per token = 2 × layers × kv_heads × head_dim × 2 (f16).
For a GQA model like Llama-3-8B (32 layers, 8 KV heads, 128 dim) that is
≈ 131 KB/token, so 8k context ≈ 1 GB; an older 7B without GQA is
≈ 0.5 MB/token, 8k ≈ 4 GB. The helper assumes GQA and says so.

Budget: GPU → `VRAM − 0.8 GB` for weights + KV; CPU → `MemAvailable −
3 GB` (OS, SearXNG, Valkey) with a hard rule never to exceed 70 % of
`MemTotal`. Speed on CPU is memory-bandwidth bound: tokens/s ≈ bandwidth
÷ weight bytes, so DDR4 dual-channel (~40 GB/s) gives ~15 tok/s for a 3B
Q4 and ~7 tok/s for an 8B Q4; DDR5 roughly doubles that. The helper
estimates bandwidth from the DIMM type when `dmidecode` is readable and
otherwise says "unknown, assume 30 GB/s".

### Tiers it will print

| Hardware | Ceiling | Suggest |
| --- | --- | --- |
| ≤ 8 GB RAM, no GPU | 1–2B Q4, 4k context | 1.5B instruct; summaries only, OCR via Tesseract |
| 8–16 GB RAM, no GPU | 3–4B Q4_K_M, 8k context | the default class; ~10 tok/s |
| 16–32 GB RAM, no GPU | 7–8B Q4_K_M, 8k context (slow, ~5 tok/s) or 3–4B comfortably | 3–4B unless patience |
| 6 GB VRAM | 3–4B Q4 fully offloaded, 8k | 3–4B |
| 8 GB VRAM | 7–8B Q4_K_M, 8k | 8B |
| 12 GB VRAM | 8B Q6/Q8 or 12–14B Q4 | 12–14B Q4 |
| 16 GB VRAM | 14B Q5 or 24B Q4 | 14B |
| 24 GB VRAM | 27–32B Q4_K_M, 16k | 32B |
| Apple 16 GB unified | 7–8B Q4 | 8B |
| Apple 32–64 GB unified | 14B–32B Q4 | 14B |

### The checklist it shows

- **Instruction-tuned** (the name ends in `-Instruct`, `-it`, `-chat`):
  base models do not follow the "cite your sources" instruction.
- **Context length** ≥ 8k: five sources plus a claim is 2–3k tokens.
- **Quantisation**: Q4_K_M is the sweet spot; below Q4 the model starts
  inventing citations; Q8 if the budget allows.
- **Structured output**: a model that reliably emits JSON (most 2024+
  instruct models) or a server that enforces a grammar (llama.cpp, vLLM).
- **Tool use**: not needed for this product; do not pay for it.
- **Vision**: only for the `vision_llm` OCR backend; look for `-VL` /
  multimodal models in the 2–4B class.
- **Licence**: check it allows your use; the helper does not.

The output is also served as `GET /fork/modelfit.json` (viewer-readable,
no secrets) so BoxPilot's Today page can draw it as a card.

---

## 5. Deployment: Tailscale-only and BoxPilot

### What the image provides

- Upstream's two-stage build, plus `HEALTHCHECK --interval=30s
  --timeout=3s CMD wget -qO- http://127.0.0.1:8080/healthz || exit 1`
  (upstream has none; without it BoxPilot can only use `health.kind:
  running`).
- `container/settings.template.yml` with the `fork:` section present and
  everything off, so the owner edits one file.
- Env overrides declared in `SCHEMA` for every secret or address:
  `SEARXNG_BASE_URL`, `SEARXNG_SECRET` (upstream), `FORK_LLM_BACKEND`,
  `FORK_LLM_BASE_URL`, `FORK_LLM_MODEL`, `FORK_LLM_API_KEY`,
  `FORK_OCR_URL`, `FORK_FACTCHECK_GOOGLE_API_KEY`.
- An optional `ocr` service in `container/docker-compose.yml` (Tesseract
  HTTP wrapper, no ports published, same Docker network).
- Port 8080, uid 977, volumes `/etc/searxng` and `/var/cache/searxng`,
  all as upstream.

### What the BoxPilot manifest will say

This lives in BoxPilot's `catalog/` and is written there, not here. The
shape the deployer expects (checked against BoxPilot's `schemaVersion: 2`
manifests on 2026-11-07):

```yaml
schemaVersion: 2
id: verisift
name: Verisift
category: Search
risk: low
image:
  reference: ghcr.io/aes256afro/verisift:<version>@sha256:<digest>
defaultExposure: tailnet          # install defaults to "Tailnet only"
ports:
  - id: web
    label: Web UI
    container: 8080
    host: 8084
    exposure: lan                 # the LAN choice if the owner switches it
publicHostname:
  env: SEARXNG_BASE_URL           # Serve's HTTPS name lands here, so links are right
env:
  - name: SEARXNG_SECRET
    generate: true
    secret: true
  - name: FORK_LLM_BASE_URL
    label: Local model server
    description: An OpenAI-compatible address (Ollama, LM Studio, llama.cpp). Leave empty to keep the model off.
    default: ""
  - name: FORK_LLM_API_KEY
    secret: true
    default: ""
  - name: FORK_FACTCHECK_GOOGLE_API_KEY
    secret: true
    default: ""
volumes:
  - id: config
    container: /etc/searxng
    path: config
  - id: cache
    container: /var/cache/searxng
    path: cache
    backup: false
sidecars:
  - id: ocr
    image: <tesseract http image>@sha256:…
health:
  kind: healthcheck
  timeoutSeconds: 120
```

With `defaultExposure: tailnet`, BoxPilot binds the web port to
127.0.0.1, publishes it with Tailscale Serve on the host's tailnet HTTPS
name, and fills `SEARXNG_BASE_URL` with that name. Nothing on the LAN or
the internet can reach the instance; `server.limiter` and
`public_instance` stay off, and `botdetection` never engages. When the
Ollama catalog app is installed on the same box, BoxPilot can default
`FORK_LLM_BASE_URL` to it; that is a manifest concern.

The image must be publicly pullable before the manifest lands (a new GHCR
package starts private; BoxPilot's `catalog-check-images` reports the
401 as `MISSING`).

---

## 6. Recommended order of implementation

1. **Rename and scaffold** (half a day): choose the name, do the brand
   sweep, add `searx/fork/` with the `SettingsFork` struct wired into
   `SCHEMA`, the `fact check` category tab, `tests/unit/fork/`, and a CI
   job that runs upstream's tests plus ours. This proves the rebase story
   before any feature.
2. **`ClaimReview` result type + template + Google Fact Check engine**
   (one to two days): the whole claim → verdict → source layout appears
   with one engine and real data. Normalisation table and its tests.
3. **Mode switch, bang, heuristic banner, ranking plugin, no-model
   summary** (one to two days): fact-check mode is now a complete feature
   without any model.
4. **Tier 2 site engines, Tier 3 fallback, ClaimReview enrichment**
   (two to three days, mostly selector work and caching).
5. **Container: HEALTHCHECK, settings template, env overrides, GHCR
   publish** (half a day), then the BoxPilot manifest in the other repo.
   At this point the product is deployable and useful.
6. **LLM layer with `disabled` and `openai_compat`** (one to two days):
   the client, the schema-validated `LlmVerdict`, the no-sources rule,
   the panel, the Test button. Anthropic and OpenAI backends are an hour
   each afterwards.
7. **Model-fit helper** (one day): pure functions over text fixtures from
   real machines, then the preferences section and the JSON endpoint.
8. **OCR** last (two to three days): the sidecar, the route, the
   preprocessing, the cleaner, the rule-based extractor, the panel. The
   `vision_llm` backend comes after Tesseract works, because it needs §6
   and `allow_images`.

OCR goes last because it is the least reliable feature and depends on
both the fact-check mode and (optionally) the LLM layer; shipping steps
1–5 first gives a product that is honest and complete on its own.
