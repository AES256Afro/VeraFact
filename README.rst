VeraFact
========

Search the web, keep the facts.

VeraFact is a privacy-respecting metasearch engine with a fact-check mode:
a query that is a claim is routed to fact-checking sources and laid out as
claim → verdict → source.  An optional model layer (local by default, a
frontier API if you choose) can summarise what the reviewers found, read a
claim out of a screenshot, or search alongside the engines; it is off until
the owner turns it on, and never gives a verdict without sources.

It is built on `SearXNG <https://github.com/searxng/searxng>`_ and keeps
upstream's engines, plugins, settings and theme.  Everything the fork adds
lives under ``searx/fork/`` and the ``fork:`` section of ``settings.yml``.

- Plan and status: ``docs/fork/`` (``ARCHITECTURE.md``, ``FEATURES.md``,
  ``NAMING.md``)
- Run it on a box today: ``deploy/verafact/README.md``
- Upstream documentation (settings, engines, admin): https://docs.searxng.org

License: AGPL-3.0-or-later, as upstream.
