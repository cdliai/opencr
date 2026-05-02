# Contributing to OpenCR

Thanks for considering a contribution. 

OpenCR exists to make Turkish-language and archival OCR easy to run, 
share, and improve — every PR, issue, and dataset published with OpenCR 
helps that goal.

## Ways to help

- **File issues.** Found a bug, a layout that OpenCR struggles with, 
or a confusing piece of docs? Open an issue with a short PDF 
(or page screenshot) we can reproduce against.

- **Add Turkish-language test fixtures.** A small public-domain PDF + the 
expected text is one of the highest-leverage contributions.

- **Benchmarks.** Compare OpenCR against Tesseract / Surya / 
PaddleOCR / Marker on a Turkish corpus and post the table — even 
informal numbers are useful.

- **Model-backend ports.** MLX, llama.cpp, ONNX, or any other runtime 
that improves throughput on a target platform.

- **Translations.** README and dataset cards in additional languages.

## Setup

```bash
git clone https://github.com/cdliai/opencr.git
cd opencr
make install
make test
```

`make run` starts a local dev server on http://localhost:39672 with the `local` model backend (no GPU needed; ~5–30 s/page on M-series Macs).

## Code style

- Python: keep it boring and explicit. Type hints on public functions. No new dependencies without a brief rationale in the PR.

- Frontend: stays Alpine + plain CSS until the state model genuinely outgrows it. No build step, no framework rewrite.

- Tests: every new code path should have a unit or integration test. We use `pytest` and `pytest-asyncio`.

## Pull request flow

1. Open an issue first for non-trivial changes — a 5-line discussion saves a 500-line rewrite.

2. Branch from `main`, name it `feat/...` or `fix/...`.

3. Run `make lint test` before pushing.

4. PR description: what changed, what it fixes, how to verify locally.

## Reporting OCR-quality regressions

If a particular PDF regresses after a change, please attach 
(or link to a public copy of) the PDF, the page number, what 
OpenCR produced, and what was expected. Quality bugs without 
a reproducer are very hard to act on.

## Code of conduct

Be respectful. We're a small project trying to do useful work for 
Turkish-language NLP — no room for harassment or 
discrimination here.

## License

By submitting a PR, you agree your contribution is licensed under the project's [Apache 2.0 License](./LICENSE).
