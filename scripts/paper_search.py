#!/usr/bin/env python3
"""Batch arXiv + Semantic Scholar paper search with rate limiting.

Searches queries from docs/paper_keywords.md.
Respects arXiv (~1 req/3s) and Semantic Scholar (~5 req/s) rate limits.
Downloads PDFs by default (--no-pdfs to skip). Groups PDFs by section/topic.
Uses tqdm progress bars throughout. Results grouped by low-level topic
within each group. Has auto-resume from checkpoint (--fresh to reset).
Category filter: cs.CL, cs.AI, cs.LG only (arXiv categories).

All HTTP calls have retry with exponential backoff (429/5xx/network errors).

Filters: year >= 2023 preferred, year >= 2021 tolerated (up to 10 total),
         citationCount > 10.

Usage:
  python scripts/paper_search.py --all
  python scripts/paper_search.py --groups A,B,C
  python scripts/paper_search.py --query "LLM document extraction" --max 20
  python scripts/paper_search.py --all --no-pdfs
  python scripts/paper_search.py --all --dry-run
  python scripts/paper_search.py --all --json
  python scripts/paper_search.py --all --fresh
"""

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

from tqdm import tqdm

NS = {'a': 'http://www.w3.org/2005/Atom'}

ARXIV_DELAY = 3
SS_DELAY = 5
PDF_DELAY = 3
MAX_RESULTS = 20
YEAR_PREFERRED = 2023
YEAR_TOLERATED = 2021
MIN_CITATIONS = 10
YEAR_TOLERANCE_QUOTA = 10
SS_RETRIES = 3
HTTP_RETRIES = 2
TOPIC_LABEL_MAX = 50

REPO_ROOT = Path(__file__).resolve().parent.parent
KEYWORDS_FILE = REPO_ROOT / "docs" / "paper_keywords.md"
FINDINGS_FILE = REPO_ROOT / "docs" / "paper_findings.md"
PDF_DIR = REPO_ROOT / "papers"
CHECKPOINT_FILE = REPO_ROOT / "scripts" / ".paper_search_state.json"
ARXIV_CATEGORIES = ["cs.CL", "cs.AI", "cs.LG"]

_last_arxiv = 0.0
_last_ss = 0.0
_last_pdf = 0.0


def rate_limit(delay, last):
    elapsed = time.time() - last
    if elapsed < delay:
        time.sleep(delay - elapsed)
    return time.time()


def http_get(url, headers=None):
    req = urllib.request.Request(
        url,
        headers=headers or {
            'User-Agent': 'PaperSearchBot/1.0 (mailto:research@example.com)'
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def search_arxiv(query, max_results=20, sort="relevance", retry=0):
    global _last_arxiv
    _last_arxiv = rate_limit(ARXIV_DELAY, _last_arxiv)

    cat_filter = '+OR+'.join(f'cat:{c}' for c in ARXIV_CATEGORIES)
    params = {
        'search_query': f'all:{urllib.parse.quote(query)}+AND+({cat_filter})',
        'max_results': str(max_results),
        'sortBy': sort,
        'sortOrder': 'descending',
    }
    url = "https://export.arxiv.org/api/query?" + "&".join(
        f"{k}={v}" for k, v in params.items()
    )

    try:
        data = http_get(url)
    except urllib.error.HTTPError as e:
        if e.code == 429 and retry < HTTP_RETRIES:
            wait = 3 * (retry + 1)
            tqdm.write(f"  [RETRY] arXiv 429, {wait}s")
            time.sleep(wait)
            return search_arxiv(query, max_results, sort, retry + 1)
        print(f"  [WARN] arXiv HTTP {e.code}, skipping")
        return []
    except Exception as e:
        if retry < HTTP_RETRIES:
            wait = 3 * (retry + 1)
            tqdm.write(f"  [RETRY] arXiv error, {wait}s")
            time.sleep(wait)
            return search_arxiv(query, max_results, sort, retry + 1)
        print(f"  [WARN] arXiv error: {e}, skipping")
        return []

    root = ET.fromstring(data)
    entries = root.findall('a:entry', NS)

    papers = []
    for entry in entries:
        raw_id = entry.find('a:id', NS).text.strip()
        full_id = raw_id.split('/abs/')[-1]
        arxiv_id = full_id.split('v')[0]
        published = entry.find('a:published', NS).text[:10]
        year = int(published[:4])
        title = entry.find('a:title', NS).text.strip().replace('\n', ' ')
        authors = ', '.join(
            a.find('a:name', NS).text for a in entry.findall('a:author', NS)
        )
        summary = entry.find('a:summary', NS).text.strip().replace('\n', ' ')
        cats = ', '.join(c.get('term') for c in entry.findall('a:category', NS))

        if 'withdrawn' in summary.lower() or 'retracted' in summary.lower():
            continue

        papers.append({
            'arxiv_id': arxiv_id,
            'title': title,
            'authors': authors,
            'published': published,
            'year': year,
            'abstract': summary,
            'categories': cats,
            'url': f'https://arxiv.org/abs/{arxiv_id}',
            'pdf_url': f'https://arxiv.org/pdf/{arxiv_id}',
        })

    return papers


def get_citation_count(arxiv_id, retry=0):
    global _last_ss
    _last_ss = rate_limit(SS_DELAY, _last_ss)

    url = (
        f"https://api.semanticscholar.org/graph/v1/paper/arXiv:{arxiv_id}"
        "?fields=citationCount,year"
    )
    try:
        data = http_get(url, headers={'User-Agent': 'PaperSearchBot/1.0'})
        result = json.loads(data)
        return result.get('citationCount', 0), result.get('year')
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None, None
        if e.code == 429 and retry < SS_RETRIES:
            wait = 2 ** (retry + 1)
            tqdm.write(f"    [RETRY] SS 429, {wait}s")
            time.sleep(wait)
            return get_citation_count(arxiv_id, retry + 1)
        print(f"    [WARN] SS HTTP {e.code} for {arxiv_id}")
        return None, None
    except Exception as e:
        if retry < SS_RETRIES:
            wait = 2 ** retry or 1
            tqdm.write(f"    [RETRY] SS err")
            time.sleep(wait)
            return get_citation_count(arxiv_id, retry + 1)
        print(f"    [WARN] SS error for {arxiv_id}: {e}")
        return None, None


def download_pdf(arxiv_id, pdf_dir, retry=0):
    global _last_pdf
    _last_pdf = rate_limit(PDF_DELAY, _last_pdf)

    url = f"https://arxiv.org/pdf/{arxiv_id}"
    pdf_path = pdf_dir / f"{arxiv_id}.pdf"
    if pdf_path.exists():
        return True

    try:
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        data = http_get(url, headers={'User-Agent': 'PaperSearchBot/1.0'})
        pdf_path.write_bytes(data)
        return True
    except Exception as e:
        if retry < HTTP_RETRIES:
            wait = 3 * (retry + 1)
            tqdm.write(f"    [RETRY] PDF fail {arxiv_id}, {wait}s")
            time.sleep(wait)
            return download_pdf(arxiv_id, pdf_dir, retry + 1)
        tqdm.write(f"    [WARN] PDF failed {arxiv_id}: {e}")
        return False


def parse_keywords(filepath):
    queries = []
    current_group = None
    current_group_name = None
    current_section = None
    current_section_name = None
    in_exploratory = False

    for line in filepath.read_text().splitlines():
        g = re.match(r'^## Group (\w+):\s*(.*)', line)
        if g:
            current_group = g.group(1)
            current_group_name = g.group(2).strip()
            current_section = None
            current_section_name = None
            in_exploratory = False
            continue
        s = re.match(r'^### (\w+\d+)\s*[—\-–]\s*(Core|Exploratory)\s*(.*)', line)
        if s:
            current_section = s.group(1)
            trail = s.group(3).strip()
            current_section_name = f"{s.group(2)} Queries" + (f" {trail}" if trail else "")
            in_exploratory = (s.group(2) == 'Exploratory')
            continue
        m = re.match(r'^- `(.+?)`', line)
        if m and current_section:
            queries.append({
                'group': current_group,
                'group_name': current_group_name or '',
                'section': current_section,
                'section_name': current_section_name or '',
                'query': m.group(1),
                'type': 'exploratory' if in_exploratory else 'core',
                'topic_label': None,
            })
        j = re.match(r'^\s+→ Justifikasi:\s*(.*)', line)
        if j and queries and queries[-1]['topic_label'] is None:
            label = j.group(1).strip()
            queries[-1]['topic_label'] = label[:TOPIC_LABEL_MAX]

    for q in queries:
        if q['topic_label'] is None:
            words = q['query'].split()
            q['topic_label'] = ' '.join(words[:4])[:TOPIC_LABEL_MAX]

    return queries


def passes_year_filter(year, tolerance_used):
    if year >= YEAR_PREFERRED:
        return True
    if year >= YEAR_TOLERATED and tolerance_used < YEAR_TOLERANCE_QUOTA:
        return True
    return False


def save_checkpoint(state):
    with open(CHECKPOINT_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def load_checkpoint():
    if CHECKPOINT_FILE.exists():
        with open(CHECKPOINT_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None


def cleanup_checkpoint():
    if CHECKPOINT_FILE.exists():
        CHECKPOINT_FILE.unlink()


def main():
    global ARXIV_DELAY, SS_DELAY, MAX_RESULTS, MIN_CITATIONS

    parser = argparse.ArgumentParser(description='Batch arXiv paper search')
    parser.add_argument('--all', action='store_true', help='Search all queries')
    parser.add_argument(
        '--groups', type=str, help='Comma-separated groups (e.g. A,B,C)'
    )
    parser.add_argument(
        '--query', type=str, help='Single query (bypass keywords file)'
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='Print queries without searching'
    )
    parser.add_argument(
        '--arxiv-delay', type=int, default=ARXIV_DELAY,
        help=f'Seconds between arXiv requests (default: {ARXIV_DELAY})'
    )
    parser.add_argument(
        '--ss-delay', type=int, default=SS_DELAY,
        help=f'Seconds between SS requests (default: {SS_DELAY})'
    )
    parser.add_argument(
        '--max', type=int, default=MAX_RESULTS,
        help=f'Max results per query (default: {MAX_RESULTS})'
    )
    parser.add_argument(
        '--min-citations', type=int, default=MIN_CITATIONS,
        help=f'Minimum citations (default: {MIN_CITATIONS})'
    )
    parser.add_argument(
        '--no-pdfs', action='store_true',
        help='Skip PDF downloads (default: download ON)'
    )
    parser.add_argument(
        '--pdf-dir', type=str, default=str(PDF_DIR),
        help=f'PDF output directory (default: {PDF_DIR})'
    )
    parser.add_argument(
        '--fresh', action='store_true',
        help='Ignore checkpoint and start fresh'
    )
    parser.add_argument(
        '--json', action='store_true', dest='json_output',
        help='Also write findings as JSON (addon, .md always written)'
    )
    args = parser.parse_args()

    ARXIV_DELAY = args.arxiv_delay
    SS_DELAY = args.ss_delay
    MAX_RESULTS = args.max
    MIN_CITATIONS = args.min_citations

    if args.query:
        queries = [{
            'group': '', 'group_name': '',
            'section': 'CUSTOM', 'section_name': 'Custom Query',
            'query': args.query, 'type': 'core', 'topic_label': None,
        }]
    elif args.groups:
        target = set(args.groups.upper().split(','))
        queries = [
            q for q in parse_keywords(KEYWORDS_FILE)
            if q['group'] in target
        ]
    elif args.all:
        queries = parse_keywords(KEYWORDS_FILE)
    else:
        parser.print_help()
        sys.exit(1)

    if not queries:
        print("No queries found.")
        sys.exit(1)

    core_queries = [q for q in queries if q['type'] == 'core']
    exploratory_queries = [q for q in queries if q['type'] == 'exploratory']
    total_queries = len(core_queries) + len(exploratory_queries)

    print(f"Queries: {len(core_queries)} core + {len(exploratory_queries)} exploratory = {total_queries}")
    print(f"Rate limits: arXiv {ARXIV_DELAY}s / SS {SS_DELAY}s (retries: SS {SS_RETRIES}x, others {HTTP_RETRIES}x)")
    print(f"Year filter: >= {YEAR_PREFERRED} preferred, >= {YEAR_TOLERATED} tolerated (≤{YEAR_TOLERANCE_QUOTA})")
    print(f"Citation filter: > {MIN_CITATIONS}")

    if args.dry_run:
        for q in queries:
            tag = "[E]" if q['type'] == 'exploratory' else "[C]"
            label = q.get('topic_label', '')
            print(f"  {tag} [{q['group']}/{q['section']}] {q['query']}")
            if label:
                print(f"       Topic: {label}")
        print(f"\nTotal: {len(queries)} queries")
        return

    all_results = {}
    global_tolerance_used = 0
    processed = 0
    seen_groups = {}

    checkpoint = None if args.fresh else load_checkpoint()
    if checkpoint:
        all_results = checkpoint['all_results']
        global_tolerance_used = checkpoint['global_tolerance_used']
        completed = checkpoint.get('completed_queries', [])
        paper_to_groups = {k: set(v) for k, v in checkpoint.get('paper_to_groups', {}).items()}
        queries = [
            q for q in queries
            if {'group': q['group'], 'section': q['section'], 'query': q['query']} not in completed
        ]
        processed = checkpoint.get('progress', {}).get('processed', 0)
        print(f"\n  Checkpoint found — resuming from query {processed + 1}/{total_queries}")
        print(f"  ({len(completed)} queries already done, {len(queries)} remaining)")
        if not queries:
            print("  All queries already completed. Use --fresh to re-run.")
    else:
        paper_to_groups = {}
        checkpoint = None

    for q in queries:
        q['topic_label'] = q.get('topic_label') or ' '.join(q['query'].split()[:4])[:TOPIC_LABEL_MAX]

    for q in queries:
        processed += 1
        gk = f"Group {q['group'] or 'Custom'}"
        sk = f"{q['section']} — {q['section_name']}"
        tag = "[E]" if q['type'] == 'exploratory' else "[C]"

        print()
        print(f"{'='*60}")
        print(f"  [{processed}/{total_queries}] {tag} {q['group']}/{q['section']}")
        print(f"  Query: {q['query']}")
        print(f"{'='*60}")

        papers = search_arxiv(q['query'], max_results=MAX_RESULTS)
        if not papers:
            print("  → No results")
            continue
        print(f"  arXiv: {len(papers)} papers")

        year_filtered = []
        tol_used_here = 0
        for p in papers:
            if passes_year_filter(p['year'], global_tolerance_used + tol_used_here):
                year_filtered.append(p)
                if p['year'] < YEAR_PREFERRED:
                    tol_used_here += 1
        global_tolerance_used += tol_used_here
        print(f"  Year filter: {len(year_filtered)}/{len(papers)} kept (tolerance used: {tol_used_here})")

        for p in tqdm(year_filtered, desc="  SS citations", unit=" paper", leave=False):
            citations, ss_year = get_citation_count(p['arxiv_id'])
            p['citationCount'] = citations
            p['ss_year'] = ss_year

        cited = [
            p for p in year_filtered
            if p.get('citationCount') is not None and p['citationCount'] > MIN_CITATIONS
        ]
        recent_uncited = [
            p for p in year_filtered
            if p.get('citationCount') is None and p['year'] >= YEAR_PREFERRED
        ]
        final = cited + recent_uncited
        print(f"  Citation filter: {len(final)} pass ({len(cited)} cited, {len(recent_uncited)} recent uncited)")

        if final:
            for i, p in enumerate(final[:5], 1):
                c = p.get('citationCount', '?')
                print(f"  {i}. [{p['arxiv_id']}] ({p['year']}, cit:{c}) {p['title'][:90]}")

        if not args.no_pdfs and final:
            section_dir = f"{q['section']}__{q['section_name'].replace(' ', '_')}"[:80]
            section_pdf_dir = Path(args.pdf_dir) / f"group_{q['group'] or 'Custom'}" / section_dir
            for p in tqdm(final, desc="  PDF download", unit=" pdf", leave=False):
                ok = download_pdf(p['arxiv_id'], section_pdf_dir)
                if not ok:
                    tqdm.write(f"    [WARN] Failed PDF: {p['arxiv_id']}")

        all_results.setdefault(gk, {})
        all_results[gk].setdefault(sk, {'papers': {}, 'group_name': q['group_name'] or ''})
        section_dict = all_results[gk][sk]['papers']
        for p in final:
            pid = p['arxiv_id']
            paper_to_groups.setdefault(pid, set()).add(gk)
            if pid in section_dict:
                existing_label = q.get('topic_label', '')
                if existing_label and existing_label not in section_dict[pid].get('found_by', []):
                    section_dict[pid].setdefault('found_by', []).append(existing_label)
                if gk not in section_dict[pid].setdefault('also_in_groups', []):
                    section_dict[pid]['also_in_groups'].append(gk)
            else:
                p['found_by'] = [q.get('topic_label', '')] if q.get('topic_label') else []
                p['also_in_groups'] = []
                section_dict[pid] = p

        seen_groups.setdefault(gk, q['group_name'] or '')

        # --- checkpoint ---
        cp = {
            'all_results': all_results,
            'global_tolerance_used': global_tolerance_used,
            'completed_queries': checkpoint.get('completed_queries', []) if checkpoint else [],
            'paper_to_groups': {k: list(v) for k, v in paper_to_groups.items()},
            'progress': {'total': total_queries, 'processed': processed},
        }
        cp_entry = {'group': q['group'], 'section': q['section'], 'query': q['query']}
        if cp_entry not in cp['completed_queries']:
            cp['completed_queries'].append(cp_entry)
        save_checkpoint(cp)
        checkpoint = cp

    print()
    print(f"{'='*60}")
    print(f"  DONE — processed {processed}/{total_queries} queries")
    print(f"{'='*60}")

    # Cross-group tags: fill also_in_groups for papers found in multiple groups
    for pid, groups in paper_to_groups.items():
        if len(groups) > 1:
            for gk in groups:
                for sk in all_results.get(gk, {}):
                    section = all_results[gk][sk]
                    if pid in section.get('papers', {}):
                        section['papers'][pid]['also_in_groups'] = sorted(groups - {gk})

    FINDINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if FINDINGS_FILE.exists():
        FINDINGS_FILE.write_text("")

    with open(FINDINGS_FILE, 'w', encoding='utf-8') as f:
        f.write("# Paper Findings — Certificate Autofill\n\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Queries: {total_queries} ({len(core_queries)} core, {len(exploratory_queries)} exploratory)\n")
        f.write(f"Filters: year>={YEAR_TOLERATED} (pref>={YEAR_PREFERRED}), citations>{MIN_CITATIONS}\n\n")

        total_unique = 0
        for gk in sorted(all_results.keys()):
            sections = all_results[gk]
            if not sections:
                continue

            group_desc = seen_groups.get(gk, '')
            header = f"## {gk}"
            if group_desc:
                header += f" — {group_desc}"
            f.write(header + "\n\n")

            for sk in sorted(sections.keys()):
                section = sections[sk]
                papers_dict = section['papers']
                group_name = section.get('group_name', '')

                if not papers_dict:
                    continue

                papers_list = list(papers_dict.values())
                papers_list.sort(key=lambda x: x.get('citationCount') or 0, reverse=True)
                total_unique += len(papers_list)

                f.write(f"### {sk} ({len(papers_list)} papers)\n")
                all_topics = set()
                for p in papers_list:
                    for t in p.get('found_by', []):
                        if t:
                            all_topics.add(t)
                if all_topics:
                    f.write(f"*Topics: {', '.join(sorted(all_topics))}*\n\n")

                f.write("| # | Paper | Y | Cit | Topic | Cross |\n")
                f.write("|---|-------|---|-----|-------|-------|\n")
                for i, p in enumerate(papers_list, 1):
                    title_esc = p['title'].replace('|', '\\|')[:100]
                    c = p.get('citationCount', 'N/A')
                    if c is None:
                        c = '?'
                    topic = (p.get('found_by') or [''])[0][:50]
                    cross = p.get('also_in_groups', [])
                    cross_str = ', '.join(sorted(cross))[:30] if cross else ''
                    f.write(
                        f"| {i} | [{p['arxiv_id']}]({p['url']}) {title_esc} "
                        f"| {p['year'] % 100} | {c} | {topic} | {cross_str} |\n"
                    )

                sk_short = sk.split(' — ')[0]
                f.write(f"\n### {sk_short} — Abstracts\n\n")
                for i, p in enumerate(papers_list, 1):
                    abstract = p['abstract'][:500]
                    if len(p['abstract']) > 500:
                        abstract += '...'
                    topic_tag = (p.get('found_by') or [''])[0][:30]
                    f.write(f"**{i}. [{p['arxiv_id']}]({p['url']})")
                    if topic_tag:
                        f.write(f" ({topic_tag})")
                    f.write(f" — {p['title'][:120]}**\n")
                    f.write(f"> {abstract}\n\n")

            f.write("---\n\n")

        f.write(f"**Total papers collected: {total_unique}**\n")

    if args.json_output:
        json_path = FINDINGS_FILE.with_suffix('.json')
        json_out = {
            'generated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'filters': {
                'year_min': YEAR_TOLERATED,
                'year_preferred': YEAR_PREFERRED,
                'min_citations': MIN_CITATIONS,
            },
            'total_papers': total_unique,
            'groups': {},
        }
        for gk in sorted(all_results.keys()):
            sections = all_results[gk]
            if not sections:
                continue
            group_data = {'description': seen_groups.get(gk, ''), 'sections': {}}
            for sk in sorted(sections.keys()):
                papers_dict = sections[sk]['papers']
                if not papers_dict:
                    continue
                papers_list = sorted(
                    papers_dict.values(),
                    key=lambda x: x.get('citationCount') or 0,
                    reverse=True,
                )
                group_data['sections'][sk] = []
                for p in papers_list:
                    group_data['sections'][sk].append({
                        'arxiv_id': p['arxiv_id'],
                        'title': p['title'][:200],
                        'year': p['year'],
                        'citation_count': p.get('citationCount'),
                        'categories': p.get('categories', ''),
                        'found_in_queries': p.get('found_by', []),
                        'also_in_groups': p.get('also_in_groups', []),
                        'url': p['url'],
                        'abstract': p['abstract'][:1000],
                    })
            json_out['groups'][gk] = group_data
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(json_out, f, indent=2, ensure_ascii=False)
        print(f"       → {json_path}")

    cleanup_checkpoint()

    print(f"\nResults → {FINDINGS_FILE}")
    if args.json_output:
        print(f"       → {FINDINGS_FILE.with_suffix('.json')}")
    print(f"Total unique papers: {total_unique}")
    if not args.no_pdfs:
        pdf_dir_used = Path(args.pdf_dir)
        count = sum(1 for d in pdf_dir_used.glob("group_*") for _ in d.rglob("*.pdf"))
        print(f"PDFs downloaded: {count} → {pdf_dir_used}")
    if not args.fresh:
        cleanup_checkpoint()


if __name__ == '__main__':
    main()
