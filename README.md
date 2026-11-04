# TAMU Digital Collections Types Vocabulary

A SKOS vocabulary combining two type systems used across Texas A&M University
Libraries' digital collections (Archipelago):

- **ADO Types** (`source/ado_types.yml`) — the underlying Archipelago Digital
  Object types used to model digital objects in the repository (e.g. *Image
  ADO*, *Map ADO*, *Book ADO*).
- **Browse/Search Types** (`source/browse_search_type.yml`) — the public-facing
  genre/format terms end users browse and search by (e.g. *Postcard*,
  *Correspondence*, *Photograph*), cross-linked back to the ADO type(s) that
  implement them.

The two files are compiled into a single `skos:ConceptScheme` under the
namespace `https://w3id.org/tamu/dc-types/`.

## Repository layout

```
source/                  Hand-maintained source of truth (YAML)
scripts/build_site.py    Converts source/*.yml -> ttl, rdf, index.html
tamu-dc-types.ttl        Generated: Turtle serialization
tamu-dc-types.rdf        Generated: RDF/XML serialization
index.html               Generated: human-readable browser (GitHub Pages site)
w3id.org.htaccess        Content-negotiation rules to submit to w3id.org
```

**`source/*.yml` is the only file you should hand-edit.** The `.ttl`, `.rdf`,
and `index.html` files are generated — regenerate them after any source
change rather than editing them directly.

## Regenerating the site

```bash
pip install -r requirements.txt
python3 scripts/build_site.py
```

This rewrites `tamu-dc-types.ttl`, `tamu-dc-types.rdf`, and `index.html` at
the repo root. Commit the results. A GitHub Actions check
(`.github/workflows/build-check.yml`) fails the build if the generated files
are out of sync with `source/*.yml`, so regenerate before pushing.

The script also prints a warning for any `skos:broader` / `skos:narrower` /
`skos:related` reference in the source YAML that doesn't match an actual
concept (currently: `Issue` references a `Journal ADO` that doesn't exist in
`ado_types.yml` — likely a typo for `Book ADO`, worth confirming with whoever
maintains the source).

## Publishing on GitHub Pages

1. In repo settings, enable **Pages**, source = `main` branch, root folder.
2. The site will be live at `https://tamulib-dc-labs.github.io/tamu-dc-ontology/`.
3. `tamu-dc-types.ttl` and `tamu-dc-types.rdf` are served as plain static
   files alongside `index.html`.

### A note on GitHub Pages' MIME types

GitHub Pages is a static host and doesn't let you set custom response
headers, so `.ttl`/`.rdf` may be served with a generic content type (e.g.
`text/plain` or `application/octet-stream`) rather than `text/turtle` /
`application/rdf+xml`. Most RDF tooling (rdflib, `rapper`, etc.) dispatches
on file extension when you pass a URL ending in `.ttl`/`.rdf`, so this is
usually harmless in practice. If you need exact `Content-Type` headers, put
a CDN (e.g. Cloudflare) in front of the Pages site, since there is no
`.htaccess`/`_headers` equivalent on vanilla GitHub Pages.

## Content negotiation via w3id.org

Concept URIs are minted under `https://w3id.org/tamu/dc-types/` rather than
the raw `github.io` URL, so the namespace survives any future move of the
GitHub Pages site. GitHub Pages can't do real `Accept`-header-based content
negotiation (it's static hosting), so **w3id.org** — which runs Apache in
front of the identifier space — handles it instead, 303-redirecting to the
right file on GitHub Pages:

```bash
curl -L -H "Accept: text/turtle"      https://w3id.org/tamu/dc-types/
curl -L -H "Accept: application/rdf+xml" https://w3id.org/tamu/dc-types/
curl -L -H "Accept: text/html"        https://w3id.org/tamu/dc-types/
```

To activate this:

1. Fork [perma-id/w3id.org](https://github.com/perma-id/w3id.org).
2. Add this repo's `w3id.org.htaccess` as `tamu/dc-types/.htaccess` in that
   fork.
3. Open a PR against `perma-id/w3id.org` per their contribution guidelines.

Until that PR is merged, the vocabulary is still fully usable directly at
`https://tamulib-dc-labs.github.io/tamu-dc-ontology/` — the `w3id.org`
namespace is just the long-term-stable front door for the URIs baked into
the RDF.

**Important:** the concept URIs in `tamu-dc-types.ttl` / `.rdf` already use
the `w3id.org` namespace (`BASE` in `scripts/build_site.py`). If you decide
*not* to register with w3id.org, update `BASE` to the GitHub Pages URL (or
another domain you control) and regenerate before treating these URIs as
final — changing the namespace later means every published URI changes.

## Status

This is a first draft generated directly from the current `source/*.yml`
files. Things worth a maintainer's review before calling it final:

- Term slugs (e.g. `Image ADO` → `ImageADO`) are generated automatically;
  rename any that read awkwardly before URIs are published/cited anywhere.
- The `Journal ADO` dangling reference noted above.
- Whether ADO Types and Browse/Search Types should stay in one
  `ConceptScheme` (current approach) or be split into two linked schemes.
- Licensing/rights statement for the vocabulary (none is currently declared).
