# Geolonia-first coordinate search verification

Date: 2026-10-04. Implementation: `feat/geolonia-coordinates`.

## Reproducible checks

- `KAKEI_DB_PATH=/private/tmp/kakei-geolonia-full.sqlite3 backend/.venv/bin/python -m unittest discover -s backend/tests -v`: 345 passed.
- `npm test --prefix backend/geolonia`: 6 passed with the pinned official normalization library and synthetic dataset responses.
- `npm test --prefix front`: 141 passed in 29 files.
- `npm run build --prefix front`: passed. The existing map bundle size warning remains.
- From `front`, `npx playwright test --config=playwright.agent.config.cjs tests/e2e/geolonia-coordinates.spec.cjs tests/e2e/web-coordinates.spec.cjs tests/e2e/agent-delete.spec.cjs`: 5 passed.

Backend tests use isolated SQLite databases. Browser tests run a disposable fixture server on port 8767. The user's running app on port 8765 and its database were not changed; no paid model calls were made.

## Official connection

A temporary script used the actual Python `GeoloniaClient`, Node worker, official library, and `candidate_from_match` against public addresses from the library's example. This is a read-only connection check, not a claim about any store's identity or entrance.

| Input | Result | Address level | Point level | Fetch proofs | Selectable candidate |
| --- | --- | --- | --- | --- | --- |
| 北海道札幌市西区二十四軒二条二丁目3-3 | matched | 8 | 8 | 3 | yes, valid v2 evidence |
| 北海道札幌市西区二十四軒二条二丁目 | coarse | 3 | 3 | 2 | no |

Detailed coordinates: longitude 141.315540696, latitude 43.074206115. Proofs contain the national JSON, versioned city JSON, and the town's exact Range response from the residential-address file, including retrieval times and SHA-256 digests. The coarse response is retained as supplemental information and rejected as a candidate. Fixed fixtures separately cover Web fallback after coarse, missing, unavailable, malformed, and failed Geolonia results.

The initial sandbox-restricted connection returned `geolonia_network`; repeating with authorized network access succeeded. Live data coverage may change. This check does not establish historical store location, store identity, or an entrance point.

## Visual and interaction checks

Inspected the screenshots at desktop 1440×900 and phone 375×812:

- `evidence-*.png`: address coordinate type, matched address, dataset source label, processed-data attribution and CC BY 4.0 link.
- `confirmation-*.png`: confirmation checkbox and selection control remain reachable with keyboard focus; horizontal overflow is absent.
- `trajectory-*.png`: after selection, approval, save and reload, the evidence type, matched address, attribution, entrance limitation and user-confirmed status remain visible.

Switching candidates resets confirmation. Unconfirmed coordinates cannot be selected. Coarse results do not have a radio control. Existing Web published/estimated candidates and reviewed trajectory deletion pass the related browser regression tests.

The Mapbox public token is not configured in the disposable fixture server, so the embedded map displays its configuration placeholder. The existing external map link remains available for checking coordinates. The screenshots include an existing skip-to-main-content focus indicator; visual styling was not changed by this feature.

## Independent review

One fresh-context reviewer inspected the whole branch against the approved specification and plan, and independently reproduced two Important findings. Both were corrected in `1199568`:

- User-message co-occurrence could associate an unrelated address with the requested store. Direct adjacent name/address pairing is now required, and explicitly negated/unknown/unrelated mentions use Web discovery. `test_unrelated_or_negated_user_addresses_require_web_discovery` failed before the fix and passed afterward; the affirmative pair still skips Web.
- Nested malformed worker success data could raise an exception while constructing supplemental results. The entire match/proof structure is now validated at the Python process boundary. `test_nested_malformed_success_is_failed_and_worker_reaped` and `test_nested_malformed_worker_response_falls_back_to_web` failed before the fix and passed afterward; malformed output stops/reaps the worker and Web produces a valid v1 candidate.

The backend suite passed 345/345 after the fix, and official detailed/coarse connections still returned 8/8 and 3/3 respectively. No Critical findings and no behaviors declined for judgment were reported. There was no second review; regression tests verify the fix pass.

Deferred minor: network retry counts/classifications are not separately persisted in attempt history. Retries remain bounded and tested, and address transformations are recorded, but a first-request success and a success after communication retries cannot be distinguished from the saved history.

## Implementation rulings

These decisions were recorded during execution, in this order:

1. Update the existing pipeline constant in `backend/agent/limits.py` rather than duplicate it in `place_search.py`. Cost if wrong: historical-reuse compatibility.
2. Published npm 3.1.3 lacks the retry implementation visible on repository master. The fixed dataset fetcher therefore implements initial request plus two retries. Cost if wrong: redundant requests/time, bounded by tests and deadlines.
3. Permit only numeric `v` query parameters on the fixed dataset endpoint because the official library uses them. Cost if wrong: fetch/provenance compatibility; safe and unsafe queries are tested.
4. Require grounded store/address association before direct candidate creation; an address alone does not establish the requested store name. Cost if wrong: additional Web discovery. Review strengthened enforcement for user messages.
5. Reference-count shared sessions and close them when their last search finishes, with turn-level cleanup as fallback. Cost if wrong: stale processes or lost shared cache; process/parallel tests cover ownership.
