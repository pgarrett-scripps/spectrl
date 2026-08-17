# spectrl demo

A single-page browser demo of [spectrl](../README.md): it **encodes** example
mass spectra into `spectrl.v1` tokens, shows the **shareable URL + QR code**, and
**decodes** the token back into a plotted spectrum, entirely client-side, with
no server or network call. It runs on the real
[`@spectrl-ms/spectrl`](../js) JavaScript codec.

## Launch

From the repo root:

```bash
just demo
```

…or directly:

```bash
cd js && npm install && npm run build   # build the codec the demo imports
cd ../demo && npm install && npm run dev
```

Then open **http://127.0.0.1:8000**.

The default playground bundle stays small. PSI-MS zstd support is loaded as a
separate browser chunk only when a pasted token actually uses a zstd codec.

## What it shows

The page leads with the product idea, then puts the decoded spectrum and its
share action at the center of an interactive playground. Everything is
recomputed live on each example or encoding-mode change.

- **Pick a spectrum**: peptide MS², small-molecule MS¹, top-down MS², per-peak
  ion mobility, auxiliary arrays, or synthetic scans of **100** and **500**
  peaks. Toggle **lossless** to compare sizes.
- **Spectrum plot**: an uncluttered SVG stick plot. Hover a peak for m/z / intensity.
- **Spectrum summary**: readable chips surface the interpretation, MS level,
  precursor, charge, activation, ion mobility, auxiliary arrays, and peak count
  before the raw CV metadata.
- **Share bar** (under the plot): a compact status line plus:
  - **Copy shareable link**: the URL (token in a `#fragment`, never sent to a
    server). The raw URL isn't shown because it isn't human-readable.
  - **QR code**: reveals a QR of the URL on demand. Oversized tokens (e.g. the
    500-peak example) surface the token-too-large guidance.
- **View token**: reveals the bare token and accepts any `spectrl.v1` token to decode.
- **Technical details**: an expandable inspector containing token size (KB)
  and B/peak, complete-token size relative to raw peak arrays, what
  the *other* mode would cost, m/z range, base peak, round-trip precision
  (max/mean Δm/z and Δintensity, or "bit-exact" in lossless), encode/decode
  timing, and a segment-size breakdown bar chart.
- **Decoded metadata**: the inspector also contains a table rendered from the decoded PSI-MS CV accessions
  (ms level, polarity, precursor m/z, charge, activation, ProForma, …).

The page reads a token from its own URL fragment on load, so a link like
`…/index.html#spectrl.v1.…` opens straight to that spectrum, which is handy for slides.

## Talking points for a live demo

- Open the page, encode the MS² example, then **turn off Wi-Fi** and reload the
  shareable URL: it still decodes. The data was never on a server.
- Decode in this JS app a token your Python session produced (same `spectrl.v1`
  format) to show cross-implementation interop.
- Truncate a character in the token textarea to show the checksum rejecting a
  corrupted token instead of plotting garbage.

> Note: the example masses are illustrative (computed from monoisotopic residue
> masses). They demonstrate the format, not a specific real acquisition.
