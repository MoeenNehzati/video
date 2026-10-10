#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import re
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from scripts.project_runtime import add_config_argument, data_path, fresh_output, load_project


_DUCKDUCKGO_BLOCKED = False


def _normalize_for_match(s: str) -> str:
    s = (s or "").strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\\s+", " ", s).strip()


def _title_tokens(title: str) -> list[str]:
    norm = _normalize_for_match(title)
    toks = [t for t in norm.split(" ") if len(t) >= 3 and t not in {"the", "and", "for"}]
    return toks[:10]


def _read_file_prefix(path: Path, n: int = 16) -> bytes:
    with path.open("rb") as f:
        return f.read(n)


def _extract_xml_text_from_mxl(path: Path) -> str | None:
    try:
        with zipfile.ZipFile(path) as zf:
            # Similar heuristic to musicxml tooling: first xml not in META-INF.
            names = [n for n in zf.namelist() if n.lower().endswith(".xml") and not n.startswith("META-INF/")]
            if not names:
                return None
            data = zf.read(names[0])
    except Exception:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("utf-8", errors="ignore")


def _extract_ascii_strings(blob: bytes, min_len: int = 4) -> list[str]:
    out: list[str] = []
    cur: list[int] = []
    for b in blob:
        if 32 <= b <= 126:
            cur.append(b)
            continue
        if len(cur) >= min_len:
            out.append(bytes(cur).decode("ascii", errors="ignore"))
        cur = []
    if len(cur) >= min_len:
        out.append(bytes(cur).decode("ascii", errors="ignore"))
    return out


def _verify_downloaded_file(path: Path, title: str) -> list[str]:
    """
    Best-effort sanity checks:
    - file header matches expected container type (PDF/MIDI/ZIP/XML)
    - title tokens appear somewhere in embedded text/metadata (very weak, warning-only)
    """
    warns: list[str] = []
    toks = _title_tokens(title)
    if not toks:
        return warns

    suf = path.suffix.lower()
    prefix = _read_file_prefix(path, 8)

    if suf == ".pdf" and not prefix.startswith(b"%PDF"):
        warns.append("Downloaded .pdf does not start with %PDF header.")
        return warns

    if suf in {".mid", ".midi"}:
        if not prefix.startswith(b"MThd"):
            warns.append("Downloaded MIDI does not start with MThd header.")
            return warns
        blob = path.read_bytes()
        hay = _normalize_for_match(" ".join(_extract_ascii_strings(blob)))
        if not any(t in hay for t in toks):
            warns.append("Could not find title tokens in MIDI metadata strings (may still be correct).")
        return warns

    if suf in {".mxl", ".mscz"} or prefix.startswith(b"PK"):
        xml_text = _extract_xml_text_from_mxl(path)
        if xml_text is None:
            warns.append("Could not extract XML payload from zip container (MXL/MSCZ).")
            return warns
        hay = _normalize_for_match(xml_text)
        if not any(t in hay for t in toks):
            warns.append("Could not find title tokens in extracted XML text (may still be correct).")
        return warns

    if suf in {".xml", ".musicxml"}:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            warns.append("Could not read MusicXML as text for verification.")
            return warns
        if "<score-partwise" not in text and "<score-timewise" not in text:
            warns.append("MusicXML file does not look like score-partwise/score-timewise.")
        hay = _normalize_for_match(text)
        if not any(t in hay for t in toks):
            warns.append("Could not find title tokens in MusicXML text (may still be correct).")
        return warns

    # Unknown type: do nothing.
    return warns

@dataclass(frozen=True)
class Row:
    number: str
    title: str
    composer_or_origin: str
    status: str
    source: str
    url: str
    fmt: str


def _read_rows(csv_path: Path) -> list[Row]:
    rows: list[Row] = []
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            if not r:
                continue
            number = (r.get("number") or "").strip()
            title = (r.get("title") or "").strip()
            composer_or_origin = (r.get("composer_or_origin") or "").strip()
            status = (r.get("copyright_status") or "").strip()
            source = (r.get("source") or "").strip()
            url = (r.get("url") or "").strip()
            fmt = (r.get("format") or "").strip().upper() or "PDF"
            if number and not re.fullmatch(r"[A-Za-z0-9_-]+", number):
                raise ValueError(f"Unsafe song number {number!r}; use letters, digits, _ or -")
            if not (number and title and status and source and url):
                continue
            rows.append(
                Row(
                    number=number,
                    title=title,
                    composer_or_origin=composer_or_origin,
                    status=status,
                    source=source,
                    url=url,
                    fmt=fmt,
                )
            )
    return rows


def _download(url: str, out_path: Path, timeout_sec: float = 60.0) -> dict:
    out_path = fresh_output(out_path)
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; CodexCLI/1.0; +https://openai.com/)",
            "Accept": "*/*",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout_sec) as resp:  # nosec - expected for controlled URLs
        payload = resp.read()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(payload)
        return {'requested_url': url, 'final_url': resp.geturl() if hasattr(resp, 'geturl') else url,
                'retrieved_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
                'size_bytes': len(payload)}


def _nonempty(path: Path) -> bool:
    try:
        return path.exists() and path.stat().st_size > 0
    except OSError:
        return False


def _format_priority(fmt: str) -> int:
    f = (fmt or "").strip().lower()
    if f in {"musicxml", "xml", "musicxml.gz"}:
        return 0
    if f == "mxl":
        return 1
    if f == "mscz":
        return 2
    if f in {"mid", "midi"}:
        return 3
    if f == "pdf":
        return 4
    if f in {"lyrics", "txt"}:
        return 5
    return 9


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        if it in seen:
            continue
        seen.add(it)
        out.append(it)
    return out


def _is_direct_score_url(url: str) -> bool:
    u = url.lower()
    return any(u.endswith(ext) for ext in (".musicxml", ".xml", ".mxl", ".mscz", ".mid", ".midi", ".pdf"))


def _guess_format_from_url(url: str) -> str:
    u = url.lower()
    if u.endswith(".musicxml") or u.endswith(".xml"):
        return "MUSICXML"
    if u.endswith(".mxl"):
        return "MXL"
    if u.endswith(".mscz"):
        return "MSCZ"
    if u.endswith(".mid") or u.endswith(".midi"):
        return "MIDI"
    if u.endswith(".pdf"):
        return "PDF"
    if u.endswith(".txt"):
        return "LYRICS"
    return "UNKNOWN"


def _search_duckduckgo_urls(query: str, max_results: int = 10, timeout_sec: float = 30.0) -> list[str]:
    # Best-effort HTML scraping (no API key). May break if DDG changes.
    global _DUCKDUCKGO_BLOCKED  # noqa: PLW0603 - simple cross-call signal
    q = urllib.parse.quote_plus(query)
    url = f"https://duckduckgo.com/html/?q={q}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; CodexCLI/1.0; +https://openai.com/)",
            "Accept": "text/html,*/*",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:  # nosec - expected for controlled URLs
            html = resp.read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as e:
        # Some environments get blocked (403/429). Treat as "no results" rather than failing the run,
        # but record that it happened so callers can emit a clearer warning.
        if getattr(e, "code", None) in {403, 429}:
            _DUCKDUCKGO_BLOCKED = True
        return []
    except (urllib.error.URLError, TimeoutError, OSError):
        return []

    urls: list[str] = []
    for m in re.finditer(r'href="[^"]*uddg=([^"&]+)', html):
        try:
            u = urllib.parse.unquote(m.group(1))
        except Exception:
            continue
        if not u.startswith(("http://", "https://")):
            continue
        urls.append(u)
        if len(urls) >= max_results:
            break
    return _dedupe_preserve_order(urls)


def _candidate_urls_for_song(title: str, max_candidates: int) -> list[tuple[str, str]]:
    # Returns list of (fmt, url) in preference order.
    queries = [
        f"\"{title}\" filetype:musicxml",
        f"\"{title}\" filetype:mxl",
        f"\"{title}\" filetype:mscz",
        f"\"{title}\" filetype:mid",
        f"\"{title}\" filetype:midi",
        f"\"{title}\" filetype:pdf",
        f"\"{title}\" musicxml",
        f"\"{title}\" mxl",
        f"\"{title}\" mscz",
        f"\"{title}\" midi",
        f"\"{title}\" sheet music pdf",
        f"\"{title}\" noter pdf",
        f"\"{title}\" site:svensktvisarkiv.se pdf",
        f"\"{title}\" site:imslp.org pdf",
        f"\"{title}\" site:imslp.org mxl",
        f"\"{title}\" site:commons.wikimedia.org filetype:mid",
        f"\"{title}\" site:commons.wikimedia.org filetype:pdf",
        f"\"{title}\" site:archive.org pdf",
        f"\"{title}\" site:arkivkopia.se pdf",
        f"\"{title}\" site:runeberg.org pdf",
        f"\"{title}\" site:musopen.org sheet music",
        f"\"{title}\" site:openscore.cc musicxml",
        f"\"{title}\" site:mutopiaproject.org midi",
        f"\"{title}\" site:cpdl.org pdf",
        f"\"{title}\" site:hymnary.org musicxml",
        f"\"{title}\" site:mamalisa.com midi",
        f"\"{title}\" site:github.com musicxml",
        f"\"{title}\" site:github.com mxl",
        f"\"{title}\" site:github.com mscz",
        f"\"{title}\" site:github.com mid",
    ]
    gathered: list[str] = []
    for q in queries:
        gathered.extend(_search_duckduckgo_urls(q, max_results=10))
    gathered = _dedupe_preserve_order(gathered)
    direct = [u for u in gathered if _is_direct_score_url(u)]

    scored: list[tuple[int, str, str]] = []
    for u in direct:
        fmt = _guess_format_from_url(u)
        scored.append((_format_priority(fmt), fmt, u))
    scored.sort(key=lambda t: t[0])
    out: list[tuple[str, str]] = []
    for _p, fmt, u in scored:
        out.append((fmt, u))
        if len(out) >= max_candidates:
            break
    return out


def _strip_html_to_text(html: str) -> str:
    # Very lightweight cleanup: remove tags, keep some line breaks.
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"(?is)<br\\s*/?>", "\n", text)
    text = re.sub(r"(?is)</p\\s*>", "\n\n", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"[ \\t\\r\\f\\v]+", " ", text)
    text = re.sub(r"\\n{3,}", "\n\n", text)
    return text.strip()


def _mediawiki_title_variants(title: str) -> list[str]:
    # MediaWiki titles use underscores for spaces and preserve diacritics.
    base = title.strip().replace(" ", "_")
    if not base:
        return []
    translit = (
        base.replace("å", "a")
        .replace("ä", "a")
        .replace("ö", "o")
        .replace("Å", "A")
        .replace("Ä", "A")
        .replace("Ö", "O")
    )
    out = [base]
    if translit != base:
        out.append(translit)
    return out


def _candidate_lyric_urls_for_song(title: str) -> list[str]:
    # A few deterministic sources that often work for Swedish children's songs.
    candidates: list[str] = []
    for t in _mediawiki_title_variants(title):
        candidates.append(f"https://sv.wikisource.org/wiki/{urllib.parse.quote(t)}?action=raw")
        candidates.append(f"https://sv.wikipedia.org/wiki/{urllib.parse.quote(t)}?action=raw")
        candidates.append(f"https://sv.wikisource.org/wiki/{urllib.parse.quote(t)}")
        candidates.append(f"https://sv.wikipedia.org/wiki/{urllib.parse.quote(t)}")
    return candidates


def _strip_mediawiki_markup(text: str) -> str:
    # Minimal "good enough" cleanup for wiki raw text.
    # Keep it conservative: remove templates/refs/tables/files/categories and most formatting.
    text = re.sub(r"(?s)<!--.*?-->", " ", text)
    text = re.sub(r"(?s)<ref[^>]*>.*?</ref>", " ", text)
    text = re.sub(r"(?s)<ref[^/]*/>", " ", text)
    text = re.sub(r"(?s)\{\{.*?\}\}", " ", text)
    text = re.sub(r"(?m)^\s*\|.*$", " ", text)  # tables
    text = re.sub(r"(?m)^\s*\{\|.*$", " ", text)
    text = re.sub(r"(?m)^\s*\|\}.*$", " ", text)
    text = re.sub(r"(?mi)^\s*\[\[(Category|Fil|File):.*?\]\]\s*$", " ", text)
    # Replace MediaWiki links: [[Page]] or [[Page|Label]] -> Label (or Page).
    text = re.sub(r"\[\[(?:[^\]\|]*\|)?([^\]]+)\]\]", r"\1", text)
    text = re.sub(r"(?i)</?poem\s*>", "", text)
    text = re.sub(r"(?mi)^\s*kategori\s*:\s*.*$", " ", text)
    text = re.sub(r"(?m)^\s*\}+\s*$", " ", text)
    text = re.sub(r"''+", "", text)  # bold/italic markers
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _strip_stanza_numbers(text: str) -> str:
    # Remove common stanza numbering styles while preserving blank lines.
    lines: list[str] = []
    for raw in text.splitlines():
        s = raw.strip()
        if re.fullmatch(r"(\(?\d{1,2}\)?[.)]?|vers\s+\d{1,2}[.:]?)", s, flags=re.IGNORECASE):
            continue
        lines.append(raw)
    return "\n".join(lines)


def _extract_swedish_block(text: str) -> str | None:
    # Heuristic extractor for pages that include many languages (e.g. Brother Jakob).
    # Expect a "Svenska" marker followed by indented lyric lines (often prefixed with ":" or "::").
    lines = text.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if ln.strip().lower() == "svenska":
            start = i + 1
            break
    if start is None:
        return None

    out: list[str] = []
    for ln in lines[start:]:
        if not ln.strip():
            if out:
                break
            continue
        if ln.lstrip().startswith(":"):
            out.append(ln)
            continue
        # Stop at the next language header / section header.
        if re.fullmatch(r"[A-Za-zÅÄÖåäö][A-Za-zÅÄÖåäö \-]{0,40}", ln.strip()):
            break
        if ln.strip().startswith("=="):
            break
    if not out:
        return None
    return "\n".join(out).strip()


def _expand_repeat_markers(lines: list[str]) -> list[str]:
    # Expand simple repeat markers like ":||: ... :||" by duplicating the inner content.
    out: list[str] = []
    pat = re.compile(r"^\s*:?\|\|:\s*(.*?)\s*:?\|\|\s*$")
    for ln in lines:
        m = pat.match(ln)
        if m:
            inner = m.group(1).strip()
            if inner:
                out.append(inner)
                out.append(inner)
            continue
        out.append(ln)
    return out


def _lyrics_to_full_text(text: str) -> tuple[str, list[str]]:
    # Convert to a plain lyric block: no wiki headings, no indent markers, no repeat symbols.
    notes: list[str] = []
    raw_lines = text.splitlines()
    kept: list[str] = []
    for ln in raw_lines:
        s = ln.strip()
        if not s:
            kept.append("")
            continue
        if s.startswith(("==", "=", "Ursprung", "Övrigt", "På olika språk")):
            continue
        if s.lower().startswith(("franska", "tyska", "engelska", "danska", "norska", "finska", "ryska", "latin")):
            # Likely language sections; keep only the selected block upstream.
            continue
        if s.startswith(":"):
            s = s.lstrip(":").strip()
        kept.append(s)

    kept = _expand_repeat_markers(kept)
    # Remove any remaining repeat tokens inline (minor).
    kept2: list[str] = []
    for ln in kept:
        ln2 = ln.replace(":||:", "").replace(":||", "").replace("||:", "").replace("||", "")
        kept2.append(ln2.strip())

    text2 = "\n".join(kept2)
    text2 = _strip_stanza_numbers(text2)
    text2 = re.sub(r"\n{3,}", "\n\n", text2).strip()
    if text2 != text:
        notes.append("normalized to plain lyrics (no repeats/markup)")
    return text2 + "\n", notes


def _lyrics_quality_fix(text: str, title: str) -> tuple[bool, str, list[str]]:
    """
    Return (ok, fixed_text, notes).
    - ok=False means "obviously not lyrics" (JS/HTML dump, navigation, etc.) and caller should retry another URL.
    - ok=True may still include minor cleanups (stanza numbers, headings).
    """
    notes: list[str] = []
    t = (text or "").strip()
    if not t:
        return False, "", ["empty text"]

    # If the page includes poem blocks, prefer them (often the cleanest lyric content).
    poem_blocks = re.findall(r"(?is)<poem[^>]*>(.*?)</poem>", t)
    if poem_blocks:
        t = "\n\n".join(p.strip() for p in poem_blocks if p.strip()).strip()

    # Fast "obviously wrong" filters.
    bad_markers = [
        "rlconf",
        "rlstate",
        "rlpagemodules",
        "mw.config",
        "mw.loader",
        "function(",
        "document.cookie",
        "<script",
        "<style",
        "<html",
        "<head",
    ]
    low = t.lower()
    if any(m in low for m in bad_markers):
        return False, "", ["looks like page JS/HTML, not lyrics"]

    # If HTML tags remain in quantity, treat as wrong (we expect plain-ish text at this stage).
    if len(re.findall(r"</?[a-zA-Z][^>]{0,60}>", t)) >= 8:
        return False, "", ["looks like HTML page body, not lyrics"]

    # Minor cleanups.
    t2 = t
    t2 = t2.replace("\r\n", "\n").replace("\r", "\n")
    t2 = unicodedata.normalize("NFKC", t2)
    t2 = re.sub(r"[ \t]+\n", "\n", t2)
    t2 = re.sub(r"\n{3,}", "\n\n", t2)

    # Strip a leading title line if it matches the song title tokens strongly.
    lines = t2.splitlines()
    if lines:
        first = lines[0].strip()
        toks = _title_tokens(title)
        hay = _normalize_for_match(first)
        if toks and sum(1 for tok in toks[:4] if tok in hay) >= max(2, min(3, len(toks[:4]))):
            notes.append("removed leading title line")
            t2 = "\n".join(lines[1:]).lstrip()

    t2 = _strip_stanza_numbers(t2)

    # If this looks like a multi-language page, try to isolate Swedish lyrics.
    sw_block = _extract_swedish_block(t2)
    if sw_block:
        t2 = sw_block

    # Convert to plain lyric block and expand/remove repeat markers.
    t2, more_notes = _lyrics_to_full_text(t2)
    notes.extend(more_notes)

    # Keep only if we have enough "lyric-like" content (letters on multiple lines).
    lyric_lines = [ln for ln in t2.splitlines() if re.search(r"[A-Za-zÅÄÖåäö]", ln)]
    if len("".join(lyric_lines)) < 80 or len(lyric_lines) < 3:
        # Too short: could be a stub page, a redirect, or metadata only.
        return False, "", ["too little lyric content after cleanup"]

    return True, t2.strip() + "\n", notes


def main(argv=None):
    parser = argparse.ArgumentParser(description='Bounded catalogue discovery, source download, and lyric extraction')
    commands = parser.add_subparsers(dest='operation', required=True)
    catalogue = commands.add_parser('catalogue')
    catalogue.add_argument('csv_file', type=Path)
    catalogue.add_argument('--out', type=Path, required=True)
    catalogue.add_argument('--search-direct', action='store_true')
    catalogue.add_argument('--search-lyrics', action='store_true')
    catalogue.add_argument('--no-pdf', action='store_true')
    catalogue.add_argument('--max-direct-candidates', type=int, default=5)
    download = commands.add_parser('download')
    download.add_argument('url')
    download.add_argument('--out', type=Path, required=True)
    download.add_argument('--receipt', type=Path, required=True)
    download.add_argument('--title', required=True)
    download.add_argument('--verify-downloads', action='store_true')
    extract = commands.add_parser('extract')
    extract.add_argument('raw', type=Path)
    extract.add_argument('--url', required=True)
    extract.add_argument('--title', required=True)
    extract.add_argument('--out', type=Path, required=True)
    for command in (catalogue, download, extract):
        add_config_argument(command)
    args = parser.parse_args(argv)
    config = load_project(args.config_root)
    inputs = [data_path(config, getattr(args, name), must_exist=True)
              for name in ('csv_file', 'raw') if hasattr(args, name)]
    output = fresh_output(data_path(config, args.out), inputs=inputs)
    if args.operation == 'catalogue':
        if args.max_direct_candidates < 1:
            raise ValueError('max-direct-candidates must be positive')
        rows = _read_rows(inputs[0])
        if not rows:
            raise ValueError('No usable catalogue rows')
        grouped = {}
        for row in rows:
            grouped.setdefault(row.number, []).append(row)
        result = []
        for number, song_rows in grouped.items():
            row = song_rows[0]
            item = {'number': number, 'title': row.title, 'license_evidence': row.status,
                    'license_verification': 'Catalogue claim; not independently verified'}
            if row.status.upper().startswith('SKYDDAD'):
                item['skipped'] = 'SKYDDAD'
            else:
                candidates = ([(fmt, url, 'duckduckgo') for fmt, url in
                               _candidate_urls_for_song(row.title, args.max_direct_candidates)] if args.search_direct else [])
                candidates += [(r.fmt, r.url, r.source) for r in song_rows]
                seen = set()
                item['sources'] = []
                for fmt, url, source in sorted(candidates, key=lambda value: _format_priority(value[0])):
                    fmt = fmt.upper()
                    if url in seen or (fmt == 'PDF' and args.no_pdf) or fmt not in {'MUSICXML','XML','MXL','MSCZ','MIDI','MID','PDF'}:
                        continue
                    seen.add(url)
                    item['sources'].append({'format': fmt, 'url': url, 'source': source})
                item['lyric_urls'] = _candidate_lyric_urls_for_song(row.title)[:6]
                if args.search_lyrics:
                    queries = [f'"{row.title}" sångtext', f'"{row.title}" text', f'"{row.title}" lyrics']
                    if row.composer_or_origin:
                        queries.append(f'"{row.title}" {row.composer_or_origin} sångtext')
                    item['lyric_urls'] += _dedupe_preserve_order([url for query in queries for url in
                        _search_duckduckgo_urls(query, max_results=5) if url.startswith(('http://','https://'))])[:6]
            result.append(item)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    elif args.operation == 'download':
        receipt = fresh_output(data_path(config, args.receipt), inputs=[output])
        if receipt == output:
            raise ValueError('Source and receipt destinations must differ')
        value = _download(args.url, output)
        if not _nonempty(output):
            raise ValueError('Downloaded source is empty')
        value['title'] = args.title
        value['original_name'] = urllib.parse.unquote(urllib.parse.urlparse(args.url).path.rsplit('/', 1)[-1])
        value['warnings'] = _verify_downloaded_file(output, args.title) if args.verify_downloads else []
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    else:
        payload = inputs[0].read_bytes()
        try:
            text = payload.decode('utf-8')
        except UnicodeDecodeError:
            text = payload.decode('latin-1', errors='ignore')
        text = _strip_html_to_text(text) if '<html' in text.lower() else text.strip()
        if args.url.endswith('?action=raw') and 'wiki' in args.url:
            text = _strip_mediawiki_markup(text)
        ok, fixed, notes = _lyrics_quality_fix(text, args.title)
        if not ok:
            raise ValueError('; '.join(notes))
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(fixed, encoding='utf-8')
        print(json.dumps({'notes': notes}, ensure_ascii=False))


if __name__ == '__main__':
    main()
