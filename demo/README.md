# spectrl demo

A single-page browser demo of [spectrl](../README.md): it **encodes** example
mass spectra into `spectrl2` tokens, shows the **shareable URL + QR code**, and
**decodes** the token back into a plotted spectrum, entirely client-side, with
no server or network call. It runs on the real
[`@spectrl/spectrl`](../js) JavaScript codec.

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

## What it shows

The spectrum plot sits at the top so you see the decoded
data immediately. Everything is recomputed live on each pick / mode toggle.

- **Pick a spectrum**: peptide MS² (real b/y fragment-ion m/z + ProForma),
  small-molecule MS¹ isotope envelope, dense 40-peak MS², or synthetic profile
  scans of **100** and **500** peaks. Toggle **lossless** to compare sizes.
- **Spectrum plot**: an SVG stick plot; hover a peak for m/z / intensity.
- **Share bar** (under the plot): a compact status line (token size in KB, peak
  count, mode, integrity-hash status) plus:
  - **Copy link**: the shareable URL (token in a `#fragment`, never sent to a
    server). The raw URL isn't shown because it isn't human-readable.
  - **Copy token**: the bare `spectrl2.…` token.
  - **Show QR**: reveals a QR of the URL on demand. Oversized tokens (e.g. the
    500-peak example) surface the token-too-large guidance.
  - **Paste a token…**: reveals a box to paste any `spectrl2` token to decode.
- **Encoding stats**: token size (KB) and B/peak, ratio vs raw float64, what
  the *other* mode would cost, m/z range, base peak, round-trip precision
  (max/mean Δm/z and Δintensity, or "bit-exact" in lossless), encode/decode
  timing, and a segment-size breakdown bar chart.
- **Decoded metadata**: a table rendered from the decoded PSI-MS CV accessions
  (ms level, polarity, precursor m/z, charge, activation, ProForma, …).

The page reads a token from its own URL fragment on load, so a link like
`…/index.html#spectrl2.…` opens straight to that spectrum, which is handy for slides.

## Talking points for a live demo

- Open the page, encode the MS² example, then **turn off Wi-Fi** and reload the
  shareable URL: it still decodes. The data was never on a server.
- Decode in this JS app a token your Python session produced (same `spectrl2`
  format) to show cross-implementation interop.
- Truncate a character in the token textarea to show the content-hash
  integrity check rejecting a corrupted token instead of plotting garbage.

> Note: the example masses are illustrative (computed from monoisotopic residue
> masses); they demonstrate the format, not a specific real acquisition.
