#!/usr/bin/env python3
"""Build the TAMU DC Types vocabulary from source/*.yml.

Generates, at the repo root (so GitHub Pages can serve them directly):
  - tamu-dc-types.ttl   (Turtle)
  - tamu-dc-types.rdf   (RDF/XML)
  - index.html          (human-readable browser / landing page)

Run with:  python3 scripts/build_site.py
Requires:  pyyaml, rdflib
"""
import html
import os
import re
import sys
from pathlib import Path

if os.environ.get("PYTHONHASHSEED") != "0":
    # rdflib's pretty-xml serializer orders elements using Python's string
    # hashing internally (via dict/set iteration order), which is randomized
    # per-process by default. Without a fixed hash seed, re-running this
    # script produces a byte-different but semantically identical .rdf file
    # on every invocation, which defeats the CI drift check. Re-exec once
    # with a fixed seed so output is reproducible regardless of how this
    # script is invoked.
    os.environ["PYTHONHASHSEED"] = "0"
    os.execv(sys.executable, [sys.executable] + sys.argv)

import yaml
from rdflib import Graph, Namespace, URIRef, Literal
from rdflib.namespace import RDF, SKOS, DCTERMS

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = REPO_ROOT / "source"

BASE = "https://w3id.org/tamu/dc-types/"
GH_PAGES_BASE = "https://tamulib-dc-labs.github.io/tamu-dc-ontology/"
NS = Namespace(BASE)
SCHEME_URI = URIRef(BASE)

VOCAB_TITLE = "TAMU Digital Collections Types Vocabulary"


def slugify(label: str) -> str:
    parts = re.split(r"[\s/]+", label.strip())
    parts = [re.sub(r"[^A-Za-z0-9_]", "", p) for p in parts]
    return "".join(p[:1].upper() + p[1:] if p else "" for p in parts)


def as_list(v):
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def load_source(path: Path):
    data = yaml.safe_load(path.read_text())
    return data.get("profile", {}), data.get("types", {})


def main():
    sources = [
        (SOURCE_DIR / "ado_types.yml", "ADO Types"),
        (SOURCE_DIR / "browse_search_type.yml", "Browse/Search Types"),
    ]

    label_to_uri = {}
    all_entries = []  # dicts, document order preserved
    for path, source_label in sources:
        profile, types = load_source(path)
        for key, body in types.items():
            label = body.get("skos:prefLabel") or key
            slug = slugify(label)
            uri = NS[slug]
            label_to_uri[label] = uri
            label_to_uri[key] = uri
            all_entries.append({
                "uri": uri,
                "slug": slug,
                "label": label,
                "body": body,
                "source": source_label,
                "profile": profile,
            })

    entry_by_uri = {e["uri"]: e for e in all_entries}

    g = Graph()
    g.bind("skos", SKOS)
    g.bind("dcterms", DCTERMS)
    g.bind("tamudc", NS)

    g.add((SCHEME_URI, RDF.type, SKOS.ConceptScheme))
    g.add((SCHEME_URI, SKOS.prefLabel, Literal(VOCAB_TITLE, lang="en")))
    g.add((SCHEME_URI, DCTERMS.title, Literal(VOCAB_TITLE, lang="en")))
    g.add((SCHEME_URI, DCTERMS.description, Literal(
        "A SKOS vocabulary combining Archipelago Digital Object (ADO) Types and "
        "Browse/Search Types used across Texas A&M University Libraries digital "
        "collections (Archipelago).", lang="en")))
    g.add((SCHEME_URI, DCTERMS.publisher, Literal("Texas A&M University Libraries", lang="en")))

    for e in all_entries:
        uri, label, body = e["uri"], e["label"], e["body"]
        g.add((uri, RDF.type, SKOS.Concept))
        g.add((uri, SKOS.inScheme, SCHEME_URI))
        g.add((uri, SKOS.prefLabel, Literal(label, lang="en")))
        g.add((uri, DCTERMS.source, Literal(e["source"], lang="en")))
        for a in as_list(body.get("skos:altLabel")):
            g.add((uri, SKOS.altLabel, Literal(a, lang="en")))
        if body.get("skos:definition"):
            g.add((uri, SKOS.definition, Literal(body["skos:definition"], lang="en")))
        if body.get("skos:note"):
            g.add((uri, SKOS.scopeNote, Literal(body["skos:note"], lang="en")))
        for ex in as_list(body.get("skos:example")):
            g.add((uri, SKOS.example, Literal(ex)))
        for m in as_list(body.get("skos:exactMatch")):
            g.add((uri, SKOS.exactMatch, URIRef(m)))
        for m in as_list(body.get("skos:relatedMatch")):
            g.add((uri, SKOS.relatedMatch, URIRef(m)))

    unresolved = set()

    def resolve(target_label):
        u = label_to_uri.get(target_label)
        if u is None:
            u = NS[slugify(target_label)]
            unresolved.add(target_label)
        return u

    for e in all_entries:
        uri, body = e["uri"], e["body"]
        for field, prop, relname in (
            ("skos:broader", SKOS.broader, "broader"),
            ("skos:narrower", SKOS.narrower, "narrower"),
            ("skos:related", SKOS.related, "related"),
        ):
            targets = []
            for target_label in as_list(body.get(field)):
                targets.append(resolve(target_label))
                g.add((uri, prop, resolve(target_label)))
            e[relname] = targets

    broader_subjects = {s for s, _, _ in g.triples((None, SKOS.broader, None))}
    for e in all_entries:
        e["is_top"] = e["uri"] not in broader_subjects
        if e["is_top"]:
            g.add((SCHEME_URI, SKOS.hasTopConcept, e["uri"]))
            g.add((e["uri"], SKOS.topConceptOf, SCHEME_URI))

    unresolved = {u for u in unresolved if NS[slugify(u)] not in entry_by_uri}
    if unresolved:
        print("NOTE: these related/broader/narrower labels have no matching "
              "source entry (dangling references in the source YAML):", file=sys.stderr)
        for u in sorted(unresolved):
            print(f"  - {u!r}", file=sys.stderr)

    ttl_path = REPO_ROOT / "tamu-dc-types.ttl"
    rdf_path = REPO_ROOT / "tamu-dc-types.rdf"
    g.serialize(destination=str(ttl_path), format="turtle")
    g.serialize(destination=str(rdf_path), format="pretty-xml")
    print(f"Wrote {ttl_path} ({len(g)} triples)")
    print(f"Wrote {rdf_path}")

    write_html(all_entries, entry_by_uri, unresolved)


def esc(s):
    return html.escape(str(s), quote=True)


def pill_links(uris, entry_by_uri, css_class="pill"):
    out = []
    for u in uris:
        e = entry_by_uri.get(u)
        if e:
            out.append(f'<a class="{css_class}" href="#{esc(e["slug"])}">{esc(e["label"])}</a>')
        else:
            slug = str(u).rsplit("/", 1)[-1]
            out.append(f'<span class="{css_class} pill-undefined" title="referenced in source but not defined">{esc(slug)}</span>')
    return " ".join(out)


def ext_links(uris):
    out = []
    for u in uris:
        out.append(f'<a class="pill pill-ext" href="{esc(u)}" target="_blank" rel="noopener">{esc(u)}</a>')
    return " ".join(out)


def build_tree(all_entries, entry_by_uri):
    children = {e["uri"]: set() for e in all_entries}
    for e in all_entries:
        for n in e["narrower"]:
            children[e["uri"]].add(n)
        for parent in e["broader"]:
            children.setdefault(parent, set()).add(e["uri"])

    def render(uri, seen):
        e = entry_by_uri.get(uri)
        if e is None or uri in seen:
            return ""
        seen = seen | {uri}
        kids = sorted(children.get(uri, []), key=lambda u: entry_by_uri[u]["label"] if u in entry_by_uri else "")
        kid_html = "".join(render(k, seen) for k in kids if k in entry_by_uri)
        li = f'<li><a href="#{esc(e["slug"])}">{esc(e["label"])}</a>'
        if kid_html:
            li += f'<ul>{kid_html}</ul>'
        li += "</li>"
        return li

    tops = [e for e in all_entries if e["is_top"]]
    items = "".join(render(e["uri"], set()) for e in tops)
    return f"<ul class='tree'>{items}</ul>"


def write_html(all_entries, entry_by_uri, unresolved):
    by_source = {}
    for e in all_entries:
        by_source.setdefault(e["source"], []).append(e)

    nav_sections = []
    for source, items in by_source.items():
        links = "".join(f'<li><a href="#{esc(e["slug"])}">{esc(e["label"])}</a></li>' for e in items)
        nav_sections.append(f'<h3>{esc(source)}</h3><ul>{links}</ul>')

    cards = []
    for source, items in by_source.items():
        cards.append(f'<h2 class="source-heading" id="{esc(slugify(source))}">{esc(source)}</h2>')
        for e in items:
            body = e["body"]
            alt = as_list(body.get("skos:altLabel"))
            definition = body.get("skos:definition", "")
            note = body.get("skos:note")
            examples = as_list(body.get("skos:example"))
            exact = as_list(body.get("skos:exactMatch"))
            related_match = as_list(body.get("skos:relatedMatch"))

            badges = f'<span class="badge">{esc(source)}</span>'
            if e["is_top"]:
                badges += '<span class="badge badge-top">Top concept</span>'

            rel_rows = ""
            if e["broader"]:
                rel_rows += f'<div class="rel-row"><span class="rel-label">Broader</span>{pill_links(e["broader"], entry_by_uri)}</div>'
            if e["narrower"]:
                rel_rows += f'<div class="rel-row"><span class="rel-label">Narrower</span>{pill_links(e["narrower"], entry_by_uri)}</div>'
            if e["related"]:
                rel_rows += f'<div class="rel-row"><span class="rel-label">Related</span>{pill_links(e["related"], entry_by_uri)}</div>'
            if exact:
                rel_rows += f'<div class="rel-row"><span class="rel-label">Exact match</span>{ext_links(exact)}</div>'
            if related_match:
                rel_rows += f'<div class="rel-row"><span class="rel-label">Related match</span>{ext_links(related_match)}</div>'

            alt_html = f'<div class="alt-labels">Also known as: {esc(", ".join(alt))}</div>' if alt else ""
            note_html = f'<aside class="scope-note">{esc(note)}</aside>' if note else ""
            examples_html = ""
            if examples:
                ex_items = "".join(f"<li>{esc(x)}</li>" for x in examples)
                examples_html = f'<details class="examples"><summary>Examples ({len(examples)})</summary><ul>{ex_items}</ul></details>'

            cards.append(f"""
<article class="concept" id="{esc(e['slug'])}">
  <h3>{esc(e['label'])} {badges}</h3>
  {alt_html}
  <p class="definition">{esc(definition)}</p>
  {note_html}
  {rel_rows}
  {examples_html}
  <div class="uri"><a href="{esc(e['uri'])}">{esc(e['uri'])}</a></div>
</article>""")

    tree_html = build_tree(all_entries, entry_by_uri)

    unresolved_html = ""
    if unresolved:
        items = "".join(f"<li>{esc(u)}</li>" for u in sorted(unresolved))
        unresolved_html = f"""
<section class="callout callout-warn">
  <h3>Dangling references found in source data</h3>
  <p>The following labels are referenced via <code>skos:broader</code>, <code>skos:narrower</code>,
  or <code>skos:related</code> but have no corresponding entry in <code>source/*.yml</code>.
  They render below as unlinked tags. Fix by adding the missing concept or correcting the label in the source YAML.</p>
  <ul>{items}</ul>
</section>"""

    page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(VOCAB_TITLE)}</title>
<link rel="alternate" type="text/turtle" href="tamu-dc-types.ttl">
<link rel="alternate" type="application/rdf+xml" href="tamu-dc-types.rdf">
<style>
  :root {{
    --maroon: #500000;
    --maroon-dark: #3a0000;
    --bg: #ffffff;
    --bg-alt: #f7f5f3;
    --text: #222;
    --muted: #666;
    --border: #e2ddd8;
    --pill-bg: #f1ece7;
    --pill-text: #3a0000;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; font-family: "Helvetica Neue", Arial, sans-serif; color: var(--text); background: var(--bg);
    line-height: 1.55;
  }}
  header.site {{
    background: linear-gradient(135deg, var(--maroon), var(--maroon-dark));
    color: #fff; padding: 2.5rem 1.5rem 2rem;
  }}
  header.site h1 {{ margin: 0 0 .25rem; font-size: 1.8rem; }}
  header.site p {{ margin: .25rem 0; color: #f1e4e4; max-width: 60rem; }}
  .downloads {{ margin-top: 1.25rem; display: flex; gap: .75rem; flex-wrap: wrap; }}
  .downloads a {{
    background: #fff; color: var(--maroon-dark); text-decoration: none; padding: .5rem 1rem;
    border-radius: 6px; font-weight: 600; font-size: .9rem;
  }}
  .downloads a:hover {{ background: #f1e4e4; }}
  .layout {{ display: flex; max-width: 1200px; margin: 0 auto; }}
  nav.toc {{
    width: 240px; flex: 0 0 240px; padding: 1.5rem 1rem; border-right: 1px solid var(--border);
    position: sticky; top: 0; align-self: flex-start; max-height: 100vh; overflow-y: auto;
    background: var(--bg-alt);
  }}
  nav.toc h2 {{ font-size: .85rem; text-transform: uppercase; letter-spacing: .04em; color: var(--muted); }}
  nav.toc h3 {{ font-size: .8rem; text-transform: uppercase; color: var(--maroon-dark); margin: 1rem 0 .25rem; }}
  nav.toc ul {{ list-style: none; margin: 0 0 .5rem; padding: 0; }}
  nav.toc li a {{ display: block; padding: .2rem 0; color: var(--text); text-decoration: none; font-size: .9rem; }}
  nav.toc li a:hover {{ color: var(--maroon); text-decoration: underline; }}
  main {{ flex: 1; padding: 1.5rem 2rem 4rem; min-width: 0; }}
  section.intro {{ max-width: 48rem; margin-bottom: 2rem; }}
  section.intro h2 {{ margin-top: 2rem; }}
  pre {{ background: #2b2b2b; color: #eee; padding: 1rem; border-radius: 6px; overflow-x: auto; font-size: .85rem; }}
  code {{ background: var(--pill-bg); padding: .1rem .3rem; border-radius: 3px; font-size: .9em; }}
  pre code {{ background: none; padding: 0; }}
  .callout {{ border: 1px solid var(--border); border-left: 4px solid var(--maroon); background: var(--bg-alt);
    padding: 1rem 1.25rem; border-radius: 6px; margin: 1.5rem 0; max-width: 48rem; }}
  .callout-warn {{ border-left-color: #b45309; }}
  .tree {{ list-style: none; padding-left: 1rem; }}
  .tree ul {{ list-style: none; padding-left: 1.25rem; border-left: 1px dashed var(--border); }}
  .tree li {{ margin: .15rem 0; }}
  .tree a {{ text-decoration: none; color: var(--maroon-dark); }}
  .tree a:hover {{ text-decoration: underline; }}
  h2.source-heading {{ margin-top: 3rem; padding-top: 1rem; border-top: 2px solid var(--border); color: var(--maroon-dark); }}
  article.concept {{
    border: 1px solid var(--border); border-radius: 8px; padding: 1.25rem 1.5rem; margin: 1.25rem 0;
    scroll-margin-top: 1rem; background: #fff;
  }}
  article.concept:target {{ border-color: var(--maroon); box-shadow: 0 0 0 2px rgba(80,0,0,.15); }}
  article.concept h3 {{ margin: 0 0 .4rem; display: flex; align-items: center; gap: .5rem; flex-wrap: wrap; font-size: 1.15rem; }}
  .badge {{ font-size: .68rem; text-transform: uppercase; letter-spacing: .03em; background: var(--pill-bg);
    color: var(--pill-text); padding: .15rem .5rem; border-radius: 999px; font-weight: 600; }}
  .badge-top {{ background: var(--maroon); color: #fff; }}
  .alt-labels {{ color: var(--muted); font-size: .85rem; margin-bottom: .5rem; }}
  .definition {{ margin: .4rem 0 .75rem; }}
  .scope-note {{ font-size: .88rem; color: var(--muted); border-left: 3px solid var(--border); padding-left: .75rem; margin: .5rem 0; }}
  .rel-row {{ margin: .35rem 0; font-size: .9rem; display: flex; gap: .5rem; flex-wrap: wrap; align-items: baseline; }}
  .rel-label {{ color: var(--muted); font-size: .78rem; text-transform: uppercase; letter-spacing: .03em; min-width: 6.5rem; }}
  .pill {{ background: var(--pill-bg); color: var(--pill-text); padding: .15rem .55rem; border-radius: 999px;
    text-decoration: none; font-size: .85rem; }}
  .pill:hover {{ background: #e6dcd4; }}
  .pill-ext {{ background: #eef2f6; color: #1f4b6e; max-width: 28rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; display: inline-block; }}
  .pill-undefined {{ background: #fde8e8; color: #9b1c1c; }}
  details.examples summary {{ cursor: pointer; font-size: .85rem; color: var(--maroon-dark); margin-top: .5rem; }}
  details.examples ul {{ margin: .4rem 0 0; }}
  .uri {{ margin-top: .75rem; font-size: .78rem; }}
  .uri a {{ color: var(--muted); text-decoration: none; }}
  .uri a:hover {{ text-decoration: underline; }}
  footer {{ text-align: center; color: var(--muted); font-size: .85rem; padding: 2rem; border-top: 1px solid var(--border); }}
  @media (max-width: 800px) {{
    .layout {{ flex-direction: column; }}
    nav.toc {{ width: auto; flex: none; position: static; max-height: none; border-right: none; border-bottom: 1px solid var(--border); }}
    main {{ padding: 1.25rem; }}
  }}
</style>
</head>
<body>
<header class="site">
  <h1>{esc(VOCAB_TITLE)}</h1>
  <p>A SKOS vocabulary of digital object and browse/search types used across Texas A&amp;M University
     Libraries digital collections (Archipelago). Published by Texas A&amp;M University Libraries.</p>
  <p><strong>Namespace:</strong> <code>{esc(BASE)}</code></p>
  <div class="downloads">
    <a href="tamu-dc-types.ttl">Download Turtle (.ttl)</a>
    <a href="tamu-dc-types.rdf">Download RDF/XML (.rdf)</a>
    <a href="https://github.com/tamulib-dc-labs/tamu-dc-ontology">View source on GitHub</a>
  </div>
</header>
<div class="layout">
  <nav class="toc">
    <h2>Contents</h2>
    {''.join(nav_sections)}
  </nav>
  <main>
    <section class="intro">
      <h2>About this vocabulary</h2>
      <p>This vocabulary combines two source files maintained by TAMU Libraries:</p>
      <ul>
        <li><strong>ADO Types</strong> &mdash; the underlying Archipelago Digital Object (ADO) types used to
            model digital objects in the repository (e.g. <em>Image ADO</em>, <em>Map ADO</em>, <em>Book ADO</em>).</li>
        <li><strong>Browse/Search Types</strong> &mdash; the public-facing genre/format terms end users browse
            and search by (e.g. <em>Postcard</em>, <em>Correspondence</em>, <em>Photograph</em>), related back
            to the ADO type(s) that implement them.</li>
      </ul>
      <p>Each concept is identified by a dereferenceable URI under <code>{esc(BASE)}</code>. Content
         negotiation is handled via <a href="https://w3id.org">w3id.org</a>, which redirects requests for a
         concept URI to this GitHub Pages site, choosing a representation based on the client's
         <code>Accept</code> header:</p>
      <pre><code># human-readable page
curl -L -H "Accept: text/html" {esc(BASE)}

# Turtle
curl -L -H "Accept: text/turtle" {esc(BASE)}

# RDF/XML
curl -L -H "Accept: application/rdf+xml" {esc(BASE)}</code></pre>

    </section>

    {unresolved_html}

    <section class="intro">
      <h2>Concept hierarchy</h2>
      {tree_html}
    </section>

    {''.join(cards)}
  </main>
</div>
<footer>
  
</footer>
</body>
</html>
"""
    out_path = REPO_ROOT / "index.html"
    out_path.write_text(page, encoding="utf-8")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
