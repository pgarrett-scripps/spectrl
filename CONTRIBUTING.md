# Contributing to spectrl

Thanks for your interest in improving spectrl. The token format is an open
specification governed in this repository, so contributions are welcome at two
levels:

1. **The reference implementation** (this Python library): bug fixes, codecs,
   performance, tests, docs.
2. **The format specification**: see [SPECIFICATION.md](SPECIFICATION.md).
   Changes that alter the on-the-wire token format are governed more strictly
   (see *Format changes* below).

By contributing, you agree that your contributions are licensed under the
project's [Apache-2.0 License](LICENSE), and you certify the
[Developer Certificate of Origin](https://developercertificate.org/) for each
commit.

## Development setup

This project uses [uv](https://docs.astral.sh/uv/) and
[just](https://github.com/casey/just).

```bash
uv sync --all-extras       # install runtime + dev + optional deps
just test                  # run the test suite
just lint                  # run ruff
```

If you don't use `just`, the underlying commands are:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

## Pull requests

- Open an issue first for anything non-trivial so we can agree on the approach.
- Keep PRs focused; one logical change per PR.
- Add or update tests for any behavior change. The round-trip and
  canonical-hash tests are the contract; do not weaken them without discussion.
- Run `just test` and `just lint` before pushing.
- Update [CHANGELOG.md](CHANGELOG.md) under `## [Unreleased]`.

## Format changes (token wire format)

The `spectrl2` token format is normative. Any change that affects how a token
is produced or parsed (new header keys, codec changes, framing changes)
**must**:

1. Be discussed in an issue tagged `format`.
2. Update [SPECIFICATION.md](SPECIFICATION.md) and `schema/registry.json`.
3. Preserve backward compatibility, or bump the format version
   (`spectrl2` → `spectrl3`) per the versioning policy in the specification.
4. Include round-trip test vectors.

`schema/registry.json` also drives the generated internal constant modules for
Python and TypeScript. After changing registered keys, accessions, codecs, or
wire limits, run `just registry`; do not hand-edit `src/spectrl/_format.py` or
`js/src/format.ts`. The test suite checks all three files for drift.

Format changes are reviewed for backward compatibility and for interoperability
with mzML controlled-vocabulary semantics and [ProForma](https://www.psidev.info/proforma).

## Reporting bugs

Open a GitHub issue with: the spectrl version, a minimal reproducing snippet
or token, and the expected vs. actual behavior. For decode failures, include
the (redacted if needed) token or its header inspected via `spectrl inspect`.
