# Naming

The product must not be called "SearXNG" or carry that word. The Python
package stays `searx/` (renaming it would touch every upstream file and make
rebases miserable); the brand lives in `settings.yml: general.instance_name`,
`brand:`, the wordmark SVGs, `base.html` and the container labels. Upstream's
trademark position is informal, but the footer credit "based on SearXNG"
stays, as the AGPL requires attribution and it is honest.

Availability was checked on 2026-11-07 with two cheap probes: an
unauthenticated `GET https://github.com/<name>` (404 = the user/org handle is
free) and RDAP (`https://rdap.org/domain/<name>`, 404 = not registered).
Neither is a trademark search; do a USPTO / EUIPO check before printing
anything.

| # | Name | Why | GitHub handle | Domains | Conflicts noticed |
| --- | --- | --- | --- | --- | --- |
| 1 | **Verisift** | *verify* + *sift*: sift the web, verify the claim. Says what the fact-check mode does without claiming to be an oracle. | `verisift` free | `.com` taken, `.app` `.dev` `.io` free | none found |
| 2 | **Assay** | To assay is to test a metal for purity; short, unusual, works as a verb ("assay this"). | `assay-search` free (bare `assay` taken) | `assay.search` free, `assaysearch.com` taken | generic word; weak trademark but also few collisions |
| 3 | **Claimsight** | A clear sight on claims. Reads well on a verdict badge. | `claimsight` free | `.com` `.app` taken, `.io` free | none found |
| 4 | **Touchstone** | The stone assayers rubbed gold on to test it; "a touchstone for the web". | `touchstone-search` free | `touchstone.search` free | very common product word |
| 5 | **Litmus** | The litmus test. Instantly understood. | `litmus-search` free | `litmus.search` free | Litmus is a large email-testing SaaS; avoid for anything commercial |
| 6 | **Crucible** | Where claims are put to heat. | `crucible-search` free | `crucible.search` free | Atlassian Crucible (code review, retired) still shows up in dev searches |
| 7 | **Groundtruth** | The ML term for verified labels. Fits the "sources first, model second" rule. | `groundtruth-search` free | `groundtruth.app` taken | GroundTruth is an ad-tech company |
| 8 | **Sieve** | The simplest metaphor: a sieve for the web. | `sieve-search` free | `sievesearch.com` taken | overloaded (Sieve mail-filter language) |
| 9 | **Lodestar** | A guiding star; private search that points you somewhere true. | `lodestar-search` free | `lodestar.search` free | Lodestar is an Ethereum client |
| 10 | **Attest** | To bear witness; "attested" is what a sourced verdict is. | `attest-search` free | `attest.search` free | Attest is a market-research SaaS |

## Second round (2026-11-07, later the same day)

The user preferred the spelling **Verasift** (*vera*, Latin and Italian for
*true*, also a first name) over Verisift, and asked for more candidates.

| # | Name | Why | GitHub handle | Domains | Conflicts noticed |
| --- | --- | --- | --- | --- | --- |
| 11 | **Verasift** | *vera* + *sift*; reads like a person who sifts | `verasift` free | `.app` `.dev` `.io` `.search` free, `.com` taken | none found |
| 12 | **Sextant** | fix your position from fixed stars; sources as the stars | `sextant-search` free | `sextant.search` free | common product word |
| 13 | **Loupe** | the jeweller's glass; inspection at close range | `loupe-search` free | `loupe.search` free | a few small software products |
| 14 | **Nullius** | from *nullius in verba*, take nobody's word for it | `nullius` taken, `nullius-search` free | `nullius.search` free, `.com` `.app` taken | obscure to most people |
| 15 | **Plumbline** | the builder's test of true vertical | `plumbline` taken | `plumbline.search` free, `.app` taken | — |
| 16 | **Factum** | Latin "a thing done", root of *fact* | `factum` taken, `factum-search` free | `factum.search` free, `.app` taken | a few legal-tech products |
| 17 | **Parallax** | the same object from two viewpoints gives its true distance | `parallax-search` free | `parallax.search` free | Parallax Inc. (electronics) |
| 18 | **Aletheia** | Greek for truth as unconcealment | `aletheia-search` taken | `aletheia.search` free | hard to spell and say |
| 19 | **Vetter** | one who vets | `vetter` taken | `vetter.search` free | surname, several companies |

## Recommendation

**Verasift**, as the user prefers. It has the cleanest availability of
anything checked (GitHub handle plus four domains free, no collision
found) and it carries a meaning you can explain in one sentence. The
working identity is on the mockup canvas (row "Brand"): three mark
options (sieve-check, lens-with-mesh, funnel), a two-tone wordmark in
Albert Sans with *Vera* in teal, the tagline "Sift the web. Keep what's
true.", one brand colour and three reserved verdict colours.

Runners-up if Verasift falls at a trademark search: **Sextant** (free
everywhere checked), **Loupe** (short, says inspection), **Assay** from
the first round.

## Brand rules (for whichever name wins)

- One brand colour (teal `#0f6e8c`, `#5cc3e0` on dark) for the product's
  own voice: mark, mode switch, links. The verdict colours (false
  `#b3261e`, mixed `#a16207`, true `#15803d`) are reserved for
  fact-checkers' ratings and never appear on a button or in the brand.
- Model copy always names the model and where it ran ("qwen2.5-3b,
  local"; "Claude Haiku 5.5, Anthropic API"), never "AI" alone.
- Every page that sends anything off the box carries one sentence saying
  what left: "Only the query left this box."
- The footer credit "based on SearXNG" stays as text; the word never
  appears in the mark.

Once chosen, the rename sweep is: `general.instance_name`, `brand.*`,
`client/simple/src/brand/*.svg`, `searx/templates/simple/searxng-wordmark.min.svg`,
`base.html` (`<meta name="description">`, `<title>`, footer), `index.html`
`<h1>`, `container/Dockerfile` OCI labels, `package.json` name, and the
GitHub repository name (currently `SearXNG-Fork`, which contains the word).
