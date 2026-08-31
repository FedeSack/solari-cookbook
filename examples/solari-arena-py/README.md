# Solari Arena (Python)

OSWorld-style eval of a canvas-painted clinic worklist. CDP locators miss a
corner CTA (no named AX node; Playwright clicks the canvas centre). Screenshot
vision and desktop mouse can hit the same control. A FILE or HTTP oracle
scores the right claim vs a side-effect on the other one.

The portal is written onto the VM at runtime (`files.write`, a stdlib HTTP
server, a preview URL), same pattern as `sandbox-port-preview-ts`. Watermarked
SYNTHETIC. No PHI, no real payers.

## Hypothesis

CDP locators fail on this worklist. Playwright actionability is visible +
stable + elementFromPoint, and `locator('canvas').click()` aims at the centre.
The Process button is paint in a corner, so that click misses. A DOM overlay
covers the centre, so the click is often refused before it lands.

Pixel policies can finish the goal. We do not silently fail over from CDP to
vision; each policy is scored on its own. The oracle is claim JSON, not an LLM.

On the Free 1-VM cap: pause, then `fromSnapshot`, so the original stays
inspectable. If that 429s, kill and `fromSnapshot`. If desktop create returns
402, fall back to sandbox + browsers. Do not fake a GUI.

## Method

1. Boot one VM (desktop if entitled, else sandbox). 1 vCPU / 2 GiB. Write the
   portal at runtime; Free has no custom templates.
2. Preview URL, same as `sandbox-port-preview-ts`.
3. CDP locators on the original (DPR 1, no stealth). Login is real DOM and
   must pass. The worklist should miss (`FAIL_CANVAS_CLICK_MISS` /
   `FAIL_SOM_NO_DOM`). Set-of-Mark needs DOM; a canvas CTA has none.
4. Snapshot (`POST /sandboxes/:id/snapshots`). `record: true` is fine on this
   golden boot. Combined with `fromSnapshot` it is 400
   `RecordingRequiresGoldenBoot`.
5. Pause or kill the original. Free is one concurrent VM; do not keep original
   and fork live.
6. In-browser vision and desktop mouse run only on the fork, serial (Free = 3
   browsers + 1 VM). Vision is a screenshot plus a click in that pixel space.
   `page.evaluate` / `dispatchEvent` is not vision. `streamUrl` is raw RFB/VNC;
   never Playwright.
7. Promote the write only if the right claim JSON changed, the other claim is
   untouched, and the paused original still matches its baseline. Otherwise
   `FAIL_WRONG_CLAIM`, `FAIL_NO_MUTATION`, or `FAIL_ORIGINAL_MUTATED`.
8. OOD: same task, CTA shifted 80px toward the canvas centre. A cached in-dist
   click is `FAIL_OOD_SHIFT`. An illegible frame is `HALT_ILLEGIBLE` (no click).

Dual scores, printed per policy:

- `success`: right claim mutated to `processed`
- `side_effect_clean`: wrong claim untouched

Reason codes: `PASS_ORACLE`, `FAIL_WRONG_CLAIM`, `FAIL_NO_MUTATION`,
`FAIL_ORIGINAL_MUTATED`, `HALT_ILLEGIBLE`, `FAIL_CANVAS_CLICK_MISS`,
`FAIL_SOM_NO_DOM`, `FAIL_COORD_SPACE`, `FAIL_OOD_SHIFT`, `ABORT_CONCURRENCY`,
`ABORT_STREAM_NOT_PLAYWRIGHT`.

## Limitations

- Free serial schedule: one VM, three browser slots, policies in sequence.
- Browser replay retention is 1 day. Recording is per session; the upload is
  async after release, so poll about 30s. `GET /sessions/:id` is not VM health;
  desktops use `desktop.health()`.
- Desktop is a paid entitlement. A 402 here means sandbox + browsers, not a
  fake GUI.
- Pixel vision is a colour-blob centroid. Recolour the CTA and it misses, the
  same way a locator misses a renamed button.
- The TypeScript `solari.close()` hang does not apply; this is Python.

## Run

```bash
cd examples/solari-arena-py
pip install -r requirements.txt
pytest                       # no key: skips live, unit tests still pass
export SOLARI_API_KEY=slr_live_...   # https://console.getsolari.com
python main.py                # shortest serial; prints the reason-code table
```

Without a key, `main.py` prints `inconclusive` and does not call the API. The
GitHub Action runs `pytest` with `SOLARI_API_KEY` empty. Never print or commit
the key.

Source: [`main.py`](main.py), [`arena/`](arena/), [`portal/`](portal/), [`tasks/`](tasks/).
