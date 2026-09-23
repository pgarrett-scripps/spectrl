# spectrl demo

A two-page browser demo of [spectrl](../README.md): it **encodes** example
mass spectra into `spectrl.v3` tokens, shows the **shareable URL + QR code**, and
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

The demo bundle stays small. The Brotli payload backend is loaded as a
separate browser chunk only when a token actually uses it.

It also **converts files**: open an mzML, MGF or MS2 file, pick a spectrum,
and get its token; or write the displayed spectrum back out as any of the
three. Like everything else here, that happens in the page, with no upload.

## What it shows

Two pages share one stylesheet and a three-item header: **Demo**, **Convert**,
and the GitHub repository.

**Demo** (`index.html`) puts one spectrum on the page, top to bottom:

- **Example spectrum**: peptide MS², small-molecule MS¹, top-down MS², per-peak
  ion mobility, auxiliary arrays, or synthetic scans of **100** and **500**
  peaks. A **lossless** toggle re-encodes the current spectrum bit-exactly.
- **Plot and summary**: an SVG stick plot (hover a peak for m/z and intensity)
  with chips for MS level, precursor, charge, activation, extra arrays, and
  peak count.
- **Token**: the bare `spectrl.v3` string, editable, with **Copy link**
  (token in a URL `#fragment`), **Copy token**, and an on-demand **QR code**.
  Paste any token here to decode it.
- **Metadata in the token**: every decoded PSI-MS parameter with its accession.
- Two collapsed sections: **Encoding details** (size, bytes per peak,
  round-trip error, timings, checksum, segment breakdown) and **Quality
  report** (downloadable JSON).

**Convert** (`convert.html`) is a tool with both directions on screen: open an
mzML, MGF or MS2 file and pick a spectrum from the list to get its token, or
paste a token and save it as mzML, MGF, MS2, or a peak-list TSV. Anything a
format cannot hold is listed when you save. Three small example files
(`examples/example.mzML`, `.mgf`, `.ms2`) are offered for download so the
converter can be tried without a run to hand. They are the demo's example
spectra written by the library's own writers; `npm run examples` regenerates
them, and `npm run build` does so too.

The demo reads a token from its own URL fragment on load, so a link like
`…/index.html#spectrl.v3.…` opens straight to that spectrum, which is handy for slides.

## Talking points for a live demo

- Open the page, encode the MS² example, then **turn off Wi-Fi** and reload the
  shareable URL: it still decodes. The data was never on a server.
- Decode in this JS app a token your Python session produced (same `spectrl.v3`
  format) to show cross-implementation interop.
- Truncate a character in the token textarea to show the checksum rejecting a
  corrupted token instead of plotting garbage.

> Note: the example masses are illustrative (computed from monoisotopic residue
> masses). They demonstrate the format, not a specific real acquisition.

**User data**

The converter accepts pasted two-column peak lists as well as files. Peak-list
TSV export writes only the m/z and intensity arrays. See the
[workflow guide](../docs/workflows.md).

**Browser regression checks**

Build the library first, then run these commands from the demo directory:

```bash
npm ci
npx playwright install chromium
npm test
```

The same assertions can run in a regular browser. Run `npm run build-tests`,
serve the demo directory, open `/tests/browser.html`, and select Run browser
regressions. The suite checks literal metadata rendering, user-data import,
encoding-mode changes, and the three downloadable example files.
