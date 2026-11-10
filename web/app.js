// Sieve web page: reads the API, re-checks every review in the browser, submits proposals with a NEAR wallet.
const API = window.SIEVE_API;
const NEAR = 10n ** 24n;
const app = document.getElementById("app");
const enc = new TextEncoder();
let config = null;

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const b64 = (s) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0));
const hex = (bytes) => [...new Uint8Array(bytes)].map((b) => b.toString(16).padStart(2, "0")).join("");
const unhex = (h) => Uint8Array.from(h.match(/../g).map((x) => parseInt(x, 16)));
const near = (yocto) => (Number(BigInt(yocto) * 1000n / NEAR) / 1000).toString();
async function get(path) {
  const r = await fetch(API + path);
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}

// Read the contract directly from a NEAR RPC node, so the browser check does not rely on the API.
async function rpcView(method, args) {
  const r = await fetch(window.SIEVE_RPC, { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "query", params: { request_type: "call_function", finality: "final",
      account_id: config.contract, method_name: method, args_base64: btoa(JSON.stringify(args)) } }) });
  const body = await r.json();
  if (body.error || !body.result) throw new Error("RPC: " + JSON.stringify(body.error || body).slice(0, 120));
  return JSON.parse(new TextDecoder().decode(Uint8Array.from(body.result.result)));
}

function signedReview(responseB64) {
  const content = JSON.parse(new TextDecoder().decode(b64(responseB64))).choices[0].message.content.trim()
    .replace(/^```[a-zA-Z]*\n?/, "").replace(/```$/, "");
  return JSON.parse(content);
}

// The score the contract reads from a signed answer: the count of true checks for a checklist rubric, else "score".
function signedScore(review) {
  if (review.checks && typeof review.checks === "object") return Object.values(review.checks).filter((v) => v === true).length;
  return review.score;
}

// The canonical request, byte for byte as sieve/request.py and the contract build it.
function buildRequest(model, system, roundId, proposalId, title, body, seed, record, stage, evidence) {
  let user = `Round ${roundId}, proposal ${proposalId}, stage ${stage}.\nApplicant record (written by the Sieve contract, not by the applicant): ` +
    `first seen ${record.days} days before this submission; ${record.submitted} proposals submitted before this one; ` +
    `${record.passed} passed review; ${record.delivered} milestones delivered.\n<proposal>\nTITLE: ${title}\n\n${body}\n</proposal>`;
  if (stage > 0) user += `\n<evidence milestone="${stage}">\n${evidence ?? ""}\n</evidence>`;
  return `{"model":${JSON.stringify(model)},"messages":[{"role":"system","content":${JSON.stringify(system)}},` +
    `{"role":"user","content":${JSON.stringify(user)}}],"temperature":0,"seed":${seed},"response_format":{"type":"json_object"}}`;
}

// Re-check one review here without trusting the API: the proposal, round and key registration come from a
// NEAR RPC node; the request is rebuilt from them; the model's ed25519 signature over "model:reqhash:resphash"
// is checked; and the score is read from the signed answer itself. Only the signed answer comes from the API.
async function checkInBrowser(review, proposalId) {
  const [proposal, signer] = await Promise.all([
    rpcView("get_proposal", { proposal_id: proposalId }),
    rpcView("get_signer", { public_key_hex: review.public_key }),
  ]);
  const round = await rpcView("get_round", { round_id: proposal.round_id });
  if (!signer || signer.model !== review.model) return { ok: false, why: "key is not registered on chain for this model" };
  if (round.models[review.slot] !== review.model) return { ok: false, why: "model does not match the round's slot" };
  const stage = review.stage ?? 0;
  const at = stage === proposal.stage ? proposal : proposal.past[stage];
  const system = stage === 0 ? round.system : round.milestone_system;
  const local = buildRequest(review.model, system, proposal.round_id, proposalId, proposal.title, proposal.body,
    at.seed, at.record, stage, at.evidence);
  let signed;
  try { signed = signedScore(signedReview(review.response)); } catch { return { ok: false, why: "signed answer is not a review" }; }
  if (signed !== review.score) return { ok: false, why: "shown score differs from the signed answer" };
  const reqHash = hex(await crypto.subtle.digest("SHA-256", enc.encode(local)));
  const respHash = hex(await crypto.subtle.digest("SHA-256", b64(review.response)));
  const text = `${review.model}:${reqHash}:${respHash}`;
  const ok = window.nacl.sign.detached.verify(enc.encode(text), unhex(review.signature), unhex(review.public_key));
  return { ok, why: ok ? "" : "signature does not match", reqHash, respHash };
}

// 5 by 7 dot-matrix glyphs, the way the hackathon page draws its numbers.
const GLYPHS = {
  "0": "01110100011000110001100011000101110", "1": "00100011000010000100001000010001110",
  "2": "01110100010000100010001000100011111", "3": "11111000100010000010000011000101110",
  "4": "00010001100101010010111110001000010", "5": "11111100001111000001000011000101110",
  "6": "00110010001000011110100011000101110", "7": "11111000010001000100010000100001000",
  "8": "01110100011000101110100011000101110", "9": "01110100011000101111000010001001100",
  "/": "00001000010001000100010001000010000", ".": "00000000000000000000000000110001100",
  "-": "00000000000000011111000000000000000", " ": "00000000000000000000000000000000000",
};
function dots(text, size = "") {
  const digit = (ch) => `<span class="d">${[...(GLYPHS[ch] || GLYPHS[" "])].map((b) => `<i${b === "1" ? ' class="on"' : ""}></i>`).join("")}</span>`;
  return `<span class="dm ${size}" role="img" aria-label="${esc(text)}">${[...String(text)].map(digit).join("")}</span>`;
}

// The pixel score strip: one column per score from 0 to 10, a cell filled per model at its score,
// columns at or above the threshold on a blue ground, and the median column outlined.
function strip(scores, threshold) {
  const sorted = [...scores].sort((a, b) => a - b);
  const median = sorted.length ? sorted[Math.floor((sorted.length - 1) / 2)] : null;
  const cols = Array.from({ length: 11 }, (_, v) => {
    const n = scores.filter((s) => s === v).length;
    const cls = ["col", v >= threshold ? "gate" : "", v === median ? `med ${median >= threshold ? "pass" : "fail"}` : ""].join(" ");
    return `<span class="${cls}" title="${v}">${[2, 1, 0].map((k) => `<i${k < n ? ' class="on"' : ""}></i>`).join("")}</span>`;
  }).join("");
  const label = scores.length ? `model scores ${scores.join(", ")}, median ${median}, passes at ${threshold}` : "not reviewed yet";
  return `<div class="strip${scores.length ? "" : " empty"}" role="img" aria-label="${label}">${cols}
    <span class="axis"><span>0</span><span>passes at ${threshold}</span><span>10</span></span></div>`;
}

function status(p) {
  const tranche = (p.dao_proposal_ids || []).length;
  if (p.completed) return `<span class="status-pass">All milestones delivered</span>`;
  if (p.stage > 0 && !p.finalized) return `Milestone ${p.stage} evidence under review`;
  if (p.finalized && p.outcome && p.outcome.passed && tranche) {
    return `<span class="status-pass">${p.stage === 0 ? "Passed" : `Milestone ${p.stage} accepted`}; tranche ${tranche} (${near(p.outcome.amount)} NEAR) sent to the DAO vote as proposal ${p.dao_proposal_ids[tranche - 1]}</span>`;
  }
  if (p.finalized && p.outcome) {
    if (p.outcome.paid) return `<span class="status-pass">Won the honeypot bounty</span>`;
    if (p.outcome.passed && p.outcome.dao_proposal_id == null) return `<span class="status-pass">Passed, but the bounty was already claimed</span>`;
    if (p.outcome.passed) return `<span class="status-pass">Passed, sent to the DAO vote${p.outcome.dao_proposal_id != null ? ` (DAO proposal ${p.outcome.dao_proposal_id})` : ""}</span>`;
    return `<span class="status-fail">Did not pass (median ${p.outcome.median})</span>`;
  }
  if (p.pending) return "Filing on the DAO";
  const filled = p.slots.filter(Boolean).length;
  return filled ? `${filled} of ${p.slots.length} reviews in` : "Waiting for reviews";
}

async function home() {
  const { rounds, current } = await get("/api/rounds");
  const ids = new Set(Object.values(current || {}));
  const live = ids.size ? rounds.filter((r) => ids.has(r.id)) : rounds;
  const earlier = rounds.filter((r) => !live.includes(r));
  const grant = live.filter((r) => r.kind === "Grant");
  const honey = live.filter((r) => r.kind === "Honeypot");
  const reviewed = rounds.reduce((n, r) => n + (r.proposal_count || 0), 0);
  app.className = "wide";
  app.innerHTML = `
    <section style="max-width:1120px;margin:0 auto;padding:0 20px">
      <div class="hero"><div>
        <h1>Grant reviews you can check</h1>
        <p class="lede">Three AI models review every proposal against a rubric stored on NEAR. Each answer is signed inside a secure enclave, and the contract rebuilds the exact prompt and checks every signature before the median counts. <strong>Passing proposals go to the DAO's vote. The AI never moves money.</strong></p>
        <div class="actions">${grant.map((r) => `<a class="button primary" href="#/round/${r.id}">Submit a proposal</a>`).slice(0, 1).join("")}
          <a class="button" href="#/redteam">See the red-team results</a></div>
      </div><div class="mesh" aria-hidden="true"><canvas id="sieve-canvas" width="84" height="84"></canvas></div></div>
    </section>
    <div class="ticker" aria-hidden="true">${"<span>Signed in the enclave</span><span>Checked on chain</span><span>Voted by the DAO</span>".repeat(4)}</div>
    <section class="band"><div class="band-in">
      <div class="stat"><p class="idx">[ 01 / proposals reviewed ]</p>${dots(reviewed, "big")}<p>Every one reviewed by three models, each signature checked by the contract.</p></div>
      <div class="stat"><p class="idx">[ 02 / templated injections ]</p>${dots("0/10", "big")}<p>Ten kinds of hidden instruction tried on borderline proposals; none got one through under the deployed rule.</p></div>
      <div class="stat"><p class="idx">[ 03 / newcomer first payout ]</p>${dots("0.2", "big")}<p>NEAR. A plausible plan can win only this much before delivery evidence is reviewed.</p></div>
    </div></section>
    <section style="max-width:1120px;margin:0 auto;padding:0 20px">
      <h2>Open rounds</h2>
      <div class="cols">${grant.map((r) => `<div class="cell"><p class="tag">[ round ${r.id} / grant ]</p>${dots(r.threshold, "small")}
        <p class="kind">Passes at a median of ${r.threshold} of 10</p><h3><a href="#/round/${r.id}">Grants on ${esc(r.dao.split(".")[0])}</a></h3>
        <p>First payout ${near(r.newcomer_tranche || r.tranche)} NEAR for newcomers, ${near(r.tranche)} NEAR per milestone after that. Reviewed by ${r.models.length} models.</p>
        <a class="button" href="#/round/${r.id}">See proposals</a></div>`).join("")}
      ${honey.map((r) => `<div class="cell"><p class="tag">[ round ${r.id} / honeypot ]</p>${dots(near(r.bounty), "small")}
        <p class="kind">NEAR bounty, ${r.open ? "unclaimed" : "claimed"}</p><h3><a href="#/round/${r.id}">Fool the reviewer</a></h3>
        <p>Every proposal here is worthless by definition. Get one to a passing median without an injection flag and the contract pays you automatically.</p>
        <a class="button" href="#/round/${r.id}">Try it</a></div>`).join("")}</div>
      ${earlier.length ? `<p class="small muted">Earlier rounds: ${earlier.map((r) => `<a href="#/round/${r.id}">round ${r.id}</a>`).join(", ")}.</p>` : ""}
    </section>`;
  sieveAnimation(document.getElementById("sieve-canvas"));
}

// The one moving thing on the site: pixels fall onto a sieve; most pass through, some are caught.
function sieveAnimation(canvas) {
  if (!canvas || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const ctx = canvas.getContext("2d"), W = 84, H = 84, MESH = 46;
  const css = getComputedStyle(document.documentElement);
  const col = (v) => css.getPropertyValue(v).trim();
  let drops = [], caught = [], t = 0;
  const step = () => {
    if (!document.body.contains(canvas)) return;
    t++;
    if (t % 3 === 0) drops.push({ x: 2 + Math.floor(Math.random() * 40) * 2, y: 0, bad: Math.random() < 0.18 });
    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = col("--ink");
    for (let x = 0; x < W; x += 4) ctx.fillRect(x, MESH, 2, 2);
    for (const d of drops) {
      d.y += 1;
      if (d.bad && d.y === MESH - 2) { caught.push({ x: d.x, y: MESH - 2 - 2 * caught.filter((c) => c.x === d.x).length }); d.done = true; }
      ctx.fillStyle = d.bad ? col("--fail") : (d.y > MESH ? col("--blue") : col("--ink"));
      if (!d.done) ctx.fillRect(d.x, d.y, 2, 2);
    }
    drops = drops.filter((d) => !d.done && d.y < H);
    if (caught.length > 40) caught = caught.slice(-40);
    ctx.fillStyle = col("--fail");
    for (const c of caught) ctx.fillRect(c.x, c.y, 2, 2);
    setTimeout(() => requestAnimationFrame(step), 45);
  };
  step();
}

async function round(id) {
  const d = await get(`/api/rounds/${id}`);
  const r = d.round;
  const props = d.proposals.slice().reverse();
  app.innerHTML = `
    <p class="back"><a href="#/">All rounds</a></p>
    <h1 class="page">${r.kind === "Honeypot" ? "Honeypot round" : "Grant round"} ${id}</h1>
    <p class="lede">${r.kind === "Honeypot" ? `Try to get a worthless proposal approved. Bounty: ${near(r.bounty)} NEAR.` : `Reviewed by ${r.models.map(esc).join(", ")}. A median of ${r.threshold} or more with no injection flag files a ${near(r.tranche)} NEAR payout proposal on <a href="https://testnet.nearblocks.io/address/${esc(r.dao)}">${esc(r.dao)}</a>.`}</p>
    <ul class="list">${props.map((p) => {
      const scores = p.slots.filter(Boolean).map((s) => s.score);
      const s = p.signals || {};
      const dup = (s.duplicates || []).length ? ` Similar to proposal ${s.duplicates.map((x) => x[0]).join(", ")}.` : "";
      const acc = s.account && s.account.age_days != null ? ` Account ${s.account.age_days} days old${(s.account.shares_creator_with || []).length ? `, created by the same account as ${s.account.shares_creator_with.length} other applicant(s)` : ""}.` : "";
      return `<li class="row"><div><h3><a href="#/proposal/${p.id}">${esc(p.title)}</a></h3>
        <div class="meta">by ${esc(p.author)}. ${status(p)}.${dup}${acc}</div></div><div>${strip(scores, r.threshold)}</div></li>`;
    }).join("") || `<li class="row"><div class="muted">No proposals yet. Submit the first one below.</div></li>`}</ul>
    ${r.open ? submitForm(id, r) : ""}`;
  const form = document.getElementById("submit");
  if (form) form.addEventListener("submit", (e) => { e.preventDefault(); submit(id, form); });
}

function submitForm(id, r) {
  return `<h2>${r.kind === "Honeypot" ? "Try to fool the reviewer" : "Submit a proposal"}</h2>
    <form id="submit"><p class="small muted">Your proposal is stored on chain and reviewed within a few minutes. You pay its storage (under 0.1 NEAR, the rest is refunded).</p>
    <label for="t">Title</label><input id="t" name="title" maxlength="200" required>
    <label for="b">Proposal</label><textarea id="b" name="body" maxlength="8000" required placeholder="Problem, deliverables with dates, team, budget, benefit"></textarea>
    <p><button class="primary" type="submit">Submit proposal</button> <span id="submit-status" class="small muted"></span></p></form>`;
}

async function proposal(id) {
  const d = await get(`/api/proposals/${id}`);
  const { proposal: p, round: r } = d;
  // The lowest signed score per slot counts, per stage; show the current stage first, then earlier ones.
  const byStage = {};
  for (const rev of d.reviews) {
    const st = rev.stage ?? 0, slots = (byStage[st] ||= {});
    if (!slots[rev.slot] || rev.score < slots[rev.slot].score) slots[rev.slot] = rev;
  }
  const stages = Object.keys(byStage).map(Number).sort((a, b) => b - a);
  const reviews = stages.flatMap((st) => Object.values(byStage[st]).sort((a, b) => a.slot - b.slot));
  const current = reviews.filter((x) => (x.stage ?? 0) === p.stage);
  const scores = current.map((x) => x.score), sorted = [...scores].sort((a, b) => a - b);
  const median = sorted.length ? sorted[Math.floor((sorted.length - 1) / 2)] : null;
  app.innerHTML = `
    <p class="back"><a href="#/round/${p.round_id}">Round ${p.round_id}</a></p>
    <h1 class="page">${esc(p.title)}</h1>
    <p class="meta muted small">by ${esc(p.author)}. ${status(p)}.</p>
    <div class="verdict ${median === null ? "" : median >= r.threshold ? "pass" : "fail"}">
      <div><p class="label">${p.stage > 0 ? `Milestone ${p.stage} median` : "Median score"}</p><span class="num">${dots(median === null ? "-" : median, "big")}</span></div>
      ${strip(scores, r.threshold)}</div>
    <div class="proposal-body">${esc(p.body)}</div>
    ${p.record ? `<p class="small muted">Applicant record when this stage opened, written by the contract: first seen ${p.record.days} days earlier, ${p.record.submitted} earlier proposals, ${p.record.passed} passed, ${p.record.delivered} milestones delivered.</p>` : ""}
    ${p.evidence ? `<h2>Milestone ${p.stage} evidence</h2><div class="proposal-body">${esc(p.evidence)}</div>` : ""}
    ${milestoneForm(p, r)}
    <h2>Reviews</h2>
    <div id="reviews">${reviews.map((x) => `<div class="review"><div class="head">
      <h3>${esc(x.model)}${(x.stage ?? 0) > 0 ? `, milestone ${x.stage}` : (p.stage > 0 ? ", proposal review" : "")}</h3>${dots(x.score)}</div>
      <p>${esc(reviewReason(x))}</p>${(x.flags || []).map((f) => `<span class="flag">${esc(f)}</span>`).join("")}
      <p class="proof" data-key="${x.stage ?? 0}-${x.slot}">Checking the signature in your browser…</p>
      <details><summary>What was checked</summary><p>Your browser read this proposal, the round's rubric and the key registration directly from a NEAR RPC node, rebuilt the exact request, hashed it with SHA-256, and checked the model's ed25519 signature over <code>model:request-hash:response-hash</code> with key <code>${esc(x.public_key)}</code>, which the contract has registered for ${esc(x.model)}. The score shown is read from the signed answer.</p>
      <p>Transaction <a href="https://testnet.nearblocks.io/txns/${esc(x.tx)}">${esc(x.tx)}</a></p><p class="hash" data-hashes="${x.stage ?? 0}-${x.slot}"></p></details></div>`).join("") || `<p class="muted">No reviews yet. The relayer picks new proposals up within a minute.</p>`}</div>`;
  const mf = document.getElementById("milestone");
  if (mf) mf.addEventListener("submit", (e) => { e.preventDefault(); submitMilestone(id, mf); });
  for (const x of reviews) {
    let res;
    try { res = await checkInBrowser(x, id); } catch (e) { res = { ok: false, why: e.message }; }
    const key = `${x.stage ?? 0}-${x.slot}`;
    const el = document.querySelector(`.proof[data-key="${key}"]`);
    el.textContent = res.ok ? "Checked in your browser: signature, on-chain key and score" : `Check failed: ${res.why}`;
    el.classList.toggle("bad", !res.ok);
    if (res.reqHash) document.querySelector(`[data-hashes="${key}"]`).textContent = `request ${res.reqHash}, response ${res.respHash}`;
  }
}

function milestoneForm(p, r) {
  const canSubmit = p.finalized && p.outcome && p.outcome.passed && !p.completed && r.milestone_system &&
    (p.dao_proposal_ids || []).length === p.stage + 1;
  if (!canSubmit) return "";
  return `<h2>Deliver milestone ${p.stage + 1}</h2>
    <form id="milestone"><p class="small muted">Once DAO members approve the payout for this stage, the author can submit evidence of delivery: release links, commit hashes, deployed contract addresses, transaction ids. Three models review it against the original plan; if it passes, the next tranche goes to the DAO vote.</p>
    <label for="ev">Evidence</label><textarea id="ev" name="evidence" maxlength="4000" required></textarea>
    <p><button class="primary" type="submit">Submit milestone evidence</button> <span id="milestone-status" class="small muted"></span></p></form>`;
}

async function submitMilestone(proposalId, form) {
  const out = document.getElementById("milestone-status");
  try {
    const c = await wallet();
    if (!account) { out.textContent = "Connect the author's wallet first."; await c.connect(); return; }
    out.textContent = "Confirm the transaction in your wallet.";
    const w = await c.wallet();
    await w.signAndSendTransaction({ receiverId: config.contract, actions: [{ type: "FunctionCall", params: {
      methodName: "submit_milestone", args: { proposal_id: proposalId, evidence: form.evidence.value },
      gas: "100000000000000", deposit: (NEAR / 10n).toString() } }] });
    out.textContent = "Submitted. If the DAO approved the last payout, review starts within minutes; otherwise your deposit is refunded.";
    setTimeout(() => route(), 4000);
  } catch (e) { out.textContent = `Not submitted: ${e.message || e}`; }
}

function reviewReason(x) {
  try { return signedReview(x.response).reason || ""; } catch { return ""; }
}

async function redteam() {
  const { markdown } = await get("/api/redteam");
  app.innerHTML = `<h1 class="page">How often can the reviewer be fooled?</h1>
    <p class="lede">We attacked the reviewer with injected proposals on real models, kept every signed answer, and counted how often a proposal that fails on its own was pushed to a pass. Run <code>sieve redteam report</code> to re-check every signature yourself.</p>
    ${markdown ? mdTables(markdown) : `<p class="muted">Results are being collected.</p>`}`;
}

function mdTables(md) {
  const out = [];
  let table = null;
  for (const line of md.split("\n")) {
    if (line.startsWith("|")) {
      const cells = line.slice(1, -1).split("|").map((c) => c.trim());
      if (cells.every((c) => /^-+$/.test(c))) continue;
      if (!table) { table = []; out.push(table); }
      table.push(cells);
    } else {
      table = null;
      if (line.startsWith("## ")) out.push(`<h2 class="sub">${esc(line.slice(3)).replace(/`([^`]+)`/g, "<code>$1</code>")}</h2>`);
      else if (line.startsWith("# ")) continue;
      else if (line.trim()) out.push(`<p>${esc(line).replace(/`([^`]+)`/g, "<code>$1</code>")}</p>`);
    }
  }
  return out.map((t) => typeof t === "string" ? t :
    `<table><thead><tr>${t[0].map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead><tbody>${t.slice(1).map((r) =>
      `<tr>${r.map((c) => `<td>${esc(c)}</td>`).join("")}</tr>`).join("")}</tbody></table>`).join("");
}

function about() {
  app.innerHTML = `<h1 class="page">How Sieve works</h1>
    <ol class="steps">
      <li>A community opens a round on its Sputnik DAO. The rubric and the exact prompt template are stored in the Sieve contract.</li>
      <li>Applicants submit proposals on chain with their NEAR wallet.</li>
      <li>A relayer, which anyone can run, sends each proposal to three models in NEAR AI Cloud's secure enclaves and posts their signed answers.</li>
      <li>The contract rebuilds the exact prompt, checks each model's signature with a key registered after checking the enclave's attestation, and reads the score from the signed answer. During the review window (an hour in the current rounds) anyone can post a lower signed score for the same prompt, so cherry-picking a lucky answer does not help.</li>
      <li>Each request includes the applicant's record, written by the contract: how long it has known them, their earlier proposals, and milestones delivered. Claims in the proposal about the past cannot replace it.</li>
      <li>The median of the three scores decides. If it passes and no model flagged an injection attempt, the contract files a payout proposal on the DAO for members to vote on. Applicants who have never delivered a milestone get a smaller first tranche.</li>
      <li>After members approve a tranche, the author submits delivery evidence. The contract checks with the DAO that the payout was approved, then the evidence gets its own three-model review against the original plan. Passing counts a delivered milestone and files the next tranche.</li>
    </ol>
    <p>Code and the threat model: <a href="https://github.com/dhairya-pandya/sieve">github.com/dhairya-pandya/sieve</a>.</p>`;
}

let connector = null, account = null;
async function wallet() {
  if (!connector) {
    const { NearConnector } = await import("https://esm.sh/@hot-labs/near-connect@0.12.0");
    connector = new NearConnector({ network: window.SIEVE_NETWORK });
    connector.on("wallet:signIn", (t) => { account = t.accounts[0].accountId; showAccount(); });
    connector.on("wallet:signOut", () => { account = null; showAccount(); });
  }
  return connector;
}
function showAccount() {
  const b = document.getElementById("wallet");
  b.textContent = account ? account : "Connect wallet";
  b.toggleAttribute("data-on", !!account);
}
document.getElementById("wallet").addEventListener("click", async () => {
  const c = await wallet();
  if (account) await (await c.wallet()).signOut(); else await c.connect();
});

async function submit(roundId, form) {
  const out = document.getElementById("submit-status");
  const button = form.querySelector("button");
  try {
    const c = await wallet();
    if (!account) { out.textContent = "Connect a wallet first."; await c.connect(); return; }
    button.disabled = true;
    out.textContent = "Confirm the transaction in your wallet.";
    const w = await c.wallet();
    await w.signAndSendTransaction({ receiverId: config.contract, actions: [{ type: "FunctionCall", params: {
      methodName: "submit", args: { round_id: roundId, title: form.title.value, body: form.body.value },
      gas: "30000000000000", deposit: (NEAR / 10n).toString() } }] });
    out.textContent = "Submitted. Reviews arrive in a few minutes.";
    setTimeout(() => route(), 3000);
  } catch (e) {
    out.textContent = `Not submitted: ${e.message || e}`;
  } finally { button.disabled = false; }
}

async function route() {
  const [, page, id] = (location.hash || "#/").slice(1).split("/");
  app.className = "";
  document.querySelectorAll(".top nav a").forEach((a) => a.toggleAttribute("aria-current",
    a.getAttribute("href") === `#/${page === "round" || page === "proposal" ? "" : page || ""}`));
  try {
    if (!config) { config = await get("/api/rounds"); document.getElementById("contract").innerHTML = `Contract <a href="https://testnet.nearblocks.io/address/${esc(config.contract)}">${esc(config.contract)}</a> on NEAR testnet`; }
    if (page === "round") await round(Number(id));
    else if (page === "proposal") await proposal(Number(id));
    else if (page === "redteam") await redteam();
    else if (page === "about") about();
    else await home();
  } catch (e) {
    app.innerHTML = `<h1 class="page">Could not load this page</h1><p class="lede">${esc(e.message)}. The API may be waking up; reload in a few seconds.</p>`;
  }
  window.scrollTo(0, 0);
}
window.addEventListener("hashchange", route);
document.getElementById("theme").addEventListener("click", () => {
  const dark = document.documentElement.dataset.theme ? document.documentElement.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
  document.documentElement.dataset.theme = dark ? "light" : "dark";
  try { localStorage.setItem("theme", document.documentElement.dataset.theme); } catch {}
});
try { const t = localStorage.getItem("theme"); if (t) document.documentElement.dataset.theme = t; } catch {}
route();
