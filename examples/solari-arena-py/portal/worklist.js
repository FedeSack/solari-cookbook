/* Keep these numbers in sync with arena/geometry.py. */
const HEADER_H = 64;
const CTA_W = 168;
const CTA_H = 44;
const PAD = 18;
const CTA = "#e85d04";
const DECOY = "#1d4e89";

const params = new URLSearchParams(location.search);
const corner = params.get("ctaCorner") || "bottom-right";
const oodShiftPx = Number(params.get("oodShiftPx") || 0);
const targetId = params.get("claimId") || "CLM-1001";
const sideId = "CLM-1002";

const canvas = document.getElementById("worklist");
const ctx = canvas.getContext("2d");
const statusEl = document.getElementById("status");

function cornerOrigin(c, w, h) {
  if (c === "top-left") return [PAD, PAD];
  if (c === "top-right") return [w - PAD - CTA_W, PAD];
  if (c === "bottom-left") return [PAD, h - PAD - CTA_H];
  return [w - PAD - CTA_W, h - PAD - CTA_H];
}

function shiftTowardCenter(x, y, c, shift) {
  if (!shift) return [x, y];
  if (c.indexOf("right") !== -1) x -= shift; else x += shift;
  if (c.indexOf("bottom") !== -1) y -= shift; else y += shift;
  return [x, y];
}

function opposite(c) {
  return {
    "top-left": "bottom-right",
    "top-right": "bottom-left",
    "bottom-left": "top-right",
    "bottom-right": "top-left",
  }[c];
}

const W = canvas.width;
const H = canvas.height;
let [tx, ty] = cornerOrigin(corner, W, H);
[tx, ty] = shiftTowardCenter(tx, ty, corner, oodShiftPx);
const [dx, dy] = cornerOrigin(opposite(corner), W, H);

const targetRect = { x: tx, y: ty, w: CTA_W, h: CTA_H, claimId: targetId };
const decoyRect = { x: dx, y: dy, w: CTA_W, h: CTA_H, claimId: sideId };

function hit(r, x, y) {
  return x >= r.x && x < r.x + r.w && y >= r.y && y < r.y + r.h;
}

function paint() {
  ctx.fillStyle = "#e8e2d6";
  ctx.fillRect(0, 0, W, H);
  ctx.fillStyle = "#1b1f24";
  ctx.font = "16px sans-serif";
  ctx.fillText("Pending claims (painted, not DOM)", 24, 40);
  ctx.font = "14px sans-serif";
  ctx.fillText(targetId + "   SYNTHETIC-A   $120.00   pending", 24, 88);
  ctx.fillText(sideId + "   SYNTHETIC-B   $88.50   pending", 24, 120);

  ctx.fillStyle = CTA;
  ctx.fillRect(targetRect.x, targetRect.y, targetRect.w, targetRect.h);
  ctx.fillStyle = "#fff";
  ctx.font = "14px sans-serif";
  ctx.fillText("Process " + targetId, targetRect.x + 16, targetRect.y + 28);

  ctx.fillStyle = DECOY;
  ctx.fillRect(decoyRect.x, decoyRect.y, decoyRect.w, decoyRect.h);
  ctx.fillStyle = "#fff";
  ctx.fillText("Process " + sideId, decoyRect.x + 16, decoyRect.y + 28);
}

async function processClaim(claimId) {
  const res = await fetch("/api/claims/" + encodeURIComponent(claimId), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status: "processed" }),
  });
  const body = await res.json();
  statusEl.textContent = "oracle " + claimId + " → " + body.status;
}

canvas.addEventListener("click", (ev) => {
  const r = canvas.getBoundingClientRect();
  const x = ev.clientX - r.left;
  const y = ev.clientY - r.top;
  if (hit(targetRect, x, y)) {
    processClaim(targetRect.claimId);
    return;
  }
  if (hit(decoyRect, x, y)) {
    processClaim(decoyRect.claimId);
    return;
  }
  statusEl.textContent = "canvas click miss (" + Math.round(x) + "," + Math.round(y) + ")";
});

paint();
statusEl.textContent = "cta=" + corner + " shift=" + oodShiftPx + " target=" + targetId;
