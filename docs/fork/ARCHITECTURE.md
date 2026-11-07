# Fork architecture note

How upstream SearXNG is put together, and where each feature of this fork
hooks in. Read this before touching `searx/`. Paths are relative to the repo
root; upstream is `https://github.com/searxng/searxng` (remote `upstream`).

This fork is a separate product from the stock SearXNG app in the BoxPilot
catalog. Everything we add lives under `searx/fork/`, `searx/templates/<theme>/fork/`
and `docs/fork/`, so that rebasing on upstream stays a merge of mostly
disjoint files. Upstream's `AI_POLICY.rst` governs contributions *to*
upstream, not this repo; it does mean we should not expect to upstream fork
features, and that anything we do send back must be human-authored.

## 1. Request flow

```
browser ──GET/POST /search?q=…──▶ searx/webapp.py:search()
                                     │
                                     ├─ webadapter.get_search_query_from_webapp()
                                     │     RawTextQuery(q)  ← parses !bang, :lang, <timeout
                                     │     → SearchQuery(query, engineref_list, lang, safesearch,
                                     │                   pageno, time_range, …)
                                     │
                                     ├─ search.SearchWithPlugins(search_query, request, user_plugins)
                                     │     .search():
                                     │        plugins.pre_search()        ← can stop the search
                                     │        Search.search():
                                     │           external bang?  → redirect
                                     │           answerers.ask() → answers only, no engines
                                     │           search_standard(): one thread per engine
                                     │              processors[engine].search() → ResultContainer.extend()
                                     │                 (plugins.on_result() runs per result)
                                     │        plugins.post_search()       ← may add results
                                     │        result_container.close()    ← scoring / merging
                                     │
                                     └─ render('results.html', results=…, answers=…, infoboxes=…)
                                        or JSON / CSV / RSS (`format=`)
```

Key files:

| Concern | File | Notes |
| --- | --- | --- |
| Routes | `searx/webapp.py` | `/`, `/search`, `/autocompleter`, `/preferences`, `/healthz` (returns `OK`), `/stats`, `/config`, `/image` (proxy). Form is flattened into `sxng_request.form` in `pre_request()`; there is no `request.files` handling anywhere today. |
| Form → query | `searx/webadapter.py` | `parse_*` helpers for lang, safesearch, time range, timeout, categories. The place to parse a new form field. |
| Query syntax | `searx/query.py` | `QueryPartParser` subclasses: `!bang`, `:lang`, `<timeout`, `!!` external bang, `!!` lucky. Adding a prefix means one new parser class registered in `RawTextQuery._parse_query`. |
| Orchestration | `searx/search/__init__.py` | `Search` / `SearchWithPlugins`. Answerers short-circuit engines entirely when they answer. |
| Engine processors | `searx/search/processors/` | `online`, `offline`, `online_url_search`, `online_dictionary`, `online_currency`. An `offline` engine implements `search(query, params)` synchronously in-process. |
| Result container | `searx/results.py` | `ResultContainer.extend(engine_name, results)`, `.answers` (an `AnswerSet`), `.infoboxes`, `.suggestions`, `.corrections`, `.close()` does ranking. |
| Result types | `searx/result_types/` | `msgspec.Struct`s: `MainResult` (`template`, `title`, `content`, `url`, `thumbnail`, `pubdate`, `author`, `metadata`, `priority`…), `Answer`, `Translations`, `WeatherAnswer`, `KeyValue`, `Paper`, `Code`… Each type names its Jinja template. New structured results = new struct + new template, nothing else. |
| Settings | `searx/settings.yml` + `searx/settings_defaults.py` | YAML, validated against `SCHEMA` (plain `SettingsValue` entries or a `msgspec.Struct` per section). Env overrides are declared per key (`SEARXNG_PORT`, `SEARXNG_SECRET`, …). `use_default_settings: true` in a user file layers on top of the shipped defaults. New sections are added to `SCHEMA` as a struct. |
| Preferences | `searx/preferences.py` | Cookie-backed per-user settings, including which plugins are on (`PluginsSetting`). Form field names are `plugin_<id>`. |
| Plugins | `searx/plugins/_core.py` | `Plugin` ABC: `init(app)`, `pre_search(request, search) -> bool`, `on_result(request, search, result) -> bool`, `post_search(request, search) -> list[Result]`. Optional `keywords` make it a *special query* (first word of the query). Registered via FQN in `settings.yml: plugins:`. Shown in Preferences automatically from `PluginInfo`. |
| Answerers | `searx/answerers/_core.py` | `Answerer.answer(query) -> list[BaseAnswer]`, keyed by first-word keyword. When an answerer answers, **no engines run**. Good for instant local answers, wrong for anything that needs sources. |
| Engines | `searx/engines/*.py`, `searx/enginelib/` | A module with `request(query, params)` and `response(resp) -> EngineResults`, plus metadata (`about`, `categories`, `paging`, …). Declared instances live in `settings.yml: engines:`; the same module can back many instances. `json_engine` and `xpath` are config-only generic engines (`search_url`, `results_query`, `url_query`, `title_query`, `content_query`, `headers`, `paging`…). |
| Categories | `settings.yml: categories_as_tabs` | Which categories are tabs in the UI. An engine's `categories:` list puts it in a tab. |
| Templates | `searx/templates/simple/` | `base.html` → `index.html` (home) / `results.html` (results) / `preferences.html`. `simple_search.html` is the home search box, `search.html` the results-page header (logo, box, category tabs, filters). `elements/answers.html` renders `result_container.answers`; `result_templates/*.html` render main results by `result.template`; `answer/*.html` render answer structs. `macros.html` has `result_header/_sub_header/_sub_footer/_footer`. |
| Theme assets | `client/simple/` | Vite + Less + TypeScript, builds into `searx/static/themes/simple/`. `theme-auto|light|dark` and `center-alignment-yes|no` classes on `<html>` are set from preferences (`ui.theme_args.simple_style`). `src/less/definitions.less` holds the colour tokens; `src/js/plugin/*` are front-end plugins (autocomplete, hotkeys, infinite scroll). |
| Container | `container/Dockerfile`, `container/entrypoint.sh`, `container/settings.template.yml`, `container/docker-compose.yml` | Two-stage build on `searxng/base`; runs `granian` as uid 977 on `:8080`; `/etc/searxng/settings.yml` is created from the template on first start (random `secret_key`); volumes at `$__SEARXNG_CONFIG_PATH` and `$__SEARXNG_DATA_PATH` (`/var/cache/searxng`). Valkey is optional. |
| Tests | `tests/unit/`, `tests/robot/` | `pytest`-style unit tests (`test_plugins.py`, `test_webapp.py`, `engines/`, `processors/`). Fork tests go in `tests/unit/fork/`. |

Branding is spread over `searx/brand.py`, `settings.yml: general.instance_name` /
`brand:`, the wordmark SVGs in `client/simple/src/brand/` and
`searx/templates/simple/searxng-wordmark.min.svg`, `<title>`/meta in
`base.html`, the footer in `base.html`, and `index.html`'s `<h1>`. Renaming is
a sweep of those plus `container/Dockerfile` labels and `package.json`.

## 2. Where each fork feature hooks in

### 2.1 Fact-check mode

A *mode*, not a plugin toggle: it changes which engines run and which
template renders. Hooks, in request order:

1. **Trigger** (`searx/fork/factcheck/trigger.py`, called from
   `webadapter.get_search_query_from_webapp`): three ways in,
   `!fc` / `!factcheck` bang (a new `QueryPartParser` is not needed because
   `BangParser` already maps bangs to categories, so we add a `fact check`
   category and let `!fc` select it), an explicit form field
   `mode=factcheck` from the UI toggle, or a heuristic on the query
   ("is it true that…", "did X really…", "fact check:", a pasted sentence
   over ~12 words ending in a period). The heuristic only *offers* the mode
   on the results page (a banner with one click), it never silently switches.
2. **Engines** (`searx/fork/factcheck/engines/*.py` + entries in
   `searx/fork/settings-fork.yml`, merged into `settings.yml` by the build):
   one engine per fact-check source, all in category `fact check`, all
   returning a new result type.
3. **Result type** (`searx/fork/result_types/claim_review.py`):
   `ClaimReview(MainResult)` with `claim`, `claimant`, `claim_date`,
   `verdict_raw` (what the source said), `verdict` (normalised:
   `true|mostly-true|mixed|mostly-false|false|unproven|satire|outdated`),
   `reviewer`, `review_date`, `template = "fork/claim_review.html"`.
   Normalisation table lives next to it; every source keeps its own words
   visible, the normalised value only drives the badge colour and sorting.
4. **Ranking** (`searx/fork/factcheck/plugin.py`, a `Plugin` with
   `on_result` + `post_search`): when the mode is on, demote non-`ClaimReview`
   results, group reviews of the same claim, and add an `Answer` summarising
   "N reviews, M say false" without any model.
5. **Template** (`searx/templates/simple/fork/claim_review.html` and a
   `fork/factcheck_header.html` include in `results.html`): claim → verdict
   badge → source, plus the OCR panel (2.2) and LLM panel (2.3) when present.

### 2.2 Image / screenshot input

Upstream has no upload path at all, so this is the one feature that adds a
**route**: `POST /fork/ocr` (multipart, image only, size-capped) in
`searx/fork/ocr/route.py`, registered on the Flask app from `webapp.py`
behind one `if settings['fork']['ocr']['enabled']`. It calls an
`OcrBackend` (`searx/fork/ocr/backends/`: `tesseract_http` for a sidecar
container, `vision_llm` for an OCR-capable local model via the LLM layer),
runs claim extraction (`searx/fork/ocr/claims.py`, rule-based first, model
second), stores nothing, and redirects to `/search?mode=factcheck&q=<claim>`
with the OCR text passed through for display. The search box gets a paste /
drop target (`client/simple/src/js/plugin/fork_image_input.ts`) and the
preferences page a switch. The `image_proxy` machinery is unrelated: it
proxies *outbound* thumbnails, not uploads.

### 2.3 LLM layer

`searx/fork/llm/` is a thin client with one interface
(`complete(messages, *, json_schema=None, timeout)`) and four backends:
`openai_compat` (LM Studio, llama.cpp server, Ollama's `/v1`, vLLM),
`anthropic`, `openai`, `disabled`. It is used only from the fact-check
plugin's `post_search` (summarise the `ClaimReview` results that already
exist; the prompt gets the sources, the output must cite them by index) and
from the OCR claim extractor. It never runs on an ordinary search. Settings
section `fork.llm` in `SCHEMA`; secrets via env (`FORK_LLM_API_KEY`). The
output is an `LlmVerdict` answer struct rendered by `answer/fork_llm.html`,
always below the sources, never instead of them.

### 2.4 Model-fit helper

`searx/fork/modelfit/` reads `/proc/cpuinfo`, `/proc/meminfo`,
`nvidia-smi --query-gpu=memory.total --format=csv`, `rocm-smi --showmeminfo
vram`, or Apple `system_profiler` when present, and returns a
recommendation struct. Exposed on the preferences page under the LLM
section (`/preferences` already renders plugin and engine sections; this
adds one `fork/modelfit.html` include) and as `GET /fork/modelfit.json` for
BoxPilot's Today page. No network, no downloads: it prints a ceiling and a
checklist.

### 2.5 Deployment

The fork ships its own `container/` changes: `settings.template.yml` adds
the `fork:` section with everything off, `Dockerfile` adds a `HEALTHCHECK`
against `/healthz` (upstream has none, so BoxPilot can only wait for
"running"), and `docker-compose.yml` gains an optional `ocr` sidecar.
BoxPilot's generic deployer needs a manifest in *its* catalog (one YAML
file, `schemaVersion: 2`) naming this image, a `ports:` entry for 8080,
`defaultExposure: tailnet` (BoxPilot then binds the port to 127.0.0.1 and
publishes it with Tailscale Serve), `publicHostname.env: SEARXNG_BASE_URL`
so links are right behind Serve's HTTPS address, and `health.kind:
healthcheck`. Nothing in this repo knows about BoxPilot; the contract is
"image + env + port + health check". See `FEATURES.md` §5.

## 3. Rebasing on upstream

- Branch model: `main` tracks `upstream/master` plus fork commits; feature
  branches off `main`.
- Files we expect to conflict on every rebase, and keep edits minimal in:
  `searx/webapp.py` (two `include`-style hooks), `searx/webadapter.py` (one
  call), `searx/settings_defaults.py` (one `'fork': SettingsFork` line),
  `searx/templates/simple/results.html` and `search.html` (one include
  each), `searx/templates/simple/base.html` (branding), `client/simple/`
  (new Less and TS files are additive; `style.less` imports them).
- Everything else is new files. If a hook needs more than ~5 lines in an
  upstream file, move the logic into `searx/fork/` and call it.
