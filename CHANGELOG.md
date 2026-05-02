# Changelog

All notable changes to OpenCR are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/), and the project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Apache-2.0 license (`LICENSE`).
- English-first README with Turkish sibling at `README.tr.md`.
- `CONTRIBUTING.md`, GitHub Actions CI workflow, project `Makefile`.
- **Apple Silicon / CPU support.** New `MODEL_BACKEND=local` runs DeepSeek-OCR in-process via `transformers`, no GPU server required. Also adds `MODEL_BACKEND=remote` for any OpenAI-compatible endpoint.
- New CPU Docker profile and `Dockerfile.cpu`: `docker compose --profile cpu up -d`.
- `scripts/start.sh` one-command launcher with smart defaults; `requirements-local.txt` for the optional `transformers`/`torch` stack.
- **HuggingFace OAuth** ("Sign in with HuggingFace"). When configured, gates the publish action on a real HF login and uses the user's own write token. Falls back to paste-token mode when OAuth is unset.
- Publish modal now prefills `username/run-name` and adds the `opencr` discoverability tag to dataset cards.

### Changed
- **Breaking:** `docker compose up` no longer starts services without an explicit profile. Use `--profile gpu` (vLLM, NVIDIA) or `--profile cpu` (in-process transformers).
- `INPUT_DIR` / `OUTPUT_DIR` default to `./input` / `./output` outside Docker, `/data/...` inside.
- OpenAPI metadata now declares Apache-2.0; UI footer no longer claims "All rights reserved".

### Fixed
- `.gitignore` now covers `.DS_Store`, IDE folders, lint caches, and HF caches.

---

## How to release

1. Decide the next version (`MAJOR.MINOR.PATCH`).
2. Move the `[Unreleased]` block to a new `## [X.Y.Z] — YYYY-MM-DD` heading.
3. Bump `pipeline_version` in `ocr_pipeline/config.py` to match.
4. Commit: `git commit -am "release: vX.Y.Z"`.
5. Tag: `git tag vX.Y.Z && git push --tags`.
6. GitHub auto-creates a release page from the tag; paste the changelog entry into it.

Bump rules:
- **PATCH** for bug fixes that don't change behavior.
- **MINOR** for backwards-compatible features.
- **MAJOR** for breaking changes (env var renames, removed endpoints, behavior shifts users have to adapt to).
