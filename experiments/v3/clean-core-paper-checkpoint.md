# Clean core paper checkpoint

Completed on 2026-09-18 before the separately approved 0.1 ppm m/z default change.
These checks cover the four-encoding core with linear m/z scale 100000 and
logarithmic intensity scale 3600. They do not validate the later default change.

The paper library copy was synchronized with the main implementation. The
following paper gates passed:

- `just assets`
- `just check-stats-deep`, with 78 values rederived and no errors
- Isolated timing regeneration after other analysis jobs finished
- `just fmt`
- `just paper`
- `just docx`
- `just verify`, including formatting, extractors, prose rules, and staleness

Visual review covered all 23 PDF pages and all 31 rendered Word pages. No clipped
content, overlapping elements, or missing glyphs were found. The Word export
contains 11 native equations, six tables, and ten images.

At this checkpoint, the abstract contains 181 words, the main text 1288 words,
and the supporting information 1993 words. Flesch-Kincaid grades are 11.2 for
the main text and 12.3 for the supporting information.

The task implementing the 0.1 ppm default owns subsequent source synchronization,
fresh measurements, generated paper assets, exports, and verification. The
lossless core-selection study is independent of that lossy default change.
