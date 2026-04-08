---
name: download-scores
description: Download music scores (sheet music, noter) for Swedish children's songs from a CSV file. Searches IMSLP, Musikverket, Internet Archive, MuseScore, and other sources. Saves to MusicSheet/ with structured naming and produces a download report.
allowed-tools: Read Bash Grep Glob Write WebSearch WebFetch Agent TodoWrite
argument-hint: [csv-file]
effort: max
---

# Download Music Scores for Swedish Children's Songs

You are a research agent. Your task is to systematically find and download music scores (sheet music, noter) for Swedish children's songs from the provided CSV file.

## Input

The CSV file path is provided as `$ARGUMENTS`. If no argument is given, look for a CSV file in the current working directory that contains song data (e.g., `songs.csv`, `barnvisor.csv`, or similar).

Read the CSV file first. Identify columns for: song number, song title, composer, and copyright status.

## Copyright Filter

- Songs marked FRI GLOBALT or FRI I EU/SE: search and download.
- Songs marked SKYDDAD (copyright protected): **skip entirely**. Do not attempt to download.

## Output Directory

Save all files to `MusicSheet/`. Create it if it doesn't exist.

## File Naming Convention

Every downloaded file must follow this pattern:

```
[number]_[song_name]_[source].[ext]
```

Example: `007_Ekorr_n_satt_i_granen_IMSLP.pdf`

- Use the number and name exactly as in the CSV.
- Replace spaces with `_`, strip special characters: å→a, ä→a, ö→o, '→nothing.
- Multiple files for the same song: append `_v1`, `_v2`, etc.

## Search Strategy — For Every Eligible Song

Check **all** of these sources:

1. **IMSLP** (imslp.org) — search by song title and composer. Alice Tegner's works: `imslp.org/wiki/Category:Tegnér,_Alice`
2. **Musikverket / Svenskt Visarkiv** (visarkiv.se) — Swedish national folk music archive
3. **Kungliga Biblioteket** (kb.se) — digitized historical score collections
4. **Internet Archive** (archive.org) — search "svenska barnvisor noter" and individual titles
5. **Musopen** (musopen.org) — public domain scores
6. **MuseScore** (musescore.com) — community scores
7. **Svenska Barnvisor** (svenskabarnvisor.se) — may have printable scores
8. **Google search**: `[song title] noter PDF free download` and `[song title] sheet music MIDI`

### Search Tips

- Try both original Swedish spelling and transliterated versions (å→a, ä→a, ö→o).
- Try variant titles — many songs have alternate names.
- If IMSLP requires navigating to a composer page first, do so.
- Do **not** download files behind paywalls or login walls.
- Verify each file is actually a score (not a webpage or lyrics-only page).

## MIDI Files — Priority

MIDI files are especially valuable. If found, always download them. Name identically to PDFs but with `.mid` extension.

## Score Collections

If you find a collection (e.g., "Sjung med oss Mamma" on Internet Archive) that contains multiple songs from the list:
- Download the whole collection.
- Note which songs it covers in the report.
- If possible, extract individual pages per song and save as separate files.

## Thoroughness Requirements

- Try at least 3-4 different sources and search queries before marking a song as NOT FOUND.
- If multiple versions or arrangements exist, download all of them.
- Quality matters more than speed. A thorough search that finds 80% is far more valuable than a fast search that finds 30%.

## Logging — For Each Song

Track progress with TodoWrite. For each song produce a log entry:

```
Song #[n]: [Title]
Status: FOUND / PARTIAL / NOT FOUND
Files downloaded:
  - [filename] | Source: [full URL] | Format: [PDF/MIDI/XML] | Notes: [...]
Search notes: [what you tried, what you found, why certain sources were skipped]
```

## Final Report

When done, produce `MusicSheet/DOWNLOAD_REPORT.md` containing:

1. Total songs processed
2. Songs with at least one score found (with filenames)
3. Songs with only partial results
4. Songs where nothing was found (with notes on what was tried)
5. Score collections downloaded that cover multiple songs
6. MIDI files found
7. Recommendations for manual follow-up

## Context

The scores will be used to produce music accompaniment for a Swedish children's YouTube channel. Completeness and accuracy are critical.
