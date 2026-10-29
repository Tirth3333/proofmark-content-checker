# Test results

All results below were produced by actually running the suites in the development environment on **2026-10-29** (Python 3.13.18, Node 22.23.4, Linux). Nothing here is claimed without being executed.

## Summary

| Suite | Command | Result |
|---|---|---|
| Backend (pytest) | `cd backend && python -m pytest -v` | **46 passed**, 0 failed (0.74 s) |
| Frontend unit + component (Vitest, React Testing Library) | `cd frontend && npm test` | **22 passed**, 3 skipped (integration suite needs `API_URL`) |
| Frontend-to-backend integration (Vitest against live FastAPI) | `API_URL=http://127.0.0.1:8000 npm test` | **25 passed** (22 + 3 live), 0 failed |
| TypeScript | `npx tsc -b` | no errors |
| Lint | `npx oxlint src` | no warnings |
| Production build | `npm run build` | succeeds |
| Browser smoke test (Playwright, headless Chromium) | `python e2e/ui_smoke.py` | passed: demo loaded, analyzed, 2 fixes accepted, revised text asserted, no console errors (web-font requests were blocked by the sandbox and excluded) |

Not executed: `docker build` (Docker is installed but no daemon was available in this environment) and any live call to a real LLM or search provider (no keys available; those paths are covered by mocked-transport tests).

## Coverage of the required scenarios

| Requirement | Where tested |
|---|---|
| Empty and invalid input | `test_api_validation`, App: *disables Analyze for empty input*, integration: *rejects empty content* |
| Very short and long content | `test_api_short_content_note`, `test_long_content_is_handled` (60k+ chars), App: *blocks content over the server limit* |
| Repeated phrases / ideas | `test_repeated_phrase_detected`, `test_repeated_idea_across_paragraphs` |
| Vague wording | `test_vague_and_filler_with_replacements` |
| Factual claims requiring sources | `test_claim_types_detected`, `test_attribution_lowers_severity` |
| Content with no factual claims | `test_no_claims_in_clean_text`, `test_clean_text_has_few_quality_findings` |
| Brand voice rules | `test_preferred_and_avoid_terms`, `test_formal_tone_expands_contractions`, `test_unsupported_claims_rule_only_when_enabled`, `test_style_drift_against_example`, `test_brand_requires_user_rules` |
| Search intent input | `test_keyword_missing_and_present`, `test_missing_sections_for_how_to`, `test_internal_links_only_from_supplied_urls`, `test_cta_missing_for_conversion_objective`, `test_no_brief_no_intent_findings` |
| Accept and reject | lib: *applies accepted replacements…*, *ignores rejected…*; App: *accepts / rejects / undoes / restores*, *write their own fix* |
| Original text preservation | lib: *never mutates the original*; App test checks the editor still holds the original; backend `test_every_replacement_keeps_unrelated_text` |
| Undo / restoration | App: *…undoes / restores*; lib: *returns the original unchanged when nothing is accepted* |
| Overlapping edits | lib: *reports overlapping accepted edits as conflicts* |
| Export functionality | lib: CSV (escaping + formula injection), Markdown report, PDF blob; App: *exports the findings CSV and report* |
| Missing AI credentials | `test_missing_ai_credentials_falls_back` |
| AI provider failures | `test_ai_provider_failure_keeps_rule_findings`, `test_ai_invalid_json_is_an_error` |
| Fabricated AI evidence / URLs | `test_ai_findings_validated_against_original`, `test_brand_ai_findings_dropped_without_brand_brief` |
| Source verification honesty | `test_sources_only_from_search_api`, `test_empty_search_never_marks_false` |
| URL extraction errors | `test_extract_errors` (robots.txt 403, HTTP 404, non-HTML 415, JS-only page 422), `test_extract_timeout`, `test_extract_rejects_bad_and_private_urls` |
| Frontend-to-backend integration | `src/test/integration.test.ts` against the running API; Playwright smoke test |

## Bugs found by testing and fixed

1. Removing a sentence-opening filler phrase followed by a comma left `", choosing…"` in the revised text. Found in the browser smoke test; fixed in `removal_edit`; regression tests `test_removal_edit_consumes_trailing_comma` and `test_every_replacement_keeps_unrelated_text`.
2. A short unfinished final line was treated as a heading, so the cut-off ending was missed. Fixed in `is_heading`.
3. "the first Saturday" was flagged as a ranking claim. Ranking detection now requires an entity (e.g. "the first company to…").
4. The URL form's native browser validation suppressed the app's own error message. Fixed with `noValidate`.

## Raw output

### pytest -v

```
test_analyzers.py::test_sentences_keep_offsets_and_abbreviations PASSED
test_analyzers.py::test_paragraphs_and_stats PASSED
test_analyzers.py::test_removal_edit_recapitalises_sentence_start PASSED
test_analyzers.py::test_repeated_phrase_detected PASSED
test_analyzers.py::test_repeated_idea_across_paragraphs PASSED
test_analyzers.py::test_vague_and_filler_with_replacements PASSED
test_analyzers.py::test_superlative_unsupported_vs_supported PASSED
test_analyzers.py::test_guarantee_and_placeholder_and_cutoff PASSED
test_analyzers.py::test_inconsistent_terminology_suggests_majority_form PASSED
test_analyzers.py::test_clean_text_has_few_quality_findings PASSED
test_analyzers.py::test_long_content_is_handled PASSED
test_analyzers.py::test_claim_types_detected PASSED
test_analyzers.py::test_no_claims_in_clean_text PASSED
test_analyzers.py::test_attribution_lowers_severity PASSED
test_analyzers.py::test_no_brief_no_intent_findings PASSED
test_analyzers.py::test_keyword_missing_and_present PASSED
test_analyzers.py::test_missing_sections_for_how_to PASSED
test_analyzers.py::test_internal_links_only_from_supplied_urls PASSED
test_analyzers.py::test_cta_missing_for_conversion_objective PASSED
test_analyzers.py::test_brand_requires_user_rules PASSED
test_analyzers.py::test_preferred_and_avoid_terms PASSED
test_analyzers.py::test_formal_tone_expands_contractions PASSED
test_analyzers.py::test_unsupported_claims_rule_only_when_enabled PASSED
test_analyzers.py::test_style_drift_against_example PASSED
test_analyzers.py::test_removal_edit_consumes_trailing_comma PASSED
test_analyzers.py::test_every_replacement_keeps_unrelated_text PASSED
test_services.py::test_missing_ai_credentials_falls_back PASSED
test_services.py::test_ai_provider_failure_keeps_rule_findings PASSED
test_services.py::test_ai_invalid_json_is_an_error PASSED
test_services.py::test_ai_findings_validated_against_original PASSED
test_services.py::test_anthropic_provider_shape PASSED
test_services.py::test_brand_ai_findings_dropped_without_brand_brief PASSED
test_services.py::test_sources_only_from_search_api PASSED
test_services.py::test_empty_search_never_marks_false PASSED
test_services.py::test_extract_html PASSED
test_services.py::test_extract_errors[case 1] PASSED
test_services.py::test_extract_errors[case 2] PASSED
test_services.py::test_extract_errors[case 3] PASSED
test_services.py::test_extract_errors[case 4] PASSED
test_services.py::test_extract_timeout PASSED
test_services.py::test_extract_rejects_bad_and_private_urls PASSED
test_services.py::test_html_to_text_falls_back_to_body PASSED
test_services.py::test_api_validation PASSED
test_services.py::test_api_short_content_note PASSED
test_services.py::test_api_demo_end_to_end PASSED
test_services.py::test_api_is_deterministic PASSED
============================== 46 passed in 0.74s ==============================
```

### vitest --reporter=verbose (with API_URL set)

```
 ✓ src/test/App.test.tsx > App > disables Analyze for empty input and shows live counts
 ✓ src/test/App.test.tsx > App > blocks content over the server limit
 ✓ src/test/App.test.tsx > App > analyzes, highlights evidence, and accepts / rejects / undoes / restores
 ✓ src/test/App.test.tsx > App > lets the user write their own fix for an advisory finding
 ✓ src/test/App.test.tsx > App > filters findings by category and severity
 ✓ src/test/App.test.tsx > App > shows rule-based mode and the checks that need AI
 ✓ src/test/App.test.tsx > App > shows the server error message when analysis fails
 ✓ src/test/App.test.tsx > App > shows URL extraction errors and fills the editor on success
 ✓ src/test/App.test.tsx > App > loads the labelled demo article and brief
 ✓ src/test/App.test.tsx > App > exports the findings CSV and report
 ✓ src/test/lib.test.ts > applyDecisions > returns the original unchanged when nothing is accepted (restoration)
 ✓ src/test/lib.test.ts > applyDecisions > applies accepted replacements only to their own spans
 ✓ src/test/lib.test.ts > applyDecisions > ignores rejected findings and advisory findings
 ✓ src/test/lib.test.ts > applyDecisions > never mutates the original string or findings
 ✓ src/test/lib.test.ts > applyDecisions > reports overlapping accepted edits as conflicts instead of overwriting
 ✓ src/test/lib.test.ts > applyDecisions > uses a user-written fix, including for advisory findings
 ✓ src/test/lib.test.ts > applyDecisions > skips findings whose evidence no longer matches the text
 ✓ src/test/lib.test.ts > text helpers > counts words, characters and paragraphs
 ✓ src/test/lib.test.ts > text helpers > splits overlapping highlights into segments that rebuild the text exactly
 ✓ src/test/lib.test.ts > exports > builds a CSV with one row per finding, escaping and formula protection
 ✓ src/test/lib.test.ts > exports > builds a Markdown report with evidence, decisions and limitations
 ✓ src/test/lib.test.ts > exports > makes text safe for the PDF font and produces a PDF blob
 ✓ src/test/integration.test.ts > integration with live backend > health endpoint responds
 ✓ src/test/integration.test.ts > integration with live backend > analyzes the demo, every evidence span matches the text, and accepted fixes apply cleanly
 ✓ src/test/integration.test.ts > integration with live backend > rejects empty content with a readable message
 Test Files  3 passed (3)
      Tests  25 passed (25)
```
