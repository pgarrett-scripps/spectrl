# Releasing spectrl

Releases are published from GitHub. A published GitHub release triggers OIDC
Trusted Publishing for PyPI and npm, and publishes the Rust crate to crates.io.
Zenodo archives the release when the repository is connected there.

## Registry configuration

### PyPI

The repository moved from `pgarrett-scripps` to the `tacular-omics`
organization before 3.0.0. Trusted Publishers record the owner, so add one
with these settings under PyPI project **Manage → Publishing** (the old
`pgarrett-scripps` publisher can be removed after the first release):

- owner: `tacular-omics`
- repository: `spectrl`
- workflow: `publish.yml`
- environment: `pypi`

No `PYPI_TOKEN` secret is needed.

### npm

The public package is `@spectrl-ms/spectrl`. Version 0.4.1 was published once
to bootstrap the package. Its Trusted Publisher must name the new owner:

- provider: GitHub Actions
- organization/user: `tacular-omics`
- repository: `spectrl`
- workflow filename: `publish.yml`
- environment: `npm`
- allowed action: `npm publish`

GitHub environments named `pypi` and `npm` exist without deployment protection
rules. Publishing therefore starts automatically when a GitHub release is
published. Repository access controls determine who can initiate a release.

The workflow uses npm's OIDC support and automatically receives provenance. Do
not create an `NPM_TOKEN` secret.

### crates.io

The Rust crate is `spectrl` in `rust/`. crates.io allows Trusted Publishing only
for a crate that already exists, and `spectrl` has never been published, so the
first release (3.0.0) uses an API token:

1. Owner step: create a crates.io API token scoped to `publish-new` and
   `publish-update` for `spectrl`, and add it as the repository secret
   `CARGO_REGISTRY_TOKEN`. The `publish-crates` job in `publish.yml` passes it
   to `cargo publish`.
2. After 3.0.0 is on crates.io, configure its Trusted Publisher under the crate's
   **Settings → Trusted Publishing**:
   - repository owner: `tacular-omics`
   - repository name: `spectrl`
   - workflow filename: `publish.yml`
   - environment: `crates-io`
3. Switch `publish.yml` to the commented `rust-lang/crates-io-auth-action`
   steps, then delete the `CARGO_REGISTRY_TOKEN` secret and revoke the token.

CI runs `cargo publish --dry-run` on every push, so packaging errors surface
before tag time.

## Before the release

1. Confirm that the version agrees in `pyproject.toml`, `js/package.json`,
   `rust/Cargo.toml`, `CITATION.cff`, `.zenodo.json`, and the three lockfiles
   (`scripts/check_release_version.py` checks this).
2. Move the release notes from `[Unreleased]` to a dated version in
   `CHANGELOG.md`.
3. Run the complete local gate:

   ```bash
   just release-check
   ```

4. Push `main` and wait for CI to pass.
5. Confirm that the PyPI and npm Trusted Publishers match the one-time settings
   above, and that the `CARGO_REGISTRY_TOKEN` secret exists (first crates.io
   release) or the crates.io Trusted Publisher is configured (later releases).
6. Confirm that the GitHub repository is connected to Zenodo and that release
   archiving is enabled.

## Publish

Create a GitHub release with tag `vX.Y.Z`, target `main`, and the matching
section of `CHANGELOG.md` as its notes. Do not mark a stable release as a
prerelease. Publishing the release starts PyPI, npm, crates.io, and Zenodo publication.
The workflow refuses to publish when the tag and package metadata disagree.

Afterward, install from all three registries in clean directories (for Rust,
`cargo install spectrl` and run `spectrl --version`), confirm the npm
provenance and PyPI attestations, and verify the Zenodo record and DOI.
