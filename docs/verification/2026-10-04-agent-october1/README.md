# October 1 trajectory Agent verification

Date: 2026-10-04. Branch: `feat/geolonia-coordinates`.

## Exact live request

Sent `2026年10月1日の取引記録によって、軌跡を作って` to the actual local Agent, using the existing application configuration and transaction database. No proposal was approved or saved. Raw logs remain outside the repository because they contain transaction identifiers and financial data.

The baseline returned a pending two-visit draft after 100.8 seconds, but both place groups had no selectable coordinates and no unlocated stores or citations. Intermediate retests exposed variable warning wording and unsupported published coordinate formats.

The successful retest returned HTTP 200 in 73.2 seconds with a pending `trajectory.create` proposal:

| Visit | Transaction merchant | Published candidate | Coordinate result |
| --- | --- | --- | --- |
| 08:45 | セブン-イレブン 千代田店 | セブン-イレブン 千代田二番町店 | one published, source-bound point |
| 12:45 | FamilyMart | ファミリーマート一の橋店 | one published, source-bound point |

The proposal contains both transaction-linked visits in time order and one connecting leg with its mode unset. Both candidate groups have `status=found`. The Seven-Eleven candidate retains `branch_unconfirmed` and an explicit branch-name confirmation note. Both retain warnings about the historical location and entrance accuracy. Comparing the day trajectory before and after the request confirmed no saved-data change.

Geolonia ran first for both grounded transaction addresses. Its results remained supplemental: Seven-Eleven recognized the address at level 8 but had point level 3; FamilyMart had only level 3/address uncertainty. Neither representative point became selectable. Web fallback fetched the public pages and read each GeoJSON point from a feature whose own name and address matched the discovered store.

The final address-safety corrections were then checked against fresh public fetches of both pages; they still returned the same independently bound points:

- [Seven-Eleven MapFan page](https://mapfan.com/spots/SCQY5%2C1SF%2CFTT): longitude 139.73405127029, latitude 35.685769259459.
- [FamilyMart MapFan page](https://mapfan.com/spots/SCQY5%2C1S6%2C6J): longitude 139.73637648921, latitude 35.656702427323.

These are currently published positions, not proof of the stores' October 1 locations or entrances. The live Agent reply describes the lack of detailed address coordinates; the proposal separately records successful Web published points. Search-provider results and the final wording can vary between runs. The stored candidate evidence is the authority for which coordinates were retrieved.

## Fixes and guards

- Normalize known FamilyMart language variants and Seven-Eleven hyphen variants for merchant identity, including transaction grounding and coordinate conflict comparison. Preserve original names in the proposal.
- Allow a bounded abbreviated branch only with the matching grounded address; preserve the branch uncertainty for human confirmation. Different brands, unrelated branches, and other addresses remain excluded.
- Extract historical-location, branch-label, and building-relation warnings as validated categories. Identity/address conflicts remain blocking `unresolved` issues. Warning wording no longer controls whether current-coordinate verification runs.
- Preserve discovered unlocated stores and their citations on search/provider limits. Pipeline v3 invalidates reuse of earlier search behavior.
- Read embedded JSON GeoJSON features only when their own name/address, Point geometry, coordinate values and coordinate system are acceptable. No geocoding API or invented coordinate is used. [RFC 7946](https://www.rfc-editor.org/rfc/rfc7946) defines the accepted default geographic coordinate system; explicit alternate CRS data is rejected.
- Try up to three known public map-detail pages actually discovered by Web research when extraction omitted their URLs. Each still needs independent identity verification.
- Avoid joining phone numbers into house numbers during HTML matching. Structured addresses use exact address comparison; spaced house-number extensions and conflicting postal codes remain excluded.

## Verification

- `backend/.venv/bin/python -m unittest discover -s backend/tests`: 365 passed.
- In `front`, `npx playwright test --config=playwright.agent.config.cjs tests/e2e/geolonia-coordinates.spec.cjs tests/e2e/web-coordinates.spec.cjs tests/e2e/agent-delete.spec.cjs`: 5 passed. These tests use a disposable fixture server and cover candidate confirmation, saving/reloading coordinate provenance, and trajectory deletion review.
- `git diff --check`: passed.

Regression tests were observed failing before the relevant fixes, including warning handling, missing unlocated results, merchant variants, omitted discovered map URLs, embedded GeoJSON, telephone adjacency, and postcode boundaries. Backend tests use isolated fixtures. Existing database ResourceWarnings and Playwright's color-environment warning remain; they do not fail the tests.

One independent reviewer checked the changes, reproduced missed normalization conflict grouping and Geolonia branch metadata, then reviewed the later public-page parser changes and reproduced spaced-number/postcode safety gaps. All findings were fixed with regressions. Their final focused verification passed 20 fetched-coordinate tests and 15 Geolonia-search tests, with no remaining actionable findings. They did not independently establish the live request result, historical store locations, or full-suite completion; the live records and commands above supply the applicable evidence.
