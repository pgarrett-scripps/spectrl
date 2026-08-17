# Releasing spectrl

Releases are published from GitHub. A published GitHub release triggers OIDC
Trusted Publishing for both PyPI and npm; no long-lived registry token is kept
in GitHub. Zenodo archives the release when the repository is connected there.

## Registry configuration

### PyPI

The `spectrl` project already has a working Trusted Publisher. Confirm its
settings under PyPI project **Manage → Publishing**:

- owner: `pgarrett-scripps`
- repository: `spectrl`
- workflow: `publish.yml`
- environment: `pypi`

No `PYPI_TOKEN` secret is needed.

### npm

The public package is `@spectrl-ms/spectrl`. Version 0.4.1 was published once
to bootstrap the package, and its Trusted Publisher is configured as:

- provider: GitHub Actions
- organization/user: `pgarrett-scripps`
- repository: `spectrl`
- workflow filename: `publish.yml`
- environment: `npm`
- allowed action: `npm publish`

GitHub environments named `pypi` and `npm` exist without deployment protection
rules. Publishing therefore starts automatically when a GitHub release is
published. Repository access controls determine who can initiate a release.

The workflow uses npm's OIDC support and automatically receives provenance. Do
not create an `NPM_TOKEN` secret.

## Before the release

1. Confirm that the version agrees in `pyproject.toml`, `js/package.json`, and
   `CITATION.cff`, `.zenodo.json`, and both lockfiles.
2. Move the release notes from `[Unreleased]` to a dated version in
   `CHANGELOG.md`.
3. Run the complete local gate:

   ```bash
   just release-check
   ```

4. Push `main` and wait for CI to pass.
5. Confirm that the PyPI and npm Trusted Publishers match the one-time settings
   above.
6. Confirm that the GitHub repository is connected to Zenodo and that release
   archiving is enabled.

## Publish

Create a GitHub release with tag `vX.Y.Z`, target `main`, and the matching
section of `CHANGELOG.md` as its notes. Do not mark a stable release as a
prerelease. Publishing the release starts PyPI, npm, and Zenodo publication.
The workflow refuses to publish when the tag and package metadata disagree.

Afterward, install from both registries in clean directories, confirm the npm
provenance and PyPI attestations, and verify the Zenodo record and DOI.
