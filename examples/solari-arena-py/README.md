# Solari Arena (Python)

A tiny OSWorld-style eval on Solari's actual products: one cloud browser and one desktop VM. The environment is a synthetic clinic portal hosted *on* the VM (files.write + a stdlib HTTP server + a preview URL). The worklist is a canvas. The oracle is a claim JSON file, not an LLM.

This is a research note, not a leaderboard.

## Hypothesis

CDP locators die on a canvas-painted worklist: there is no named accessibility node, Playwright actionability is visible + stable + elementFromPoint, and `locator('canvas').click()` aims at the centre. The Process CTA is painted in a *corner*, so the centre click misses. An overlay sits on that centre, so the click is often refused before it lands.

In-browser screenshot vision and desktop screenshot + mouse can finish the same goal, because they look at pixels. The interesting result is **disagreement** plus a FILE/HTTP oracle — not failover theatre (we do not silently fall through policies).

A second, API-shaped hypothesis, discarded if the gateway disagrees: on the Free 1-VM cap, **pause then `fromSnapshot`** frees the slot and leaves the original inspectable; if that 429s, **kill then `fromSnapshot`**. If desktop create returns 402, we document it and fall back to sandbox + browsers. We do not fake a GUI.

## Method

1. Boot one VM (desktop if entitled; else sandbox). 1 vCPU / 2 GiB. Write the portal at runtime — Free has no custom templates.
2. Mint a preview URL (same pattern as `sandbox-port-preview-ts`).
3. **CDP locators** (cloud browser, DPR 1, no stealth) against the original: login is real DOM and must pass; the worklist should miss (`FAIL_CANVAS_CLICK_MISS` / `FAIL_SOM_NO_DOM`). Set-of-Mark needs DOM; a canvas CTA has none.
4. Snapshot the original (`POST /sandboxes/:id/snapshots`). `record: true` is legal on this golden boot. It is **not** legal with `fromSnapshot` (400 `RecordingRequiresGoldenBoot`).
5. Pause or kill the original. Free is one concurrent VM — do not keep original + fork live.
6. **In-browser vision** and **desktop mouse** run only on the fork, serial (Free = 3 browsers + 1 VM). Vision is a screenshot + a click in that pixel space. `page.evaluate` / `dispatchEvent` is not vision. `streamUrl` is raw RFB/VNC — never Playwright.
7. Promote the write **iff** the oracle says the right claim JSON changed **and** the other claim is untouched **and** the paused original still matches its baseline. Otherwise `FAIL_WRONG_CLAIM`, `FAIL_NO_MUTATION`, or `FAIL_ORIGINAL_MUTATED`.
8. OOD: the same task with the CTA shifted 80px toward the canvas centre. A cached in-dist coordinate is `FAIL_OOD_SHIFT`. A full-frame pixel scan should still find the blob if the frame is legible. An illegible frame is `HALT_ILLEGIBLE` — no click.

Dual scores, printed per policy, not aggregated into a fake ranking:

- **success** — right claim mutated to `processed`
- **side_effect_clean** — wrong claim untouched

Reason codes: `PASS_ORACLE`, `FAIL_WRONG_CLAIM`, `FAIL_NO_MUTATION`, `FAIL_ORIGINAL_MUTATED`, `HALT_ILLEGIBLE`, `FAIL_CANVAS_CLICK_MISS`, `FAIL_SOM_NO_DOM`, `FAIL_COORD_SPACE`, `FAIL_OOD_SHIFT`, `ABORT_CONCURRENCY`, `ABORT_STREAM_NOT_PLAYWRIGHT`.

The portal is watermarked **SYNTHETIC**. No PHI, no real payers, no Citrix/ICA claims.

## Limitations

- Free serial schedule: one VM, three browser slots, policies in sequence. This is not a parallel agent harvest.
- Browser replay retention is 1 day. Recording is per session; the upload is async after release, so we poll ~30s. `GET /sessions/:id` is not VM health — desktops use `desktop.health()`.
- Desktop entitlement is a paid feature. A 402 here is a documented fallback to sandbox + browsers, not a silent GUI simulation.
- Pixel vision is a colour-blob centroid, not an LLM. That is deliberate. It will fail on a recouloured CTA the same way a locator fails on a renamed button.
- TypeScript's `await solari.close()` hang is N/A; this example is Python.

## Run

```bash
cd examples/solari-arena-py
pip install -r requirements.txt
pytest tests                         # mocked API; spends nothing
# later one-shot after merge — not CI:
# export SOLARI_API_KEY=slr_live_...
# export SOLARI_ARENA_LIVE=1
# python main.py
```

Without a key, `main.py` prints `inconclusive` and does not call the API. A live serial is a **later one-shot after merge** (`SOLARI_ARENA_LIVE=1`); it is not part of CI. The unit tests mock the client and never open `api.getsolari.com`:

```bash
pytest tests
```

The GitHub Action runs those keyless tests with `SOLARI_API_KEY` unset. Never print or commit the key.

Source: [`main.py`](main.py), [`arena/`](arena/), [`portal/`](portal/), [`tasks/`](tasks/).
