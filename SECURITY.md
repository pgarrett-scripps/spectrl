# Security Policy

## Reporting a vulnerability

Please report suspected security vulnerabilities privately by email to
**pgarrett@scripps.edu** (do not open a public issue). You should receive a
response within a week. Please include a description of the issue, steps to
reproduce (a token that triggers it, if applicable), and the affected version.

## Scope

spectrl decodes tokens that typically arrive from untrusted URLs. Reports of
particular interest:

- decoding a malformed or adversarial token causing excessive memory/CPU use
  (decompression bombs, unbounded allocation) or a crash that is not a clean
  `SpectrlDecodeError`;
- silent data corruption: a token that decodes without error to values that
  differ from what a conforming producer encoded;
- content-hash verification bypasses.

The content hash is an integrity check only; it is **not** an authentication
mechanism, and reports that it can be recomputed by an adversary are expected
behavior (see SPECIFICATION.md §12).

## Supported versions

Only the latest released version receives security fixes.
