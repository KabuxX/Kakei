# Bundled Tokyo basemap

This is a manual acquisition procedure. Runtime, Vite builds and CI never download map data.

The fixed Protomaps 20261004 build (tileset 4.15.2) is extracted for `[138.90,35.45,139.95,35.95]`, zoom 0–14. Display may overscale to zoom 16. The unchanged extract was 67,063,138 bytes, above the 50 MiB cap. The derivative removes only unused `buildings` and `pois` MVT layers; all retained layer protobuf bytes (features, labels and geometry) are copied unchanged before gzip recompression. Roads include railway geometry. Building footprints, POI icons and station POI labels are absent. Major place, road and water Japanese names remain. The final PMTiles is 44,888,591 bytes.

Exact versions: go-pmtiles 1.31.2, MapLibre GL JS 6.12.0, pmtiles 4.5.0, @protomaps/basemaps 5.7.2. CLI official Darwin arm64 ZIP SHA256: `40528f7f616fcbf91207cd48c8fc023d213f6d86c0cbf1f748732803d1880f3d`. Download from https://github.com/protomaps/go-pmtiles/releases/download/v1.31.2/go-pmtiles-1.31.2_Darwin_arm64.zip and verify that digest before using the executable. Other platforms must verify their official release asset digest.

From the repository root, with the verified CLI on PATH:

```sh
pmtiles extract https://build.protomaps.com/20261004.pmtiles /tmp/tokyo-original.pmtiles --bbox=138.90,35.45,139.95,35.95 --minzoom=0 --maxzoom=14
pmtiles verify /tmp/tokyo-original.pmtiles
node tools/demo/prepare-map.mjs repack /tmp/tokyo-original.pmtiles front/demo/public/maps/tokyo.pmtiles
pmtiles verify front/demo/public/maps/tokyo.pmtiles
node tools/demo/prepare-map.mjs validate
```

A regeneration must match the committed manifest hashes and bounds, or be reviewed and update the manifest explicitly. The dated upstream archive may eventually expire; committed bytes keep builds reproducible. CLI verifies archive structure; tests also use the official PMTiles JS reader to load a tile.

Noto Sans JP is an unmodified Google Fonts variable TTF at commit `9710da1eacb3be272583c3224dcb70f9da6eadbb`. Download font and OFL from:

- https://raw.githubusercontent.com/google/fonts/9710da1eacb3be272583c3224dcb70f9da6eadbb/ofl/notosansjp/NotoSansJP%5Bwght%5D.ttf
- https://raw.githubusercontent.com/google/fonts/9710da1eacb3be272583c3224dcb70f9da6eadbb/ofl/notosansjp/OFL.txt

Save as `front/demo/public/maps/fonts/NotoSansJP.ttf` and `licenses/OFL.txt`. MapLibre v6 `font-faces` loads this same-origin font for Japanese, Latin and digits. No glyph server or sprites are needed by the retained style. See committed manifest for bytes, SHA256, provenance and geographic containment evidence. OSM attribution and license notice are in `licenses/MAP-LICENSE.txt`; font redistribution includes full OFL.

The Tokyo mainland rectangle was checked against MLIT N03-2025 Tokyo administrative polygon bounds, excluding island polygons (minimum latitude >35 degrees). The manifest records the downloaded boundary ZIP URL/digest and derived bounds. This boundary dataset is evidence only, not bundled tile content.

Resource validation checks actual committed hashes, required files and the 50 MiB archive cap. The archive source rejects off-site URLs and redirects, validates exact 206 ranges and actual streamed byte counts, shares a bounded full-file fallback on 200, and permits retries after failures. Aborting a consumer stops that consumer while another reader can continue.

Committed SHA256 values:

| File | SHA256 |
| --- | --- |
| tokyo.pmtiles | `58fd640e5db40348f95435aa25914c7e935bb0c59184f46d3f1b9601dc8ffdb3` |
| NotoSansJP.ttf | `c2f3b4d463500a2ddcd3849cded1fceeb9fd6d1c32e6cbecd568453ba50fc68f` |
| OFL.txt | `1c05c68c34f9708415aada51f17e1b0092d2cea709bf4a94cd38114f9e73d7d9` |
| MAP-LICENSE.txt | `164ed44ed282a5a49b1a01553a50aaa0f16dc927db0cc42305ad227a6a1e107e` |

All 12 places referenced by snapshot events/leg viaPlaceIds fit this rectangle. The retained snapshot also has an unused Fukuoka place (`temp:doutor_nishitetsu_fukuoka_station`); it has zero visits and is recorded in `unusedOutsidePlaces`, without deleting data or expanding the Tokyo map. Address-context null coordinates are not canonical map points. Validation rejects any referenced outside point.
