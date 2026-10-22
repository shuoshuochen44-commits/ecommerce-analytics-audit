# GitHub first release preparation

**Goal:** Publish the current desktop analysis project to the user-selected public repository, with MIT licensing, reproducible setup, tests and a Windows download.

**Scope:** Documentation, publication hygiene and automation. Preserve desktop program behavior and all existing local user data. Existing remote origin points to a local repository; add a separate GitHub remote rather than overwrite it.

## Preparation

- [ ] Confirm owner, public visibility, repository slug and MIT permission; user performs GitHub login on the official site.
- [x] Rewrite README for readers cloning the repository; include features, capability limits, setup, test and build commands, and interface screenshots.
- [x] Add root MIT license, changelog, contribution notes and Windows CI. Keep original third-party fixture license.
- [x] Exclude local workspace, credentials, generated databases and build outputs from new commits; replace machine-specific paths in tracked documentation.
- [x] Mark old browser demo package script as historical and point to current desktop build.
- [x] Verify installation and tests from a separate environment, audit staged files and assemble a release zip containing only exe, external generated import samples and usage/license/checksum files.

## Publication

- [ ] Create or inspect the user-authorized target without replacing existing remote content; add GitHub remote, push the reviewed branch and preserve old local origin.
- [ ] Check repository visibility and uploaded file list, and follow the first CI run through completion.
- [ ] Publish v0.1.0 with a Windows download and concise release notes if this version/tag does not already exist.
- [ ] Return repository and release links; report any real unfinished verification accurately.
