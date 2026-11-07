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

## Recommendation

**Verisift** first: the only candidate with no collision found, a free
GitHub handle, and free `.app`/`.dev`/`.io`. **Assay** second: shortest,
`assay.search` is free, and "assay mode" is a good name for the fact-check
mode even if the product takes another name.

Once chosen, the rename sweep is: `general.instance_name`, `brand.*`,
`client/simple/src/brand/*.svg`, `searx/templates/simple/searxng-wordmark.min.svg`,
`base.html` (`<meta name="description">`, `<title>`, footer), `index.html`
`<h1>`, `container/Dockerfile` OCI labels, `package.json` name, and the
GitHub repository name (currently `SearXNG-Fork`, which contains the word).
