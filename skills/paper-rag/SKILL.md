---
name: paper-rag
description: Retrieve and reference the radio-wave fall detection / human activity sensing paper collection in the radio-fall-detection project. Use when the user asks about fall detection using WiFi, CSI, radar, UWB, mmWave, RSSI, Doppler, activity recognition, or related topics covered by these papers.
---

# Paper RAG — radio-fall-detection

Retrieve and reference the academic paper collection on fall detection and human activity sensing using radio waves (WiFi CSI, mmWave/UWB radar, RSSI, Doppler).

## Collection

- Papers: `resources/Papers/md/` (converted Markdown)
- Raw PDFs: `resources/Papers/`
- Metadata catalog: `tools/papers/index.json` (`papers` entries)
- Search index: built by `tools/papers/rag.py` into `tools/papers/.rag-index/`

## Retrieval Workflow

1. **Scan metadata** — read `tools/papers/index.json` to find candidate papers by title, methods, or keywords.

2. **Semantic search**:

```bash
python3 tools/papers/rag.py query "fall detection using WiFi channel state information"
python3 tools/papers/rag.py query "radar based human activity recognition" --top 10
```

Queries work in English and Indonesian; results show source file, section heading, and context lines.

3. **Exact-match verification** — use ripgrep for specific terms:

```bash
rg -i "ultra-wideband" resources/Papers/md/
rg -l "CSI amplitude" resources/Papers/md/
```

4. **Deep read** — read the abstract and conclusion of the most relevant papers:

```bash
head -40 resources/Papers/md/<paper>.md
tail -50 resources/Papers/md/<paper>.md
```

5. **Index maintenance** — after adding or converting papers:

```bash
python3 tools/papers/rag.py index
python3 tools/papers/rag.py check
```

## Notes

- Run all commands from the project root.
- If search results are poor, try synonyms or re-index after adding files.
- If `rag.py` reports no index, run `python3 tools/papers/rag.py index` first.
- `rag.py check` exits non-zero when converted Markdown is missing from `tools/papers/index.json`; keep the catalog current.
