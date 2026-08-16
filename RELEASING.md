# Releasing spectrl

Releases are published from GitHub. A published GitHub release triggers the
trusted-publishing workflow for PyPI; Zenodo archives the release when the
GitHub repository is connected in Zenodo.

## Before the release

1. Confirm that the version agrees in `pyproject.toml`, `js/package.json`, and
   `CITATION.cff`, and that `date-released` is correct.
2. Move the release notes from `[Unreleased]` to a dated version in
   `CHANGELOG.md`.
3. Run the complete local gate:

   ```bash
   just release-check
   ```

4. Push `main` and wait for CI to pass.
5. Confirm that PyPI Trusted Publishing is configured for repository
   `pgarrett-scripps/spectrl`, workflow `publish.yml`, environment `pypi`.
6. Confirm that the GitHub repository is connected to Zenodo and that release
   archiving is enabled.

## Publish

Create a GitHub release with tag `vX.Y.Z`, target `main`, and the matching
section of `CHANGELOG.md` as its notes. Do not mark a stable release as a
prerelease. Publishing the release starts the PyPI workflow and Zenodo archive.

Afterward, verify the new version on PyPI, confirm the Zenodo record and DOI,
and add the DOI badge supplied by Zenodo to `README.md`.
