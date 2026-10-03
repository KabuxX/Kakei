# Receipt item tax calculation — 2026-10-03

## Behavior

- Structured extraction keeps printed item amounts, tax group references, tax basis/rate, printed group subtotals/tax, gross total, after-total reduction and actual payment separate.
- Backend allocates each exclusive group's printed tax by item amount using integer largest remainders; ties follow receipt order. Inclusive and exempt items receive no added tax.
- After-total reduction is allocated over all gross items, including exempt items, as household expense allocation. This does not change the recorded tax calculation.
- The original extraction and calculation evidence are retained in the receipt review/proposal metadata. Existing transaction items remain name/amount pairs; no database migration is required.
- Review and saved proposal display printed amount, added tax, gross, allocated reduction and recorded amount. Manual edits are explicitly distinguished from the original calculation.
- Unknown tax basis/rate, inconsistent subtotals/tax/total/payment, and nonpositive results do not yield an automatic draft. Users must check the original and correct the transaction fields. Unsupported currency also requires review; saving remains JPY-only.
- Legacy receipt reviews without tax evidence retain the existing manual correction flow. Previous cached extractions are not recomputed.

## Supplied receipt

| Item | Printed | Added tax | Gross | Reduction | Recorded |
|---|---:|---:|---:|---:|---:|
| Rice ball | 130 | 10 | 140 | 3 | 137 |
| Cola | 140 | 11 | 151 | 3 | 148 |
| Nail polish | 300 | 30 | 330 | 6 | 324 |
| Tobacco (inclusive) | 490 | 0 | 490 | 9 | 481 |
| Stamp (exempt) | 50 | 0 | 50 | 1 | 49 |
| Total | 1,110 | 51 | 1,161 | 22 | 1,139 |

The configured `gpt-6-luna` model extracted the supplied image and the deterministic calculation produced these values. Inclusive 10% group tax was correctly left null because its individual internal tax is not separately printed. Test calls did not save any business transactions.

## Verification

- Backend full suite: 181 passed.
- Frontend full suite: 90 passed.
- Browser suite: 16 passed, disposable SQLite and deterministic model fixture. Covers review, approval, actual saved item values, receipt attachment and reloaded calculation evidence.
- Production build succeeded with an empty Mapbox build token. Existing large map bundle warning remains.
- `git diff --check` passed.
- Initial sandboxed frontend run failed because localhost listeners were blocked; the permitted rerun passed. Existing SQLite ResourceWarnings remain in the backend suite.
- Desktop 1440×900 and phone 390×844 screenshots inspected; calculation cards wrap to two columns on phone without page overflow. History remains scrollable above the composer. Physical device testing was not performed.

[Desktop](desktop.png) · [Phone](phone.png)

A second live check ran the entire production `AgentRunner` receipt turn against a disposable database: completed in 25.2 seconds, prepared amount 1,139 yen, no calculation issues, zero saved business rows. This also verified the existing 60-second turn limit for the supplied sample.
