import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { CSS2DRenderer, CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';

/* ───────────────────────── helpers & state ───────────────────────── */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const REPO_COL = { click: 0x4cc9f0, jsoncpp: 0xffb703, zod: 0xb388ff };
const RULE_PAL = [0xffd166, 0x06d6a0, 0x4cc9f0, 0xef476f, 0xb388ff, 0xff9f1c, 0x80ed99, 0xf72585, 0x4895ef, 0xc77dff];
const STAGE_NAMES = ['S1 tests fail on base', 'S2 reference passes', 'S3 existing suite intact', 'S4 every rule detected',
  'S5 mutation kill', 'S6 neighbour guard', 'S7 deterministic'];
const STAGE_KEYS = ['S1_base_fails', 'S2_reference_passes', 'S3_regression_intact', 'S4_rule_ablations',
  'S5_mutation_kill', 'S6_regression_guard', 'S7_determinism'];
const esc = (s) => String(s).replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));

const S = { live: false, tasks: [], families: [], sel: null, station: 'atlas', ablated: new Set(), running: false, liveIds: new Set() };

/* ───────────────────────── renderer / scene ───────────────────────── */
const canvas = $('#gl');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: 'high-performance' });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setSize(innerWidth, innerHeight);
renderer.toneMapping = THREE.ACESFilmicToneMapping;
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x05060d);
scene.fog = new THREE.FogExp2(0x05060d, 0.0042);
const camera = new THREE.PerspectiveCamera(55, innerWidth / innerHeight, 0.1, 900);
camera.position.set(0, 90, 150);
const controls = new OrbitControls(camera, canvas);
controls.enableDamping = true; controls.dampingFactor = 0.06; controls.minDistance = 5; controls.maxDistance = 90;
controls.maxPolarAngle = Math.PI * 0.62;

const labelRenderer = new CSS2DRenderer();
labelRenderer.setSize(innerWidth, innerHeight);
Object.assign(labelRenderer.domElement.style, { position: 'fixed', inset: '0', pointerEvents: 'none', zIndex: 2 });
document.body.appendChild(labelRenderer.domElement);

const composer = new EffectComposer(renderer);
composer.addPass(new RenderPass(scene, camera));
const bloom = new UnrealBloomPass(new THREE.Vector2(innerWidth, innerHeight), 0.95, 0.65, 0.08);
composer.addPass(bloom);
composer.addPass(new OutputPass());

addEventListener('resize', () => {
  camera.aspect = innerWidth / innerHeight; camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight); composer.setSize(innerWidth, innerHeight); labelRenderer.setSize(innerWidth, innerHeight);
});

function glowTexture() {
  const c = document.createElement('canvas'); c.width = c.height = 128; const g = c.getContext('2d');
  const gr = g.createRadialGradient(64, 64, 0, 64, 64, 64);
  gr.addColorStop(0, 'rgba(255,255,255,1)'); gr.addColorStop(0.22, 'rgba(255,255,255,.35)'); gr.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = gr; g.fillRect(0, 0, 128, 128); return new THREE.CanvasTexture(c);
}
const GLOW = glowTexture();
function glow(color, size, opacity = 1) {
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: GLOW, color, blending: THREE.AdditiveBlending, depthWrite: false, transparent: true, opacity }));
  s.scale.setScalar(size); return s;
}
function label(text, cls = '', parent, pos = [0, 0, 0]) {
  const d = document.createElement('div'); d.className = 'lbl ' + cls; d.textContent = text;
  const o = new CSS2DObject(d); o.position.set(...pos); parent.add(o); return o;
}

// starfield + nebula dust
{
  const n = 2600, pos = new Float32Array(n * 3), col = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) {
    const r = 120 + Math.random() * 380, a = Math.random() * 6.283, b = Math.acos(2 * Math.random() - 1);
    pos.set([r * Math.sin(b) * Math.cos(a), r * Math.cos(b) * 0.6, r * Math.sin(b) * Math.sin(a)], i * 3);
    const c = new THREE.Color().setHSL(0.55 + Math.random() * 0.25, 0.6, 0.65); col.set([c.r, c.g, c.b], i * 3);
  }
  const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(pos, 3)); g.setAttribute('color', new THREE.BufferAttribute(col, 3));
  var stars = new THREE.Points(g, new THREE.PointsMaterial({ size: 1.4, vertexColors: true, transparent: true, opacity: 0.85, depthWrite: false, blending: THREE.AdditiveBlending }));
  scene.add(stars);
}

/* ───────────────────────── stations ───────────────────────── */
const atlasG = new THREE.Group(); const pipeG = new THREE.Group(); const varG = new THREE.Group();
pipeG.position.set(0, 0, -90); varG.position.set(100, 0, -30);
scene.add(atlasG, pipeG, varG);
const STATIONS = {
  atlas: { cam: [0, 24, 50], look: [0, 0, 0] },
  pipeline: { cam: [14, 6, -58], look: [14, -1, -90] },
  variation: { cam: [100, 20, 0], look: [100, 2, -30] },
};
function flyTo(st, dur = 2.1) {
  const p = STATIONS[st]; S.station = st; stationLabels(st); setTimeout(() => stationLabels(st), 50); gsap.to(bloom, { strength: st === 'variation' ? 0.25 : 0.95, threshold: st === 'variation' ? 0.6 : 0.08, duration: 1.2 });
  gsap.to(camera.position, { x: p.cam[0], y: p.cam[1], z: p.cam[2], duration: dur, ease: 'power3.inOut' });
  gsap.to(controls.target, { x: p.look[0], y: p.look[1], z: p.look[2], duration: dur, ease: 'power3.inOut' });
  $$('#nav button').forEach((b) => b.classList.toggle('on', b.dataset.st === st));
}

/* ───────────────────────── Atlas (all tasks as a galaxy) ───────────────────────── */
const pickables = []; // meshes that react to the pointer
let atlasNodes = [];
function buildAtlas() {
  clearGroup(atlasG);
  pickables.length = 0; atlasNodes = [];
  const repos = [...new Set(S.tasks.map((t) => t.repo))];
  repos.forEach((repo, ri) => {
    const ang = (ri / repos.length) * Math.PI * 2 + 0.4, cx = Math.cos(ang) * 17, cz = Math.sin(ang) * 11;
    const hub = glow(REPO_COL[repo] || 0xffffff, 9, 0.55); hub.position.set(cx, 0, cz); atlasG.add(hub);
    label(repo, 'fam', atlasG, [cx, 5.5, cz]);
    const fams = [...new Set(S.tasks.filter((t) => t.repo === repo).map((t) => t.family))];
    fams.forEach((fam, fi) => {
      const fa = (fi / fams.length) * Math.PI * 2 + ri, fx = cx + Math.cos(fa) * 6.2, fz = cz + Math.sin(fa) * 4.6;
      const ts = S.tasks.filter((t) => t.repo === repo && t.family === fam);
      const pts = [];
      ts.forEach((t, k) => {
        const a = (k / ts.length) * 6.283 + fi, r = 2.1;
        const m = new THREE.Mesh(new THREE.SphereGeometry(0.34 + Math.min(t.f2p, 70) / 160, 24, 18),
          new THREE.MeshBasicMaterial({ color: REPO_COL[repo] || 0xffffff }));
        m.position.set(fx + Math.cos(a) * r, Math.sin(k * 1.7) * 0.9, fz + Math.sin(a) * r);
        m.userData = { type: 'task', id: t.id, base: m.position.clone(), ph: Math.random() * 6 };
        const g = glow(REPO_COL[repo] || 0xffffff, 2.6, 0.8); m.add(g);
        if (!t.valid) m.material.color.set(0xef476f);
        if (S.liveIds.has(t.id)) { const ring = new THREE.Mesh(new THREE.TorusGeometry(0.9, 0.04, 8, 40), new THREE.MeshBasicMaterial({ color: 0x06d6a0 })); ring.rotation.x = Math.PI / 2; m.add(ring); }
        atlasG.add(m); pickables.push(m); atlasNodes.push(m); pts.push(m.position);
      });
      if (pts.length > 1) {
        const lg = new THREE.BufferGeometry().setFromPoints([...pts, pts[0]]);
        atlasG.add(new THREE.Line(lg, new THREE.LineBasicMaterial({ color: REPO_COL[repo], transparent: true, opacity: 0.22 })));
      }
      label(fam, 'fam', atlasG, [fx, 3.4, fz]);
    });
  });
  refreshSelectionHalo(); stationLabels(S.station);
}
const halo = new THREE.Mesh(new THREE.TorusGeometry(1.15, 0.05, 10, 60), new THREE.MeshBasicMaterial({ color: 0xffffff }));
halo.visible = false; atlasG.add(halo);
function refreshSelectionHalo() {
  if (!atlasG.children.includes(halo)) atlasG.add(halo);
  const n = atlasNodes.find((m) => m.userData.id === S.sel?.id);
  halo.visible = !!n; if (n) { halo.position.copy(n.position); }
}

/* ───────────────────────── Pipeline station ───────────────────────── */
const P = { core: null, rules: [], gates: [], cubes: null, tstate: [], trule: [], mut: null, packet: null, mstate: [], coreGlow: null };
function clearGroup(g) {
  [...g.children].forEach((c) => { c.traverse((o) => { o.geometry?.dispose?.(); if (o.isCSS2DObject) o.element.remove(); }); g.remove(c); });
}
function stationLabels(st) {
  const map = { atlas: atlasG, pipeline: pipeG, variation: varG };
  Object.entries(map).forEach(([k, g]) => g.traverse((o) => { if (o.isCSS2DObject) o.visible = k === st; }));
}
const tmpM = new THREE.Matrix4(), tmpP = new THREE.Vector3(), tmpS = new THREE.Vector3(), tmpQ = new THREE.Quaternion(), tmpC = new THREE.Color();

function buildPipeline(t) {
  clearGroup(pipeG);
  const rc = REPO_COL[t.repo] || 0x4cc9f0;
  // core
  const core = new THREE.Group();
  core.add(new THREE.LineSegments(new THREE.WireframeGeometry(new THREE.IcosahedronGeometry(1.7, 1)), new THREE.LineBasicMaterial({ color: rc, transparent: true, opacity: 0.9 })));
  const inner = new THREE.Mesh(new THREE.SphereGeometry(0.95, 32, 24), new THREE.MeshBasicMaterial({ color: 0xffffff }));
  core.add(inner); const cg = glow(rc, 9, 0.9); core.add(cg); P.coreGlow = cg; P.core = core;
  label(`variant ${t.id.split('/')[1]}`, 'core', core, [0, 2.9, 0]);
  pipeG.add(core);
  // rules orbit
  P.rules = [];
  t.rules.forEach((r, i) => {
    const grp = new THREE.Group(); grp.rotation.set(0.35 * Math.sin(i * 2.1), i * 0.9, 0.5 * Math.cos(i * 1.7));
    const rad = 3.8 + (i % 3) * 0.95, color = RULE_PAL[i % RULE_PAL.length];
    const ringG = new THREE.BufferGeometry().setFromPoints(Array.from({ length: 65 }, (_, k) => new THREE.Vector3(Math.cos(k / 64 * 6.283) * rad, 0, Math.sin(k / 64 * 6.283) * rad)));
    grp.add(new THREE.Line(ringG, new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.18 })));
    const orb = new THREE.Mesh(new THREE.SphereGeometry(r.id === 'core' ? 0.42 : 0.3, 20, 16), new THREE.MeshBasicMaterial({ color }));
    orb.add(glow(color, 2.4, 0.9)); orb.userData = { type: 'rule', id: r.id, idx: i, color, rad, spd: 0.25 + (i % 4) * 0.07, a: i * 1.3 };
    label(r.id, '', orb, [0, 0.4, 0]);
    grp.add(orb); pipeG.add(grp); P.rules.push({ grp, orb, color });
  });
  // tests platform (one cube per fail-to-pass test, coloured by rule)
  const total = t.rules.reduce((a, r) => a + (t.tests_by_rule[r.id] || 0), 0);
  P.trule = []; t.rules.forEach((r, i) => { for (let k = 0; k < (t.tests_by_rule[r.id] || 0); k++) P.trule.push(i); });
  P.cubes = new THREE.InstancedMesh(new THREE.BoxGeometry(0.3, 0.3, 0.3), new THREE.MeshBasicMaterial({ toneMapped: false }), Math.max(1, total));
  P.tstate = P.trule.map(() => ({ v: 0 }));
  P.trule.forEach((ri, i) => P.cubes.setColorAt(i, tmpC.set(RULE_PAL[ri % RULE_PAL.length])));
  pipeG.add(P.cubes);
  const grid = new THREE.GridHelper(14, 28, 0x2a3566, 0x1a2144); grid.position.set(0, -7.4, 0); grid.material.transparent = true; grid.material.opacity = 0.55; pipeG.add(grid);
  label(`${t.f2p} feature tests · one cube each`, '', pipeG, [0, -5.2, 0]);
  // gates
  P.gates.forEach((g) => g.dispose?.()); P.gates = [];
  const rail = new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(2.5, 0, 0), new THREE.Vector3(36, 0, 0)]), new THREE.LineBasicMaterial({ color: 0x2c3a78, transparent: true, opacity: 0.7 }));
  pipeG.add(rail);
  for (let i = 0; i < 7; i++) {
    const g = new THREE.Group(); g.position.set(8 + i * 4.3, 0, 0);
    const ring = new THREE.Mesh(new THREE.TorusGeometry(1.5, 0.09, 14, 56), new THREE.MeshBasicMaterial({ color: 0x3a4a9a, toneMapped: false }));
    ring.rotation.y = Math.PI / 2; g.add(ring);
    const disc = new THREE.Mesh(new THREE.CircleGeometry(1.45, 40), new THREE.MeshBasicMaterial({ color: 0x4cc9f0, transparent: true, opacity: 0.05, side: THREE.DoubleSide, depthWrite: false }));
    disc.rotation.y = Math.PI / 2; g.add(disc);
    label(STAGE_NAMES[i].split(' ')[0], 'gate', g, [0, 2.4, 0]);
    g.userData = { ring, disc, status: 'idle', pulse: 0 }; pipeG.add(g); P.gates.push(g);
  }
  // packet
  const pk = new THREE.Mesh(new THREE.OctahedronGeometry(0.32), new THREE.MeshBasicMaterial({ color: 0xffffff }));
  pk.add(glow(0xffffff, 3.4)); pk.position.set(2.5, 0, 0); pk.visible = false; pipeG.add(pk); P.packet = pk;
  // mutants swarm (around gate S5)
  const st5 = t.stages.S5_mutation_kill; const nm = Math.min(48, (st5.killed || 0) + (st5.survived || 0));
  P.mut = new THREE.InstancedMesh(new THREE.TetrahedronGeometry(0.17), new THREE.MeshBasicMaterial({ toneMapped: false }), Math.max(1, nm));
  P.mstate = Array.from({ length: nm }, (_, i) => ({ survived: i >= (st5.killed || 0) * nm / Math.max(1, (st5.killed || 0) + (st5.survived || 0)), a: Math.random() * 6.28, r: 2 + Math.random() * 1.2, y: (Math.random() - 0.5) * 2, k: 0 }));
  P.mstate.forEach((m, i) => P.mut.setColorAt(i, tmpC.set(0x7a86b8)));
  P.mut.visible = true; pipeG.add(P.mut);
  S.ablated.clear(); renderStageList(t); renderRules(t); stationLabels(S.station);
}

/* per-frame animation of the pipeline station */
function animatePipeline(dt, time) {
  if (!P.core) return;
  P.core.rotation.y += dt * 0.5; P.core.rotation.x += dt * 0.2;
  P.core.scale.setScalar(1 + Math.sin(time * 2) * 0.03);
  P.rules.forEach(({ grp, orb }) => { orb.userData.a += dt * orb.userData.spd; const u = orb.userData; orb.position.set(Math.cos(u.a) * u.rad, 0, Math.sin(u.a) * u.rad); });
  // cubes
  const cols = 14;
  P.trule.forEach((ri, i) => {
    const c = i % cols, r = Math.floor(i / cols), f = P.tstate[i].v;
    const shake = f > 0.01 && f < 0.99 ? Math.sin(time * 60 + i) * 0.05 : 0;
    tmpP.set((c - (cols - 1) / 2) * 0.46 + shake, -6.9 + Math.sin(time * 1.4 + i * 0.5) * 0.06 - f * 0.45, (r - 2) * 0.46);
    tmpS.setScalar(1 - f * 0.35); tmpM.compose(tmpP, tmpQ.identity(), tmpS); P.cubes.setMatrixAt(i, tmpM);
    tmpC.set(RULE_PAL[ri % RULE_PAL.length]).lerp(new THREE.Color(0xef476f), f); P.cubes.setColorAt(i, tmpC);
  });
  P.cubes.instanceMatrix.needsUpdate = true; if (P.cubes.instanceColor) P.cubes.instanceColor.needsUpdate = true;
  // gates idle pulse
  P.gates.forEach((g, i) => { const u = g.userData; g.rotation.x += dt * (u.status === 'idle' ? 0.4 : 0.9); u.disc.material.opacity = 0.05 + (u.status !== 'idle' ? 0.12 : 0) + u.pulse * 0.5; u.pulse *= 0.93; });
  // mutants
  const g5 = P.gates[4]; if (g5) P.mstate.forEach((m, i) => {
    m.a += dt * (m.survived ? 1.4 : 0.9); const k = m.k;
    const rad = m.r + k * 6, y = m.y + (m.survived ? Math.sin(time * 3 + i) * 0.2 : k * (i % 2 ? 2 : -2));
    tmpP.set(g5.position.x + Math.sin(m.a) * 0.6, y + Math.sin(m.a * 1) * 0.0, Math.cos(m.a) * rad * 0.7);
    tmpS.setScalar(m.survived ? 1.15 : Math.max(0.001, 1 - k)); tmpM.compose(tmpP, tmpQ.setFromEuler(new THREE.Euler(time + i, time, 0)), tmpS); P.mut.setMatrixAt(i, tmpM);
  });
  if (P.mut) P.mut.instanceMatrix.needsUpdate = true;
}

/* gate activation + stage list */
const STAT_COL = { ok: 0x06d6a0, warn: 0xffd166, bad: 0xef476f, na: 0x8a93b2, idle: 0x3a4a9a };
function resetGates() {
  P.gates.forEach((g) => { g.userData.status = 'idle'; g.userData.ring.material.color.set(STAT_COL.idle); });
  P.mstate.forEach((m) => { m.k = 0; }); P.cubes && P.tstate.forEach((s) => { s.v = 0; });
  $$('#stagelist li').forEach((li) => { li.className = ''; $('i', li).textContent = '—'; });
}
function activateGate(i, status, text) {
  const g = P.gates[i]; if (!g) return; const u = g.userData; u.status = status; u.pulse = 1;
  gsap.to(u.ring.material.color, { ...new THREE.Color(STAT_COL[status]), duration: 0.35 });
  gsap.fromTo(g.scale, { x: 1.5, y: 1.5, z: 1.5 }, { x: 1, y: 1, z: 1, duration: 0.8, ease: 'elastic.out(1,0.4)' });
  shockwave(g.getWorldPosition(new THREE.Vector3()), STAT_COL[status], 4);
  const li = $(`#stagelist li[data-i="${i}"]`); if (li) { li.className = status; $('i', li).textContent = text; }
}
function stageInfo(t) {
  const s = t.stages, n = (x) => x ?? 0;
  const s1 = s.S1_base_fails, s4 = Object.values(s.S4_rule_ablations.per_rule), s5 = s.S5_mutation_kill, s6 = s.S6_regression_guard;
  const guards = s1.guard_tests_passing_on_base ?? (s1.passing_on_base?.length || 0);
  return [
    { status: s1.ok ? 'ok' : 'bad', text: `${n(s1.failing) || t.f2p} fail on base${guards ? ` · ${guards} guards` : ''}` },
    { status: s.S2_reference_passes.ok ? 'ok' : 'bad', text: `${s.S2_reference_passes.passed} feature tests pass` },
    { status: s.S3_regression_intact.ok ? 'ok' : 'bad', text: `${s.S3_regression_intact.passed} existing intact` },
    { status: s.S4_rule_ablations.ok ? 'ok' : 'bad', text: `${s4.filter((a) => a.caught).length}/${s4.length} rules caught` },
    { status: s5.ok ? 'ok' : 'warn', text: `${s5.killed}/${s5.killed + s5.survived} mutants killed (${Math.round(s5.score * 100)}%)` },
    s6.applicable === false ? { status: 'na', text: 'n/a (additive patch)' }
      : { status: s6.ok ? 'ok' : 'warn', text: `${s6.killed_by_existing_suite + s6.killed_by_feature_tests}/${s6.killed_by_existing_suite + s6.killed_by_feature_tests + s6.survived} caught` },
    { status: s.S7_determinism.ok ? 'ok' : 'bad', text: 'deterministic' },
  ];
}
function movePacket(i) {
  P.packet.visible = true; return gsap.to(P.packet.position, { x: P.gates[i].position.x, duration: i === 0 ? 1.1 : 0.7, ease: 'power2.inOut' });
}
async function replay(t = S.sel) {
  if (S.running || !t) return; S.running = true; flyTo('pipeline'); setTab('task'); resetGates();
  P.packet.position.x = 2.5; await sleep(500);
  const info = stageInfo(t);
  for (let i = 0; i < 7; i++) {
    gsap.to(controls.target, { x: 8 + i * 4.3 - 3, duration: 0.9, ease: 'power2.out' });
    await movePacket(i); activateGate(i, info[i].status, info[i].text);
    if (i === 4) mutantBurst();
    if (i === 3) tourAblations(t, true);
    log(`${STAGE_NAMES[i]}  ${info[i].status.toUpperCase()}  ${info[i].text}`, info[i].status);
    await sleep(380);
  }
  P.packet.visible = false; gsap.to(controls.target, { x: 14, duration: 1.2 });
  banner(t.valid ? `✓ ${t.id} passes every gate` : `✗ ${t.id} failed a gate`); S.running = false;
}
function mutantBurst() { P.mstate.forEach((m, i) => { if (!m.survived) gsap.to(m, { k: 1, duration: 1.2 + Math.random() * 0.6, delay: i * 0.015, ease: 'power2.out' }); }); }

/* effects */
const waves = [];
function shockwave(pos, color = 0xffffff, size = 5) {
  const m = new THREE.Mesh(new THREE.RingGeometry(0.2, 0.28, 48), new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.95, side: THREE.DoubleSide, depthWrite: false, toneMapped: false }));
  m.position.copy(pos); m.lookAt(camera.position); scene.add(m);
  gsap.to(m.scale, { x: size * 4, y: size * 4, duration: 1.1, ease: 'power2.out' });
  gsap.to(m.material, { opacity: 0, duration: 1.1, onComplete: () => { scene.remove(m); m.geometry.dispose(); } });
}
function shake(amount = 0.25) {
  gsap.fromTo(camera.position, { x: '+=0' }, { x: `+=${amount}`, y: `+=${amount * 0.6}`, duration: 0.05, repeat: 7, yoyo: true, ease: 'sine.inOut' });
}
function bloomPulse(v = 1.8) { gsap.fromTo(bloom, { strength: v }, { strength: 0.95, duration: 1.2, ease: 'power2.out' }); }

/* ablation: remove a rule → its tests light up red (real evidence from validation S4) */
function ablate(ruleId) {
  const t = S.sel; if (!t) return; const ev = t.stages.S4_rule_ablations.per_rule[ruleId];
  if (!ev) { toast('`core` is always on — it is never ablated'); return; }
  const idxOf = (id) => t.rules.findIndex((r) => r.id === id);
  const on = !ev.dropped.every((d) => S.ablated.has(d));
  if (on) ev.dropped.forEach((d) => S.ablated.add(d)); else ev.dropped.forEach((d) => S.ablated.delete(d));
  const targets = []; P.trule.forEach((ri, i) => { if (ev.dropped.includes(t.rules[ri].id)) targets.push(i); });
  const hit = targets.slice(0, ev.caught_by || targets.length);
  hit.forEach((ci, k) => gsap.to(P.tstate[ci], { v: on ? 1 : 0, duration: 0.5, delay: k * 0.03 }));
  ev.dropped.forEach((d) => {
    const r = P.rules[idxOf(d)]; if (!r) return;
    gsap.to(r.orb.material.color, { ...new THREE.Color(on ? 0xef476f : r.color), duration: 0.4 });
    gsap.fromTo(r.orb.scale, { x: 2, y: 2, z: 2 }, { x: 1, y: 1, z: 1, duration: 0.9, ease: 'elastic.out(1,0.4)' });
    if (on) shockwave(r.orb.getWorldPosition(new THREE.Vector3()), 0xef476f, 3);
  });
  if (on) { shake(0.18); bloomPulse(1.6); }
  banner(on ? `S4 · remove “${ruleId}”${ev.dropped.length > 1 ? ` (+ ${ev.dropped.filter((d) => d !== ruleId).join(', ')})` : ''} → ${ev.caught_by} tests fail — the rule is independently tested`
    : `“${ruleId}” restored`);
  $$('#rules .rule').forEach((el) => el.classList.toggle('off', S.ablated.has(el.dataset.id)));
}
async function tourAblations(t, quiet) {
  if (!t) return; for (const r of t.rules) { if (r.id === 'core') continue; ablate(r.id); await sleep(quiet ? 260 : 700); }
  await sleep(quiet ? 500 : 1200);
  for (const r of t.rules) if (S.ablated.has(r.id)) { ablate(r.id); await sleep(80); }
}

/* ───────────────────────── Variation station ───────────────────────── */
let bars = [];
function buildVariation(t) {
  clearGroup(varG); bars = [];
  const fam = S.families.find((f) => f.repo === t.repo && f.family === t.family); const M = fam?.matrix;
  const grid = new THREE.GridHelper(20, 20, 0x2a3566, 0x1a2144); grid.position.y = -0.01; varG.add(grid);
  label(`${t.repo}/${t.family} · tests (rows) vs reference (cols)`, 'fam', varG, [0, 7.5, -8]);
  if (!M) { label('no variation matrix for this family yet', '', varG, [0, 2, 0]); return; }
  const n = M.variants.length, sp = 2.4, off = ((n - 1) * sp) / 2;
  M.m.forEach((row, i) => row.forEach((v, j) => {
    const h = Math.max(0.12, v * 6), diag = i === j;
    const col = diag ? 0xffd166 : tmpC.setHSL(0.02 + v * 0.38, 0.9, 0.55).getHex();
    const m = new THREE.Mesh(new THREE.BoxGeometry(1.5, h, 1.5), new THREE.MeshBasicMaterial({ color: new THREE.Color(col).multiplyScalar(0.5), toneMapped: false, transparent: true, opacity: 0.95 }));
    m.position.set(j * sp - off, h / 2, i * sp - off); m.scale.y = 0.001;
    m.userData = { type: 'bar', i, j, v, a: M.variants[i], b: M.variants[j], h }; varG.add(m); bars.push(m); pickables.push(m);
    gsap.to(m.scale, { y: 1, duration: 1.1, delay: 0.2 + (i + j) * 0.07, ease: 'back.out(1.6)' });
  }));
  M.variants.forEach((v, k) => { label(v.split('-')[1], 'gate', varG, [k * sp - off, 0, off + 2]); label(v.split('-')[1], 'gate', varG, [-off - 2, 0, k * sp - off]); });
  stationLabels(S.station);
}

/* ───────────────────────── interaction / picking ───────────────────────── */
const ray = new THREE.Raycaster(); const mouse = new THREE.Vector2(); const hoverEl = $('#hover');
let hovered = null;
function pick(e) {
  mouse.set((e.clientX / innerWidth) * 2 - 1, -(e.clientY / innerHeight) * 2 + 1); ray.setFromCamera(mouse, camera);
  const objs = [...pickables.filter((m) => m.parent), ...P.rules.map((r) => r.orb)];
  const hit = ray.intersectObjects(objs, false)[0]; return hit?.object || null;
}
canvas.addEventListener('pointermove', (e) => {
  const o = pick(e); hovered = o; canvas.style.cursor = o ? 'pointer' : 'grab';
  if (!o) { hoverEl.style.opacity = 0; return; }
  const u = o.userData; let html = '';
  if (u.type === 'task') { const t = S.tasks.find((x) => x.id === u.id); html = `<b>${esc(t.id)}</b><br>${t.rules.length} rules · ${t.f2p} tests · ${t.difficulty}<br><span style="color:var(--mut)">${t.stages.S5_mutation_kill.killed}/${t.stages.S5_mutation_kill.killed + t.stages.S5_mutation_kill.survived} mutants killed</span>`; }
  if (u.type === 'rule') { const r = S.sel.rules.find((x) => x.id === u.id); html = `<b>${esc(r.title)}</b><br><span style="color:var(--mut)">click to ablate (remove) this rule</span>`; }
  if (u.type === 'bar') html = `tests of <b>${u.a}</b><br>vs reference of <b>${u.b}</b><br>pass rate <b>${(u.v * 100).toFixed(0)}%</b>${u.i === u.j ? ' (own reference)' : ' — different behaviour'}`;
  hoverEl.innerHTML = html; hoverEl.style.left = e.clientX + 'px'; hoverEl.style.top = e.clientY + 'px'; hoverEl.style.opacity = 1;
});
canvas.addEventListener('click', (e) => {
  const o = pick(e); if (!o) return; const u = o.userData;
  if (u.type === 'task') selectTask(u.id, { fly: true });
  else if (u.type === 'rule') ablate(u.id);
  else if (u.type === 'bar') { shockwave(o.getWorldPosition(new THREE.Vector3()).setY(o.userData.h), 0xffffff, 2); gsap.fromTo(o.scale, { x: 1.25, z: 1.25 }, { x: 1, z: 1, duration: 0.6, ease: 'elastic.out(1,0.4)' }); }
});

/* ───────────────────────── UI: panels ───────────────────────── */
function toast(msg) { const d = document.createElement('div'); d.textContent = msg; $('#toast').appendChild(d); gsap.fromTo(d, { opacity: 0, y: -10 }, { opacity: 1, y: 0, duration: 0.3 }); setTimeout(() => gsap.to(d, { opacity: 0, duration: 0.4, onComplete: () => d.remove() }), 2600); }
function banner(msg) { const b = $('#banner'); b.textContent = msg; gsap.killTweensOf(b); gsap.fromTo(b, { opacity: 0, y: 20 }, { opacity: 1, y: 0, duration: 0.4 }); gsap.to(b, { opacity: 0, delay: 4.2, duration: 0.6 }); }
function log(line, cls = '') { const l = $('#log'); const d = document.createElement('div'); if (cls) d.className = cls === 'ok' || cls === 'bad' || cls === 'warn' ? cls : ''; d.textContent = line; l.appendChild(d); l.scrollTop = l.scrollHeight; }
function setTab(name) { $$('#tabs button').forEach((b) => b.classList.toggle('on', b.dataset.tab === name)); $$('.pane').forEach((p) => p.classList.toggle('on', p.id === 'tab-' + name)); }
$$('#tabs button').forEach((b) => b.addEventListener('click', () => setTab(b.dataset.tab)));
$$('#nav button').forEach((b) => b.addEventListener('click', () => gotoStation(b.dataset.st)));
addEventListener('keydown', (e) => { if (e.target.matches('input,select,textarea')) return; const k = { 1: 'atlas', 2: 'pipeline', 3: 'variation' }[e.key]; if (k) gotoStation(k); });
function gotoStation(st) { if (st !== 'atlas' && !S.sel) selectTask(S.tasks[0].id); flyTo(st); if (st === 'variation') buildVariation(S.sel); }
$('#mclose').addEventListener('click', () => $('#modal').classList.add('hide'));

function renderTaskList() {
  const root = $('#tasklist'); root.innerHTML = '';
  const groups = {}; S.tasks.forEach((t) => (groups[`${t.repo}/${t.family}`] ||= []).push(t));
  Object.entries(groups).forEach(([k, ts]) => {
    const [repo, fam] = k.split('/'); const f = document.createElement('div'); f.className = 'fam';
    f.innerHTML = `<span class="dot" style="color:#${(REPO_COL[repo] || 0xffffff).toString(16).padStart(6, '0')}"></span>${repo} · ${fam}`; root.appendChild(f);
    ts.forEach((t) => {
      const r = document.createElement('div'); r.className = 'trow' + (S.liveIds.has(t.id) ? ' live' : '') + (S.sel?.id === t.id ? ' on' : ''); r.dataset.id = t.id;
      r.innerHTML = `${t.id.split('/')[1]}<small>${S.liveIds.has(t.id) ? 'live ✦' : t.difficulty}</small>`; r.onclick = () => selectTask(t.id, { fly: true }); root.appendChild(r);
    });
  });
}
function renderStageList(t) {
  const info = stageInfo(t);
  $('#tab-task').innerHTML = `
    <h2 class="t">${esc(t.title)}</h2><div class="sub">${esc(t.id)} · base <code>${t.base_commit.slice(0, 8)}</code></div>
    <div class="chips"><span class="chip">${t.rules.length} rules</span><span class="chip">${t.f2p} fail→pass</span><span class="chip">${t.p2p} pass→pass</span>
    <span class="chip">${t.ref_lines} line patch</span><span class="chip">${t.difficulty}</span><span class="chip" style="color:var(--${t.valid ? 'ok' : 'bad'})">${t.valid ? 'valid' : 'invalid'}</span></div>
    <div class="row"><button class="btn" id="b-replay">▶ Replay validation</button><button class="btn ghost" id="b-tour">Ablation tour</button><button class="btn ghost" id="b-spec">View spec</button></div>
    <h4>Validation gates</h4><ol class="stages" id="stagelist">${STAGE_NAMES.map((n, i) => `<li data-i="${i}"><b>S${i + 1}</b><span>${n.slice(3)}</span><i>—</i></li>`).join('')}</ol>
    <h4>Rules — click to remove one (S4)</h4><div id="rules"></div>`;
  $('#b-replay').onclick = () => replay(t); $('#b-tour').onclick = () => { flyTo('pipeline'); tourAblations(t); };
  $('#b-spec').onclick = () => { $('#mbody').textContent = t.problem_md; $('#modal').classList.remove('hide'); };
}
function renderRules(t) {
  const root = $('#rules'); root.innerHTML = '';
  t.rules.forEach((r, i) => {
    const d = document.createElement('div'); d.className = 'rule'; d.dataset.id = r.id;
    d.innerHTML = `<b style="color:#${RULE_PAL[i % RULE_PAL.length].toString(16).padStart(6, '0')}">● ${esc(r.id)}</b> <small>${t.tests_by_rule[r.id] || 0} tests</small><div class="sub">${esc(r.title)}</div><p>${esc(r.requirement)}</p>`;
    d.onclick = (e) => { d.classList.toggle('open'); ablate(r.id); }; root.appendChild(d);
  });
}

/* ───────────────────────── Grader ───────────────────────── */
function renderGrader(t) {
  const p = $('#tab-grader');
  p.innerHTML = `<h4>Grade a candidate solution</h4><div class="sub">Applies the candidate patch + hidden tests at the pinned commit. ${S.live ? '<b style="color:var(--ok)">Real run.</b>' : 'Static mode replays recorded evidence.'}</div>
   <div class="row"><button class="btn" data-c="reference">Reference</button><button class="btn ghost" data-c="empty">Empty patch</button><button class="btn ghost" data-c="tamper">Edits the tests</button></div>
   <div class="row"><select id="abl">${t.rules.filter((r) => r.id !== 'core').map((r) => `<option value="${r.id}">forgets “${r.id}”</option>`).join('')}</select><button class="btn ghost" data-c="ablate">Run plausible-but-incomplete</button></div>
   <div id="gres"></div>`;
  $$('#tab-grader [data-c]').forEach((b) => b.onclick = () => grade(b.dataset.c === 'ablate' ? 'ablate:' + $('#abl').value : b.dataset.c));
}
function staticGrade(t, c) {
  if (c === 'tamper') return { verdict: 'REJECTED', reason: 'candidate edits protected test files' };
  const per = {}; t.rules.forEach((r) => (per[r.id] = [0, t.tests_by_rule[r.id] || 0]));
  let f = 0; const tot = t.f2p;
  if (c === 'reference') { t.rules.forEach((r) => (per[r.id][0] = per[r.id][1])); f = tot; }
  else if (c.startsWith('ablate:')) {
    const ev = t.stages.S4_rule_ablations.per_rule[c.slice(7)]; let left = ev.caught_by;
    t.rules.forEach((r) => { const fail = ev.dropped.includes(r.id) ? Math.min(left, per[r.id][1]) : 0; left -= fail; per[r.id][0] = per[r.id][1] - fail; });
    f = Object.values(per).reduce((a, [x]) => a + x, 0);
  }
  return { verdict: f === tot ? 'RESOLVED' : 'UNRESOLVED', f2p: [f, tot], p2p: [t.p2p, t.p2p], per, note: 'derived from recorded validation evidence' };
}
async function grade(c) {
  const t = S.sel; const box = $('#gres'); box.innerHTML = '<div class="res">running…</div>'; log(`grade ${t.id} :: ${c}`); let r;
  if (S.live) {
    try {
      const j = await (await fetch('/api/evaluate', { method: 'POST', body: JSON.stringify({ task: t.id, candidate: c }) })).json();
      if (j.error) throw new Error(j.error);
      if (j.verdict === 'REJECTED') r = { verdict: 'REJECTED', reason: j.reason };
      else { const pr = (s) => s.split('/').map(Number); r = { verdict: j.verdict, f2p: pr(j.fail_to_pass), p2p: pr(j.pass_to_pass), per: Object.fromEntries(Object.entries(j.per_rule).map(([k, v]) => [k, pr(v)])), note: `real grader run · ${j.seconds}s` }; }
    } catch (e) { box.innerHTML = `<div class="res" style="color:var(--bad)">${esc(e.message)}</div>`; return; }
  } else { await sleep(500); r = staticGrade(t, c); }
  flyTo('pipeline', 1.2);
  box.innerHTML = `<div class="res"><div class="verdict ${r.verdict}">${r.verdict}</div>
   ${r.reason ? `<div class="sub">${esc(r.reason)}</div>` : `<div class="kv"><span>fail→pass</span><b>${r.f2p[0]}/${r.f2p[1]}</b></div><div class="bar ${r.f2p[0] < r.f2p[1] ? 'partial' : ''}"><div data-w="${r.f2p[0] / Math.max(1, r.f2p[1])}"></div></div>
   <div class="kv"><span>pass→pass</span><b>${r.p2p[0]}/${r.p2p[1]}</b></div><div class="bar"><div data-w="${r.p2p[0] / Math.max(1, r.p2p[1])}"></div></div>
   <h4 style="margin-top:12px">per requirement</h4>${Object.entries(r.per).map(([k, [a, b]]) => `<div class="kv"><span>${esc(k)}</span><b>${a}/${b}</b></div><div class="bar ${a < b ? 'partial' : ''}"><div data-w="${b ? a / b : 1}"></div></div>`).join('')}
   <div class="sub">${esc(r.note)}</div>`}</div>`;
  $$('#gres .bar>div').forEach((d, i) => gsap.to(d, { width: (parseFloat(d.dataset.w) * 100) + '%', duration: 0.9, delay: i * 0.05, ease: 'power3.out' }));
  const col = { RESOLVED: 0x06d6a0, UNRESOLVED: 0xef476f, REJECTED: 0xffd166 }[r.verdict];
  shockwave(P.core.getWorldPosition(new THREE.Vector3()), col, 6); bloomPulse(2.2); gsap.to(P.coreGlow.material.color, { ...new THREE.Color(col), duration: 0.4, yoyo: true, repeat: 1 });
  banner(`${r.verdict} — ${r.f2p ? `${r.f2p[0]}/${r.f2p[1]} requirement tests pass` : r.reason}`);
  if (r.per) t.rules.forEach((ru, i) => { const [a, b] = r.per[ru.id] || [0, 0]; const fail = b - a; P.trule.forEach((ri, k) => { if (ri === i) gsap.to(P.tstate[k], { v: 0, duration: 0.1 }); }); let n = 0; P.trule.forEach((ri, k) => { if (ri === i && n++ < fail) gsap.to(P.tstate[k], { v: 1, duration: 0.5, delay: k * 0.01 }); }); });
  if (r.verdict === 'RESOLVED') P.tstate.forEach((s) => gsap.to(s, { v: 0, duration: 0.4 }));
}

/* ───────────────────────── Lab: compose your own task ───────────────────────── */
function closedSubsets(fam) { // how many distinct tasks can this family generate?
  const opt = fam.all_rules.filter((r) => r.id !== 'core'); let n = 0;
  for (let m = 0; m < 1 << opt.length; m++) { const sel = new Set(opt.filter((_, i) => m >> i & 1).map((r) => r.id)); if (opt.every((r) => !sel.has(r.id) || r.needs.every((d) => d === 'core' || sel.has(d)))) n++; }
  return n;
}
function renderLab() {
  const p = $('#tab-lab'); const fams = S.families.filter((f) => f.all_rules?.length);
  p.innerHTML = `<h4>Rule lab — compose a new task</h4><div class="sub">Pick a family and any combination of behavioural rules. ${S.live ? 'The factory will really generate, validate and package it.' : '<b style="color:var(--warn)">Static mode:</b> start the live server to build.'}</div>
   <div class="row"><select id="lfam">${fams.map((f) => `<option>${f.repo}/${f.family}</option>`).join('')}</select><input id="lseed" type="number" value="${40 + Math.floor(Math.random() * 50)}" style="width:80px" title="seed"></div>
   <div id="lrules"></div><div class="sub" id="lcount"></div><div class="row"><button class="btn" id="lbuild">⚡ Build &amp; validate live</button></div>`;
  const draw = () => {
    const fam = fams.find((f) => `${f.repo}/${f.family}` === $('#lfam').value);
    $('#lrules').innerHTML = fam.all_rules.map((r) => `<label class="check"><input type="checkbox" data-r="${r.id}" ${r.id === 'core' ? 'checked disabled' : ''}><span><b>${r.id}</b> — ${esc(r.title)}${r.needs.length ? `<small>needs ${r.needs.join(', ')}</small>` : ''}</span></label>`).join('');
    $('#lcount').innerHTML = `This family can generate <b style="color:var(--acc)">${closedSubsets(fam)}</b> distinct tasks (rule combinations) × parameter choices.`;
    $$('#lrules input').forEach((c) => c.onchange = () => { // auto-select dependencies
      if (c.checked) fam.all_rules.find((r) => r.id === c.dataset.r).needs.forEach((d) => { const x = $(`#lrules [data-r="${d}"]`); if (x) x.checked = true; });
    });
  };
  $('#lfam').onchange = draw; draw();
  $('#lbuild').disabled = !S.live;
  $('#lbuild').onclick = () => {
    const [repo, family] = $('#lfam').value.split('/'); const rules = $$('#lrules input:checked').map((c) => c.dataset.r);
    liveBuild({ repo, family, rules, seed: +$('#lseed').value, mutants: 8 });
  };
}

/* live build: stream the REAL factory log and drive the gates from it */
async function liveBuild(body) {
  if (S.running) return; S.running = true; flyTo('pipeline'); setTab('task');
  const seed = body.seed; const idGuess = `${body.repo}/${body.family}-${String(seed).padStart(2, '0')}`;
  log(`▶ live build ${idGuess} rules=${(body.rules || []).join(',') || 'sampled'}`);
  const tmp = S.tasks.find((t) => t.repo === body.repo && t.family === body.family) || S.tasks[0]; if (S.sel?.id !== tmp.id) selectTask(tmp.id, { fly: false }); resetGates();
  P.packet.visible = true; P.packet.position.x = 2.5;
  try {
    const res = await fetch('/api/build', { method: 'POST', body: JSON.stringify(body) });
    if (!res.ok) { toast((await res.json()).error || 'build failed'); S.running = false; return; }
    const rd = res.body.getReader(), dec = new TextDecoder(); let buf = '';
    for (;;) {
      const { value, done } = await rd.read(); if (done) break; buf += dec.decode(value, { stream: true });
      const parts = buf.split('\n\n'); buf = parts.pop();
      for (const p of parts) {
        const j = JSON.parse(p.replace(/^data: /, '')); if (j.done) continue; const line = j.line;
        const m = line.match(/^\s*S([1-7])\s+.+?\s{2,}(PASS|FAIL|WARN|n\/a)\b(.*)$/);
        if (m) { const i = +m[1] - 1, st = { PASS: 'ok', FAIL: 'bad', WARN: 'warn', 'n/a': 'na' }[m[2]]; await movePacket(i); activateGate(i, st, (m[3] || '').trim().replace(/^[(]|[)]$/g, '') || m[2]); if (i === 4) mutantBurst(); log(line.trim(), st === 'ok' ? 'ok' : st === 'bad' ? 'bad' : 'warn'); }
        else log(line);
      }
    }
    P.packet.visible = false;
    const j = await (await fetch('/api/live')).json();
    S.liveIds = new Set(j.tasks.map((t) => t.id)); const keep = S.tasks.filter((t) => !S.liveIds.has(t.id)); S.tasks = [...keep, ...j.tasks];
    S.families = mergeFamilies(S.families, j.families);
    buildAtlas(); renderTaskList(); const nt = j.tasks.find((t) => t.id === idGuess) || j.tasks.at(-1);
    if (nt) { selectTask(nt.id, { fly: false }); banner(`✦ new task generated & validated: ${nt.id}`); bloomPulse(2.4); }
  } catch (e) { toast('live build error: ' + e.message); }
  S.running = false;
}
function mergeFamilies(base, extra) {
  const out = base.map((f) => ({ ...f })); extra.forEach((f) => { const o = out.find((x) => x.repo === f.repo && x.family === f.family); if (o) o.tasks = [...new Set([...o.tasks, ...f.tasks])]; else out.push(f); }); return out;
}

/* ───────────────────────── Play: pluggable interactions ───────────────────────── */
const Interactions = [];
function registerInteraction(def) { Interactions.push(def); renderPlay(); }
const ctx = { THREE, gsap, scene, camera, controls, bloom, S, P, pipeG, atlasG, varG, flyTo, shockwave, shake, bloomPulse, toast, banner, log, glow, label, replay, ablate, selectTask, sleep, REPO_COL, RULE_PAL, registerInteraction };
window.TaskFactoryApp = ctx;
function renderPlay() {
  const p = $('#tab-play'); if (!p) return;
  p.innerHTML = `<h4>Interactions</h4><div class="sub">Click to run. Each one is a ~10 line plug-in.</div>${Interactions.map((x, i) => `<div class="ix" data-i="${i}"><span>${x.icon || '✦'}</span><div><b>${esc(x.label)}</b><small>${esc(x.desc || '')}</small></div></div>`).join('')}
   <h4 style="margin-top:16px">Add your own</h4>
<pre class="code">// app/custom-interactions.js
TaskFactoryApp.registerInteraction({
  id: 'confetti', icon: '🎉', label: 'Confetti',
  desc: 'burst of glow at the core',
  run({ THREE, gsap, scene, P, shockwave, glow }) {
    for (let i = 0; i &lt; 40; i++) {
      const s = glow(Math.random() * 0xffffff, 1.4);
      s.position.copy(P.core.getWorldPosition(new THREE.Vector3()));
      scene.add(s);
      gsap.to(s.position, { x: '+=' + (Math.random() - .5) * 14,
        y: '+=' + Math.random() * 10, z: '+=' + (Math.random() - .5) * 14,
        duration: 1.6, ease: 'power2.out', onComplete: () => scene.remove(s) });
    }
    shockwave(P.core.getWorldPosition(new THREE.Vector3()), 0xffffff, 6);
  }
});</pre>`;
  $$('#tab-play .ix').forEach((el) => el.onclick = () => { const d = Interactions[+el.dataset.i]; try { d.run(ctx); } catch (e) { toast(d.label + ': ' + e.message); console.error(e); } });
}
registerInteraction({ id: 'tour', icon: '🔬', label: 'Ablation tour', desc: 'remove every rule in turn: each one lights up its own tests', run: ({ flyTo, S, ablate }) => { flyTo('pipeline'); tourAblations(S.sel); } });
registerInteraction({ id: 'explode', icon: '💥', label: 'Explode tests', desc: 'scatter the test cubes and pull them back together', run: ({ P, gsap }) => { P.tstate.forEach((s, i) => gsap.to(s, { v: 1, duration: 0.4, delay: i * 0.01, yoyo: true, repeat: 1, ease: 'power2.out' })); } });
registerInteraction({ id: 'storm', icon: '🧬', label: 'Mutation storm', desc: 'replay S5: mutants are killed, survivors stay red', run: ({ P, flyTo, S }) => { flyTo('pipeline'); P.mstate.forEach((m) => (m.k = 0)); P.mstate.forEach((m, i) => { if (!m.survived) gsap.to(m, { k: 1, duration: 1.4, delay: 0.5 + i * 0.02 }); }); } });
registerInteraction({ id: 'warp', icon: '🌌', label: 'Warp tour', desc: 'cinematic flight through all three stations', run: async ({ flyTo, sleep }) => { flyTo('atlas', 1.6); await sleep(1800); flyTo('pipeline', 2.4); await sleep(2800); flyTo('variation', 2.4); await sleep(2800); flyTo('atlas', 2.4); } });
registerInteraction({ id: 'hue', icon: '🎨', label: 'Theme shift', desc: 'rotate the bloom and star colours', run: ({ gsap, bloom }) => { gsap.fromTo(bloom, { strength: 2.2, radius: 1.1 }, { strength: 0.95, radius: 0.65, duration: 1.6 }); gsap.to(stars.rotation, { y: '+=1.2', duration: 3, ease: 'power2.inOut' }); } });

/* ───────────────────────── selection + boot ───────────────────────── */
function selectTask(id, { fly = true } = {}) {
  const t = S.tasks.find((x) => x.id === id); if (!t) return; S.sel = t;
  buildPipeline(t); renderGrader(t); buildVariation(t); refreshSelectionHalo(); renderTaskList();
  $('#tab-task').scrollTop = 0; if (fly) { flyTo('pipeline'); }
  const i = stageInfo(t); if (fly) setTimeout(() => replay(t), 2300);
}

const clock = new THREE.Clock();
function loop() {
  const dt = Math.min(clock.getDelta(), 0.05), time = clock.elapsedTime;
  controls.update(); stars.rotation.y += dt * 0.004;
  atlasNodes.forEach((m) => { const u = m.userData; m.position.y = u.base.y + Math.sin(time * 0.8 + u.ph) * 0.25; m.scale.setScalar(m === hovered ? 1.35 : 1); });
  if (halo.visible) { halo.rotation.x = Math.PI / 2 + Math.sin(time) * 0.2; halo.rotation.z = time; const n = atlasNodes.find((m) => m.userData.id === S.sel?.id); if (n) halo.position.copy(n.position); }
  animatePipeline(dt, time);
  composer.render(); labelRenderer.render(scene, camera); requestAnimationFrame(loop);
}

async function boot() {
  let data = window.FACTORY_DATA;
  try { const h = await fetch('/api/health', { signal: AbortSignal.timeout(900) }); if (h.ok) { S.live = true; data = await (await fetch('/api/data')).json(); const lv = await (await fetch('/api/live')).json(); lv.tasks.forEach((t) => S.liveIds.add(t.id)); data.tasks.push(...lv.tasks); data.families = mergeFamilies(data.families, lv.families); } } catch (e) { /* static mode */ }
  S.tasks = data.tasks; S.families = data.families;
  const pill = $('#mode'); pill.className = 'pill ' + (S.live ? 'live' : 'static'); pill.textContent = S.live ? 'LIVE · real factory attached' : 'STATIC · recorded evidence';
  buildAtlas(); renderTaskList(); renderLab(); renderPlay();
  selectTask(S.tasks.find((t) => t.id === 'zod/unique-02')?.id || S.tasks[0].id, { fly: false }); S.sel = S.tasks[0];
  selectTask(S.sel.id, { fly: false });
  const t = S.sel; flyTo('atlas', 3.2);
  gsap.from('#top > *', { y: -30, opacity: 0, stagger: 0.12, duration: 0.9, ease: 'power3.out' });
  gsap.from('#left', { x: -40, opacity: 0, duration: 1, delay: 0.5, ease: 'power3.out' });
  gsap.from('#right', { x: 40, opacity: 0, duration: 1, delay: 0.7, ease: 'power3.out' });
  gsap.from('#console', { y: 40, opacity: 0, duration: 0.9, delay: 0.9 });
  log(`${S.tasks.length} tasks · ${S.families.length} families · ${S.live ? 'live backend connected' : 'static replay mode'}`, 'ok');
  setTimeout(() => banner('Click a glowing task to fly in and watch it get validated'), 2600);
  loop();
}
boot();
