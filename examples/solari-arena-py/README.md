# Solari Arena (Python)

OSWorld-style eval of a canvas-painted clinic worklist. CDP locators miss a
corner CTA (no named AX node; Playwright clicks the canvas centre). Screenshot
vision and desktop mouse can hit the same control. A FILE oracle on the guest
scores the right claim vs a side-effect on the other one.

The portal is written onto the VM at runtime (`files.write`, a stdlib HTTP
server, a preview URL), same pattern as `sandbox-port-preview-ts`. Watermarked
SYNTHETIC. No PHI, no real payers.

## Research note

Question: do CDP locators fail on a worklist whose Process control is paint
in a corner, while a screenshot-centroid and a desktop mouse can finish the
same goal, scored by claim JSON rather than an LLM?

Method: three policies, serial, on the real products. CDP on the original VM.
Vision and desktop on a snapshot-fork (Free is 1 concurrent VM). Promote a
write only if the target claim JSON moved, the decoy did not, and a paused
original still matches its baseline.

What would change our mind: CDP processes CLM-1001 without `force=True`, or
vision clicks a recoloured CTA, or a fork write shows up on the paused
original.

This is not a leaderboard. Dual scores (`success`, `side_effect_clean`) plus
a reason code. Pixel vision is a colour-blob centroid of `#E85D04`. Recolour
the button and the table prints `HALT_ILLEGIBLE`. That fixture lives in
`arena/recolor.py` and is printed by `--dry-run`.

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
4. Snapshot (`POST /sandboxes/:id/snapshots`). Desktop `record: true` and
   browser `recording=True` are extra spend; default off. Opt in with
   `SOLARI_ARENA_REPLAY=1` (legal on the golden boot only). Combined with
   `fromSnapshot` it is 400 `RecordingRequiresGoldenBoot`.
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
   click is `FAIL_OOD_SHIFT`. An illegible or recoloured frame is
   `HALT_ILLEGIBLE` (no click).

Dual scores, printed per policy:

- `success`: right claim mutated to `processed`
- `side_effect_clean`: wrong claim untouched

Reason codes: `PASS_ORACLE`, `FAIL_WRONG_CLAIM`, `FAIL_NO_MUTATION`,
`FAIL_ORIGINAL_MUTATED`, `HALT_ILLEGIBLE`, `FAIL_CANVAS_CLICK_MISS`,
`FAIL_SOM_NO_DOM`, `FAIL_COORD_SPACE`, `FAIL_OOD_SHIFT`, `ABORT_CONCURRENCY`,
`ABORT_STREAM_NOT_PLAYWRIGHT`.

## Limitations

- Free serial schedule: one VM, three browser slots, policies in sequence.
- Browser replay retention is 1 day. Recording is per session and opt-in
  (`SOLARI_ARENA_REPLAY=1`); the upload is async after release, so poll about
  30s. `GET /sessions/:id` is not VM health; desktops use `desktop.health()`.
  `kill()` ends a VM; `close()` only drops the local channel.
- Desktop is a paid entitlement. A 402 here means sandbox + browsers, not a
  fake GUI.
- Pixel vision is a colour-blob centroid. Recolour the CTA and it misses, the
  same way a locator misses a renamed button. See `--dry-run` for the fixture
  table.
- Preview URLs are public. Claim JSON is a file oracle on the guest. GET
  `/api/claims/` still requires the session cookie; the eval does not use that
  route. The login page and synthetic PDF stay reachable.
- Dry-run cost figures are a ceiling from published Free rates
  (`docs.getsolari.com/pricing`, copied 2026-09-01). They are not a live quote.
- The TypeScript `solari.close()` hang does not apply; this is Python.

## Run

Keyless, no API:

```bash
cd examples/solari-arena-py
pip install -r requirements.txt
pytest                       # unit tests; live skipped
python main.py --dry-run     # serial schedule + cost ceiling + recolor table
python main.py               # inconclusive without a key (exit 0)
```

One live shot, later, when a key is in the env. Shortest serial only
(in-dist task). pytest will not take this path unless you also set
`SOLARI_ARENA_LIVE=1`. CI sets `SOLARI_API_KEY` empty.

```bash
export SOLARI_API_KEY=slr_live_...   # https://console.getsolari.com
python main.py                       # spends: 1 VM + browsers, no record
```

`SOLARI_ARENA_REPLAY=1` turns on desktop `record` (golden boot only) and
browser `recording`. Leave it unset. Never print or commit the key.

Source: [`main.py`](main.py), [`arena/`](arena/), [`portal/`](portal/), [`tasks/`](tasks/).
