# P3B — Camera-first barcode scanner contract

## Purpose

P3B hardens the existing physical-copy barcode workflow without changing the
domain model. OwnedCopy.barcode remains the persistent local mapping and
BoardGame.bgg_id remains the game identifier.

The normal path is camera-first:

Scansiona -> camera -> decode -> automatic local lookup

Manual barcode entry remains available as a fallback, not the primary path.

## In scope

- Auto-start the camera when the scanner dialog opens and camera APIs are usable.
- Prefer the native BarcodeDetector API when it can decode the required formats.
- Fall back locally to pinned, vendored @zxing/browser when native detection is unavailable.
- Restrict decoding to EAN-13, EAN-8, UPC-A and UPC-E.
- Preserve ISBN compatibility through its EAN-13 representation where applicable.
- Prefer an environment-facing camera and request a useful HD capture size.
- Apply continuous autofocus only when the selected track reports support.
- Stop every scan loop and media track after a result, dialog close, or manual stop.
- Prevent duplicate handling of the same frame/result with a per-session detection lock.
- Distinguish permission denied, no camera, busy camera and insecure-context failures.
- Keep existing known-barcode and unknown-barcode association behavior unchanged.
- Keep manual lookup operational even if every camera path fails.

## Dependency rule

@zxing/browser is pinned to 0.2.1 and served from BoardGameCompanion itself.
There is no runtime CDN dependency. Its MIT license and the bundled
@zxing/library license are retained beside the vendored asset.

## Out of scope

- External EAN/UPC product databases.
- Treating a BGG product code as a UPC/EAN/ISBN.
- Automatic reassignment of an already-barcoded physical copy.
- BGG credentials or metadata enrichment.
## Acceptance criteria

1. Opening the scanner attempts camera scanning without another button press.
2. A successful native scan fills the barcode and starts lookup automatically.
3. A browser without BarcodeDetector can scan through ZXing.
4. Native runtime detector failure can hand the existing stream to ZXing.
5. Camera failure exposes manual entry immediately and reports an actionable reason.
6. Closing the dialog releases camera resources.
7. Existing manual barcode tests and copy persistence tests remain green.
8. Static packaging serves the vendored scanner asset in installed builds.
9. CI includes browser tests for the native and fallback paths at the level possible
   without a physical camera.
