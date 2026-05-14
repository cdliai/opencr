# Ottoman and Turkish OCR Research Brief

This note describes the current OpenCR pipeline and frames the research question we need help with: how to get more reliable OCR and structured text from Turkish, old Turkish, Latinized Ottoman, and Ottoman-script material without making the operator workflow heavy or over-engineered.

## Current System

OpenCR is a GPU-first OCR workbench. A user uploads or registers PDF documents, groups them, edits document-level metadata, runs OCR, inspects page images beside extracted text, and exports the result for corpus work or model training.

The current OCR path is:

1. Register PDFs in a document catalog.
2. Store document metadata such as title, author, work, book, date label, date precision, language, script, license, citation, notes, and group path.
3. Render each PDF page to an image.
4. Send the page image to DeepSeek-OCR-2 through the vLLM/OpenAI-compatible backend.
5. Clean the OCR text conservatively.
6. Validate the page for obvious extraction failures and corpus-quality warnings.
7. Store per-page metadata, quality flags, raw text, clean text, markdown, source PDFs, OCR image/text pairs, and text bundles.
8. Export HuggingFace-friendly datasets.

The system intentionally keeps the pipeline small. It does not try to silently "fix" historical text into modern Turkish. The goal is to preserve historical orthography, diacritics, transliteration choices, and document provenance.

Relevant implementation areas:

- `ocr_pipeline/services/batch_processor.py`: page rendering, OCR calls, retry strategy, validation, metadata collection.
- `ocr_pipeline/services/ocr_engine.py`: OpenAI-compatible client for vLLM or another GPU model server.
- `ocr_pipeline/services/output_validator.py`: page-level validation and quality flags.
- `ocr_pipeline/services/text_cleaner.py`: conservative OCR cleanup.
- `ocr_pipeline/services/text_normalizer.py`: optional NLP-oriented normalization for exported text only.
- `ocr_pipeline/services/text_bundle_exporter.py`: raw, clean, and normalized text bundles.
- `ocr_pipeline/services/ocr_pair_exporter.py`: page image plus text pairs for OCR model fine-tuning.
- `ocr_pipeline/services/dataset_exporter.py`: HuggingFace-style page/document dataset export.

## Model Context

OpenCR now uses `deepseek-ai/DeepSeek-OCR-2` as the base model. The model is distributed on HuggingFace with Apache-2.0 license metadata, is listed as a 3B BF16 image-text-to-text model, and supports Free OCR plus grounded markdown prompts. The DeepSeek-OCR-2 paper introduces DeepEncoder V2 / Visual Causal Flow, where visual tokens can be reordered by document semantics instead of being forced through a fixed raster-scan order. That makes it a better first candidate for complex pages, but not a substitute for domain-specific Ottoman/Turkish benchmarking.

The vLLM recipe for DeepSeek-OCR-2 documents OpenAI-compatible online serving with `vllm serve deepseek-ai/DeepSeek-OCR-2`, the custom `NGramPerReqLogitsProcessor`, disabled prefix caching, and multimodal image prompts. That matches OpenCR's GPU-first runtime direction.

For Ottoman Turkish, the research risk is larger than plain OCR accuracy. Arabic-script Ottoman has right-to-left script behavior, ligatures, weak or ambiguous vowel representation, historical fonts, and no clean one-to-one mapping into modern Latin Turkish. Prior work on Ottoman periodicals emphasizes that transcription into a Latin writing system is itself a modeling choice, not merely a character-recognition task.

## What We Already Preserve

OpenCR keeps separate text layers:

- `raw`: the model output after only minimal capture.
- `clean`: conservative cleaned text for reading and corpus publication.
- `normalized`: optional NLP-oriented text, currently used only in text-bundle exports.

This split matters. For scholarly work, `clean` should remain close to what OCR produced. `normalized` can join broken line hyphenation, remove simple markup leaks, and make tokenization easier, but it must not replace the archive-facing text.

OpenCR also stores:

- source PDF SHA256,
- source filename,
- model name,
- pipeline version,
- extraction mode,
- extraction attempt,
- DPI,
- page status,
- validation issues,
- quality flags,
- language/script metadata,
- project attribution through OpenCR/cdli.ai metadata.

Current quality flags include visible corpus warnings such as line-break hyphenation and markup leakage. These are not the same as "OCR is wrong"; they mean the page should not be treated as ground truth without review.

## Main Research Question

How can we improve OCR accuracy and corpus usefulness for Turkish, old Turkish, Latinized Ottoman, and Ottoman-script documents while preserving historically meaningful forms and keeping the OpenCR workflow benchmarkable and repeatable?

## Questions To Investigate

1. Which DeepSeek-OCR-2 prompt and image settings work best for our material?

   Compare Free OCR, grounded markdown, crop mode on/off, image sizes, and DPI values. Measure separately for Latinized Ottoman, modern Turkish Latin, Arabic-script Ottoman, tables, title pages, and degraded scans.

2. When should we use OCR, HTR/ATR, or a specialist engine?

   DeepSeek-OCR-2 is useful as a general vision-language OCR model. Kraken/eScriptorium-style ATR may be better for historical and non-Latin scripts when trained or fine-tuned on our domain. We should compare rather than assume one model is best.

3. What is the right target text?

   For Ottoman-script documents, there are at least three possible targets:

   - diplomatic transcription preserving script-level details,
   - scholarly transliteration,
   - modern Turkish normalization.

   These should be separate dataset columns or export layers, not one overwritten text field.

4. Which errors are dangerous for scholarship?

   Aggregate CER/WER is not enough. Historical OCR can silently modernize orthography, normalize rare forms, drop diacritics, or turn historically meaningful spelling into more common contemporary spelling. We need an error taxonomy.

5. How much ground truth is enough?

   Start with a small reviewed set: 20-50 pages chosen across document types, scan quality, script, date, and layout. Manually correct at page or line level, then calculate CER/WER and error categories.

6. What should be corrected automatically?

   Only low-risk transformations should be automatic in `normalized`: line-break hyphen joining, obvious markup removal, whitespace normalization, and page header/footer handling if confidence is high. Orthographic modernization should remain opt-in and separately labeled.

## Evaluation Protocol

Use a small gold set first, then expand only after the measurements are useful.

Recommended first benchmark:

- 10 pages: clean modern Turkish Latin print.
- 10 pages: Latinized Ottoman / early Republican Turkish with extended Latin characters.
- 10 pages: Arabic-script Ottoman print.
- 5 pages: tables, treaties, or structured forms.
- 5 pages: degraded scans or unusual typography.

For every page, store:

- page image,
- source PDF,
- OCR raw text,
- OCR clean text,
- human-reviewed text,
- target convention used by the reviewer,
- reviewer notes,
- CER,
- WER,
- quality flags,
- error categories.

Important error categories:

- character substitution,
- dropped diacritic,
- inserted diacritic,
- word split,
- word merge,
- line-break hyphenation,
- layout-order error,
- header/footer leakage,
- table structure loss,
- script confusion,
- Ottoman-to-modern normalization,
- hallucinated word,
- omitted text.

## Practical Improvements Worth Trying

These are useful without making OpenCR heavy.

1. Add an "evaluation set" mode.

   Let users mark selected pages as evaluation pages and attach reviewed text later. The pipeline can then calculate CER/WER and export a small benchmark bundle.

2. Add extraction profiles.

   Instead of many UI controls, define a few named profiles:

   - `latin_print_fast`
   - `latin_print_careful`
   - `ottoman_arabic_print`
   - `tables_and_forms`
   - `fine_tune_pairs`

   A profile can choose DPI, prompt, crop mode, and validation thresholds.

3. Keep image/text pairs export central.

   Fine-tuning needs page or line images matched with reviewed text. Current OCR pairs are useful, but the strongest version should include `reviewed_text`, `review_status`, and `target_convention`.

4. Add script-aware validation.

   If metadata says `script=latin_extended`, warn when the page is mostly Arabic script. If metadata says Ottoman Arabic script, warn when the extracted text is mostly Latin unless transliteration is the intended target.

5. Add a no-silent-modernization rule.

   Any step that changes historical spelling or transliteration must write to a new layer, not mutate `clean`.

6. Add simple page-level layout labels.

   `prose`, `title_page`, `table`, `mixed`, `index`, `blank`, and `image_only` would help researchers filter outputs and compare OCR modes.

7. Store per-run extraction profile.

   HuggingFace exports should say not only which model was used, but also which extraction profile, DPI, prompt mode, crop mode, and cleanup mode were used.

## What Not To Do Yet

Do not add a large automatic correction pipeline before we have ground truth. It would make the text look cleaner while hiding errors.

Do not collapse Ottoman-script transcription, transliteration, and modern Turkish normalization into one field. They answer different scholarly questions.

Do not judge model quality only from pages that "look readable." A page can be readable and still be bad for named entities, dates, legal terms, diacritics, or rare Ottoman forms.

Do not publish a dataset as research-grade unless it has a reviewed subset and clear quality metadata.

## Suggested Research Deliverable

Ask the researcher to produce:

1. A short survey of OCR/ATR options for Turkish, old Turkish, Latinized Ottoman, and Arabic-script Ottoman print.
2. A recommended transcription target schema.
3. A 20-50 page benchmark design.
4. A CER/WER plus error-taxonomy evaluation plan.
5. Recommended DeepSeek-OCR-2 profile settings to test.
6. A proposal for when to use DeepSeek-OCR-2 versus Kraken/eScriptorium-style specialist ATR.
7. A minimal metadata schema for HuggingFace publication that preserves source, script, date, model, pipeline, and review state.

## Source Notes

- DeepSeek-OCR-2 model card: https://huggingface.co/deepseek-ai/DeepSeek-OCR-2
- DeepSeek-OCR-2 paper: https://arxiv.org/abs/2601.20552
- vLLM DeepSeek-OCR-2 recipe: https://docs.vllm.ai/projects/recipes/en/latest/DeepSeek/DeepSeek-OCR-2.html
- Ottoman Turkish periodical transcription case study: https://arxiv.org/abs/2011.01139
- Kraken documentation: https://kraken.re/main/
- Arabic-script OCR with Kraken case study: https://arxiv.org/abs/2402.10943
- Historical OCR error-pattern study: https://arxiv.org/abs/2602.14524
- Historical newspaper OCR ground-truth example: https://lab.kb.nl/dataset/historical-newspapers-ocr-ground-truth
- Printed Ottoman Turkish OCR study: https://ideas.repec.org/a/tec/techni/v18y2023i1p47-64.html
