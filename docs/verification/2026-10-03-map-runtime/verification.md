# Runtime map configuration — 2026-10-03

## Cause and repair

The previous build explicitly cleared `VITE_MAPBOX_ACCESS_TOKEN`. The root `.env` still contained a public token, but the compiled map component depended on a build-time value, so restarting FastAPI could not restore the map.

The map now retrieves `/api/map-config` from FastAPI. The endpoint exposes only a `pk.` public Mapbox token, is available before database initialization, enforces the existing local Host checks, and returns `Cache-Control: no-store`. Missing, malformed, and secret `sk.` values produce null. The frontend shows a loading state, supports retry after configuration-fetch failure, ignores late responses after unmount, and initializes layers/markers/bounds once the runtime token arrives. Mock development mode supplies the same response shape from Vite's server environment.

Root `.env` changes require a server restart and page reload; they no longer require a frontend rebuild.

## Verification

- Red/green tests reproduced missing runtime configuration before implementation.
- Backend: 184 passed. Includes public-only response, initialization independence, missing/secret token rejection, and external Host rejection.
- Frontend: 97 passed. Includes asynchronous map initialization with paths/markers/bounds, configuration retry, late-response cleanup, and existing map selection/date/error behavior.
- Browser: 17 passed using disposable SQLite.
- Normal production build passed. A value comparison verified that Mapbox, OpenAI and Geoapify keys from `.env` do not appear in the JavaScript artifacts. No token values were logged.
- Actual application restarted from main at localhost:8765. Real Mapbox browser check after network settled: one canvas, three numbered markers, two visible colored path segments, 210 Mapbox responses without HTTP failures, no page errors or map error message.
- Desktop 1440×1000 and phone 390×844 (map-region capture) screenshots inspected. Japanese labels, basemap, markers and lines are visible. Browser uses software WebGL; no physical-device check.
- `git diff --check` passed. Existing large Mapbox bundle warning and backend SQLite ResourceWarnings remain.

[Desktop](desktop.png) · [Phone](phone.png)
