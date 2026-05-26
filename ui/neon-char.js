/**
 * neon-char.js — Neon: chibi AI girl character (Three.js primitives only)
 *
 * Style: big chibi head, large green glowing eyes, dark blue hair + antennas,
 * headphones, white jacket, orange skirt, blue legs, animated arms.
 *
 * Public API:  setEmotion(emotion)  setLevel(level)  dispose()
 */

import * as THREE from 'three';

// ── Level definitions ────────────────────────────────────────────────────────
const LEVELS = {
  baby:         { eyeColor: 0x00cc44, glowColor: 0x00cc44, antColor: 0xffaa00, accentColor: 0xff9900, glow: 0.5,  showOrbs: false, showCrown: false },
  kid:          { eyeColor: 0x00dd55, glowColor: 0x44aaff, antColor: 0xffbb00, accentColor: 0xff9900, glow: 0.9,  showOrbs: false, showCrown: false },
  adult:        { eyeColor: 0x00ee44, glowColor: 0x00eeff, antColor: 0xffcc00, accentColor: 0xff9900, glow: 1.2,  showOrbs: false, showCrown: false },
  scholar:      { eyeColor: 0x44ffaa, glowColor: 0xaa66ff, antColor: 0xcc88ff, accentColor: 0xaa66ff, glow: 1.5,  showOrbs: true,  showCrown: false },
  professional: { eyeColor: 0x88ffcc, glowColor: 0xff44ff, antColor: 0xff88ff, accentColor: 0xff44ff, glow: 2.0,  showOrbs: true,  showCrown: true  },
};

// arm target angles per emotion  { z: shoulder raise,  x: forward tilt }
const ARM_POSES = {
  idle:     { lz: -0.25, rx: 0.10, lx: 0.10, rz: 0.25 },
  talking:  { lz: -0.55, rx: 0.20, lx: 0.20, rz: 0.70 },
  thinking: { lz: -0.20, rx: 0.10, lx: 0.80, rz: 0.20 },
  happy:    { lz: -1.10, rx: 0.10, lx: 0.10, rz: 1.10 },
  sleepy:   { lz:  0.20, rx: 0.05, lx: 0.05, rz: -0.20 },
};

const EMOTIONS = {
  idle:     { bobSpeed: 1.0, lean: 0,    tilt: 0,    eyeScale: 1.0 },
  talking:  { bobSpeed: 1.6, lean: 0.05, tilt: 0,    eyeScale: 1.05 },
  thinking: { bobSpeed: 0.6, lean: 0,    tilt: 0.22, eyeScale: 0.75 },
  happy:    { bobSpeed: 2.6, lean: 0,    tilt: -0.1, eyeScale: 1.15 },
  sleepy:   { bobSpeed: 0.3, lean: 0.18, tilt: 0.15, eyeScale: 0.55 },
};

export function initNeon(canvas) {
  // ── Renderer ──────────────────────────────────────────────────────────────
  const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setClearColor(0x000000, 0);

  // ── Scene ─────────────────────────────────────────────────────────────────
  const scene = new THREE.Scene();
  scene.fog = new THREE.Fog(0x07070f, 10, 24);

  // ── Camera ────────────────────────────────────────────────────────────────
  const camera = new THREE.PerspectiveCamera(40, 1, 0.1, 50);
  camera.position.set(0, 0.8, 5.8);

  // ── Lights ────────────────────────────────────────────────────────────────
  scene.add(new THREE.AmbientLight(0xffffff, 0.75));
  const keyLight = new THREE.DirectionalLight(0xffeedd, 1.1);
  keyLight.position.set(-2, 5, 3);
  scene.add(keyLight);
  const fillLight = new THREE.DirectionalLight(0x88aaff, 0.4);
  fillLight.position.set(3, 0, 2);
  scene.add(fillLight);

  // ── Root ──────────────────────────────────────────────────────────────────
  const root = new THREE.Group();
  scene.add(root);

  // ── Shared materials ──────────────────────────────────────────────────────
  const skinMat   = new THREE.MeshToonMaterial({ color: 0xffd5b8 });
  const hairMat   = new THREE.MeshToonMaterial({ color: 0x1a2d4a });
  const jacketMat = new THREE.MeshToonMaterial({ color: 0xe8eaf6 });
  const blueMat   = new THREE.MeshToonMaterial({ color: 0x2a4080 });
  const orangeMat = new THREE.MeshToonMaterial({ color: 0xff8c00 });
  const darkMat   = new THREE.MeshToonMaterial({ color: 0x1a2030 });

  // ═══════════════════════════════════════════════════════════════════════════
  // HEAD GROUP
  // ═══════════════════════════════════════════════════════════════════════════
  const headGroup = new THREE.Group();
  headGroup.position.y = 1.50;
  root.add(headGroup);

  // ── Skull ─────────────────────────────────────────────────────────────────
  const skull = new THREE.Mesh(new THREE.SphereGeometry(0.60, 32, 32), skinMat);
  skull.scale.y = 1.05;
  headGroup.add(skull);

  // ── Hair cap — covers top + back of head ─────────────────────────────────
  const hairCapGeo = new THREE.SphereGeometry(0.625, 28, 16, 0, Math.PI * 2, 0, Math.PI * 0.60);
  const hairCap    = new THREE.Mesh(hairCapGeo, hairMat);
  hairCap.position.y = 0.02;
  headGroup.add(hairCap);

  // Hair side flaps (cover ears area)
  function makeHairFlap(side) {
    const g = new THREE.SphereGeometry(0.30, 14, 10, 0, Math.PI * 2, 0, Math.PI * 0.55);
    const m = new THREE.Mesh(g, hairMat);
    m.scale.set(0.55, 1.0, 0.7);
    m.position.set(side * 0.58, -0.18, 0.05);
    headGroup.add(m);
  }
  makeHairFlap(-1);
  makeHairFlap(1);

  // Small hair tuft / spike on top
  const tuftGeo = new THREE.SphereGeometry(0.12, 8, 8);
  const tuft    = new THREE.Mesh(tuftGeo, hairMat);
  tuft.scale.set(0.6, 1.4, 0.6);
  tuft.position.set(0.08, 0.64, 0.12);
  tuft.rotation.z = -0.2;
  headGroup.add(tuft);

  // ── Ears ──────────────────────────────────────────────────────────────────
  function makeEar(side) {
    const e = new THREE.Mesh(new THREE.SphereGeometry(0.12, 10, 10), skinMat);
    e.scale.set(0.55, 0.7, 0.5);
    e.position.set(side * 0.60, -0.05, 0);
    headGroup.add(e);
  }
  makeEar(-1); makeEar(1);

  // ── EYES — large, round, glowing green ────────────────────────────────────
  const eyeGeoBase = new THREE.SphereGeometry(0.155, 20, 20);

  const eyeMatL  = new THREE.MeshBasicMaterial({ color: 0x00ee44 });
  const eyeMatR  = new THREE.MeshBasicMaterial({ color: 0x00ee44 });
  const eyeL     = new THREE.Mesh(eyeGeoBase, eyeMatL);
  const eyeR     = new THREE.Mesh(eyeGeoBase, eyeMatR);
  eyeL.position.set(-0.215, 0.10, 0.54);
  eyeR.position.set( 0.215, 0.10, 0.54);
  eyeL.scale.set(1.0, 1.15, 0.55);
  eyeR.scale.set(1.0, 1.15, 0.55);
  headGroup.add(eyeL, eyeR);

  // Pupils
  const pupilGeo = new THREE.SphereGeometry(0.08, 12, 12);
  const pupilMat = new THREE.MeshBasicMaterial({ color: 0x001a08 });
  const pupilL   = new THREE.Mesh(pupilGeo, pupilMat);
  const pupilR   = new THREE.Mesh(pupilGeo, pupilMat.clone());
  pupilL.position.set(-0.215, 0.09, 0.615);
  pupilR.position.set( 0.215, 0.09, 0.615);
  pupilL.scale.set(0.9, 1.0, 0.4);
  pupilR.scale.set(0.9, 1.0, 0.4);
  headGroup.add(pupilL, pupilR);

  // Highlight dots
  const hlGeo = new THREE.SphereGeometry(0.035, 8, 8);
  const hlMat = new THREE.MeshBasicMaterial({ color: 0xffffff });
  const hlL   = new THREE.Mesh(hlGeo, hlMat);
  const hlR   = new THREE.Mesh(hlGeo, hlMat.clone());
  hlL.position.set(-0.175, 0.16, 0.635);
  hlR.position.set( 0.255, 0.16, 0.635);
  headGroup.add(hlL, hlR);

  // Eye glow lights
  const eyeGlowL = new THREE.PointLight(0x00ee44, 0.7, 0.9);
  const eyeGlowR = new THREE.PointLight(0x00ee44, 0.7, 0.9);
  eyeGlowL.position.copy(eyeL.position);
  eyeGlowR.position.copy(eyeR.position);
  headGroup.add(eyeGlowL, eyeGlowR);

  // Eyelids / brow lines (thin dark arches above each eye)
  function makeBrow(side) {
    const b = new THREE.Mesh(
      new THREE.TorusGeometry(0.11, 0.018, 4, 16, Math.PI * 0.55),
      new THREE.MeshToonMaterial({ color: 0x1a2d4a }),
    );
    b.position.set(side * 0.215, 0.255, 0.545);
    b.rotation.z = side * 0.15;
    b.scale.set(1.0, 1.0, 0.3);
    headGroup.add(b);
  }
  makeBrow(-1); makeBrow(1);

  // Smile / mouth — small curved arc
  const smileMesh = new THREE.Mesh(
    new THREE.TorusGeometry(0.085, 0.018, 6, 16, Math.PI * 0.65),
    new THREE.MeshToonMaterial({ color: 0xcc5566 }),
  );
  smileMesh.position.set(0.015, -0.16, 0.575);
  smileMesh.rotation.z = Math.PI + 0.1;
  smileMesh.scale.set(1.0, 1.0, 0.3);
  headGroup.add(smileMesh);

  // ── ANTENNAS ──────────────────────────────────────────────────────────────
  const antStemMat = new THREE.MeshToonMaterial({ color: 0x334455 });
  const antTipMat  = new THREE.MeshBasicMaterial({ color: 0xffaa00 });

  function makeAntenna(side) {
    const g = new THREE.Group();
    // Stem
    const stem = new THREE.Mesh(new THREE.CylinderGeometry(0.014, 0.018, 0.28, 6), antStemMat);
    stem.position.y = 0.14;
    stem.rotation.z = side * 0.22;
    g.add(stem);
    // Tip sphere
    const tip = new THREE.Mesh(new THREE.SphereGeometry(0.042, 10, 10), antTipMat.clone());
    tip.position.set(side * 0.065, 0.30, 0);
    g.add(tip);
    // Glow
    const tl = new THREE.PointLight(0xffaa00, 0.5, 0.7);
    tl.position.copy(tip.position);
    g.add(tl);
    g.position.set(side * 0.20, 0.60, 0.12);
    headGroup.add(g);
    return { tipMesh: tip, tipLight: tl };
  }
  const antL = makeAntenna(-1);
  const antR = makeAntenna(1);

  // ── HEADPHONES ────────────────────────────────────────────────────────────
  const hpBodyMat = new THREE.MeshToonMaterial({ color: 0x2a3a5a });
  const hpRimMat  = new THREE.MeshToonMaterial({ color: 0x44aaff, transparent: true, opacity: 0.8 });

  function makeHeadphone(side) {
    const g = new THREE.Group();
    // Ear cup
    const cup = new THREE.Mesh(new THREE.CylinderGeometry(0.155, 0.155, 0.09, 16), hpBodyMat);
    cup.rotation.z = Math.PI / 2;
    g.add(cup);
    // Rim ring
    const rim = new THREE.Mesh(new THREE.TorusGeometry(0.155, 0.018, 6, 20), hpRimMat);
    rim.rotation.y = Math.PI / 2;
    g.add(rim);
    g.position.set(side * 0.66, 0.05, 0);
    headGroup.add(g);
  }
  makeHeadphone(-1); makeHeadphone(1);

  // Headphone band arc
  const bandCurve = new THREE.CubicBezierCurve3(
    new THREE.Vector3(-0.55, 0.35, 0),
    new THREE.Vector3(-0.20, 0.95, 0),
    new THREE.Vector3( 0.20, 0.95, 0),
    new THREE.Vector3( 0.55, 0.35, 0),
  );
  const bandGeo = new THREE.TubeGeometry(bandCurve, 20, 0.025, 6, false);
  headGroup.add(new THREE.Mesh(bandGeo, hpBodyMat));

  // ═══════════════════════════════════════════════════════════════════════════
  // NECK
  // ═══════════════════════════════════════════════════════════════════════════
  const neck = new THREE.Mesh(new THREE.CylinderGeometry(0.115, 0.13, 0.20, 10), skinMat);
  neck.position.y = 0.85;
  root.add(neck);

  // ═══════════════════════════════════════════════════════════════════════════
  // BODY
  // ═══════════════════════════════════════════════════════════════════════════
  const bodyGroup = new THREE.Group();
  root.add(bodyGroup);

  // ── Jacket / torso ────────────────────────────────────────────────────────
  const torso = new THREE.Mesh(
    new THREE.CylinderGeometry(0.30, 0.26, 0.60, 14, 1, false),
    jacketMat,
  );
  torso.position.y = 0.55;
  bodyGroup.add(torso);

  // Blue undershirt panel at front
  const shirt = new THREE.Mesh(
    new THREE.BoxGeometry(0.30, 0.40, 0.06),
    blueMat,
  );
  shirt.position.set(0, 0.56, 0.27);
  bodyGroup.add(shirt);

  // "NEON" chest badge — glowing panel
  const badgeMat = new THREE.MeshBasicMaterial({ color: 0x00eeff });
  const badge    = new THREE.Mesh(new THREE.BoxGeometry(0.18, 0.10, 0.02), badgeMat);
  badge.position.set(0, 0.60, 0.31);
  bodyGroup.add(badge);

  // Jacket collar flaps
  function makeCollar(side) {
    const c = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.18, 0.06), jacketMat);
    c.position.set(side * 0.10, 0.76, 0.26);
    c.rotation.z = side * 0.35;
    bodyGroup.add(c);
  }
  makeCollar(-1); makeCollar(1);

  // ── Orange skirt ──────────────────────────────────────────────────────────
  const skirt = new THREE.Mesh(
    new THREE.CylinderGeometry(0.38, 0.44, 0.34, 20, 1, false),
    orangeMat,
  );
  skirt.position.y = 0.20;
  bodyGroup.add(skirt);

  // Skirt hem line
  const hemRing = new THREE.Mesh(
    new THREE.TorusGeometry(0.43, 0.016, 6, 30),
    new THREE.MeshToonMaterial({ color: 0xcc6600 }),
  );
  hemRing.position.y = 0.04;
  hemRing.rotation.x = Math.PI / 2;
  bodyGroup.add(hemRing);

  // ── ARMS ──────────────────────────────────────────────────────────────────
  function makeArm(side, targetPose) {
    const g = new THREE.Group();
    g.position.set(side * 0.36, 0.73, 0);
    g.rotation.z = targetPose.z;
    g.rotation.x = targetPose.x;

    // Upper arm — jacket sleeve
    const upper = new THREE.Mesh(
      new THREE.CylinderGeometry(0.095, 0.085, 0.30, 10),
      jacketMat,
    );
    upper.position.y = -0.15;
    g.add(upper);

    // Lower arm — blue
    const lower = new THREE.Mesh(
      new THREE.CylinderGeometry(0.080, 0.072, 0.26, 10),
      blueMat,
    );
    lower.position.y = -0.44;
    g.add(lower);

    // Orange glove / hand
    const hand = new THREE.Mesh(
      new THREE.SphereGeometry(0.105, 14, 14),
      orangeMat,
    );
    hand.position.y = -0.63;
    hand.scale.set(1.0, 0.85, 0.9);
    g.add(hand);

    // Subtle glow on hand
    const hl = new THREE.PointLight(0xff8800, 0.35, 0.6);
    hl.position.y = -0.63;
    g.add(hl);

    root.add(g);
    return g;
  }

  const armGroupL = makeArm(-1, { z: -0.30, x: 0.12 });
  const armGroupR = makeArm( 1, { z:  0.30, x: 0.12 });

  let armPoseTarget = { ...ARM_POSES.idle };
  let armPoseCurrent = { ...ARM_POSES.idle };

  // ── LEGS ──────────────────────────────────────────────────────────────────
  function makeLeg(side) {
    const g = new THREE.Group();
    g.position.set(side * 0.155, 0.02, 0);

    // Upper leg
    const upper = new THREE.Mesh(new THREE.CylinderGeometry(0.105, 0.095, 0.32, 10), blueMat);
    upper.position.y = -0.16;
    g.add(upper);

    // Knee accent ring — orange
    const knee = new THREE.Mesh(
      new THREE.TorusGeometry(0.10, 0.022, 6, 18),
      orangeMat,
    );
    knee.position.y = -0.30;
    knee.rotation.x = Math.PI / 2;
    g.add(knee);

    // Lower leg
    const lower = new THREE.Mesh(new THREE.CylinderGeometry(0.090, 0.082, 0.28, 10), blueMat);
    lower.position.y = -0.48;
    g.add(lower);

    bodyGroup.add(g);
    return g;
  }
  makeLeg(-1); makeLeg(1);

  // ── FEET / shoes ──────────────────────────────────────────────────────────
  function makeFoot(side) {
    const g = new THREE.Group();
    g.position.set(side * 0.155, -0.62, 0.055);

    // Shoe body
    const shoe = new THREE.Mesh(new THREE.BoxGeometry(0.165, 0.105, 0.26), blueMat);
    g.add(shoe);

    // Teal sole
    const sole = new THREE.Mesh(
      new THREE.BoxGeometry(0.175, 0.030, 0.275),
      new THREE.MeshToonMaterial({ color: 0x00cccc }),
    );
    sole.position.y = -0.065;
    g.add(sole);

    // Orange accent stripe
    const stripe = new THREE.Mesh(
      new THREE.BoxGeometry(0.17, 0.028, 0.10),
      orangeMat,
    );
    stripe.position.set(0, 0.02, 0.08);
    g.add(stripe);

    bodyGroup.add(g);
  }
  makeFoot(-1); makeFoot(1);

  // ── Platform circle under feet ────────────────────────────────────────────
  const platform = new THREE.Mesh(
    new THREE.CylinderGeometry(0.50, 0.50, 0.035, 32),
    new THREE.MeshToonMaterial({ color: 0x00eeff, transparent: true, opacity: 0.25 }),
  );
  platform.position.y = -0.73;
  root.add(platform);
  // Glowing ring on platform edge
  const platformRing = new THREE.Mesh(
    new THREE.TorusGeometry(0.50, 0.014, 5, 40),
    new THREE.MeshBasicMaterial({ color: 0x00eeff, transparent: true, opacity: 0.7 }),
  );
  platformRing.position.y = -0.72;
  platformRing.rotation.x = Math.PI / 2;
  root.add(platformRing);

  // ═══════════════════════════════════════════════════════════════════════════
  // KNOWLEDGE ORBS (scholar+)
  // ═══════════════════════════════════════════════════════════════════════════
  const orbGroup = new THREE.Group();
  orbGroup.position.y = 1.0;
  root.add(orbGroup);

  function buildOrbs(visible) {
    while (orbGroup.children.length) {
      const c = orbGroup.children[0];
      c.geometry?.dispose(); c.material?.dispose();
      orbGroup.remove(c);
    }
    if (!visible) return;
    const colors = [0x00eeff, 0xaa66ff, 0xff44ff, 0x44ffaa];
    for (let i = 0; i < 4; i++) {
      const orb = new THREE.Mesh(
        new THREE.SphereGeometry(0.07, 10, 10),
        new THREE.MeshBasicMaterial({ color: colors[i] }),
      );
      orb.userData = { angle: (i / 4) * Math.PI * 2, radius: 1.05 + (i%2)*0.15, speed: 0.6 + i*0.15 };
      orb.add(new THREE.PointLight(colors[i], 0.4, 1.4));
      orbGroup.add(orb);
    }
  }

  // ── Crown (professional) ──────────────────────────────────────────────────
  let crownMesh = null;
  function buildCrown(visible) {
    if (crownMesh) { root.remove(crownMesh); crownMesh.geometry.dispose(); crownMesh.material.dispose(); crownMesh = null; }
    if (!visible) return;
    crownMesh = new THREE.Mesh(
      new THREE.TorusGeometry(0.55, 0.022, 6, 50),
      new THREE.MeshBasicMaterial({ color: 0xff44ff, transparent: true, opacity: 0.9 }),
    );
    crownMesh.position.y = 2.28;
    crownMesh.rotation.x = 0.20;
    root.add(crownMesh);
  }

  // ── Ambient particles ─────────────────────────────────────────────────────
  {
    const n = 160; const pos = new Float32Array(n * 3);
    for (let i = 0; i < n; i++) {
      pos[i*3]   = (Math.random()-0.5)*14;
      pos[i*3+1] = (Math.random()-0.5)*14;
      pos[i*3+2] = (Math.random()-0.5)*6 - 2;
    }
    const pg = new THREE.BufferGeometry();
    pg.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    scene.add(new THREE.Points(pg,
      new THREE.PointsMaterial({ color: 0xffffff, size: 0.020, transparent: true, opacity: 0.30, sizeAttenuation: true, depthWrite: false })
    ));
  }

  // ── Happy burst ───────────────────────────────────────────────────────────
  const burstGroup = new THREE.Group();
  scene.add(burstGroup);
  let burstParticles = [];

  function spawnBurst() {
    burstParticles.forEach(b => { burstGroup.remove(b.mesh); b.mesh.geometry.dispose(); b.mesh.material.dispose(); });
    burstParticles = [];
    for (let i = 0; i < 22; i++) {
      const mesh = new THREE.Mesh(
        new THREE.SphereGeometry(0.032, 5, 5),
        new THREE.MeshBasicMaterial({ color: i%2===0 ? 0x00eeff : 0xff8c00, transparent: true, opacity: 1 }),
      );
      mesh.position.set((Math.random()-0.5)*0.6, 1.5+Math.random()*0.5, (Math.random()-0.5)*0.6);
      const dir = new THREE.Vector3((Math.random()-0.5)*2, Math.random()*2+0.5, (Math.random()-0.5)*2).normalize().multiplyScalar(0.04+Math.random()*0.05);
      burstGroup.add(mesh);
      burstParticles.push({ mesh, velocity: dir, life: 1.0 });
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // STATE
  // ═══════════════════════════════════════════════════════════════════════════
  let currentEmotion = 'idle';
  let emotionTarget  = { ...EMOTIONS.idle };
  let emotionCurrent = { ...EMOTIONS.idle };

  function applyLevel(name) {
    const def = LEVELS[name] || LEVELS.baby;
    eyeMatL.color.setHex(def.eyeColor);
    eyeMatR.color.setHex(def.eyeColor);
    eyeGlowL.color.setHex(def.eyeColor);
    eyeGlowR.color.setHex(def.eyeColor);
    eyeGlowL.intensity = def.glow * 0.7;
    eyeGlowR.intensity = def.glow * 0.7;
    antL.tipMesh.material.color.setHex(def.antColor);
    antR.tipMesh.material.color.setHex(def.antColor);
    antL.tipLight.color.setHex(def.antColor);
    antR.tipLight.color.setHex(def.antColor);
    badgeMat.color.setHex(def.glowColor);
    platformRing.material.color.setHex(def.glowColor);
    buildOrbs(def.showOrbs);
    buildCrown(def.showCrown);
  }

  applyLevel('baby');

  // ── Resize ────────────────────────────────────────────────────────────────
  function resize() {
    const w = canvas.clientWidth, h = canvas.clientHeight;
    if (renderer.domElement.width !== w || renderer.domElement.height !== h) {
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    }
  }
  window.addEventListener('resize', resize);
  resize();

  // ── Animation loop ────────────────────────────────────────────────────────
  let _currentLevel = 'baby';
  const clock = new THREE.Clock();
  let animFrame = null;
  const K = 0.07;   // lerp factor per frame

  function animate() {
    animFrame = requestAnimationFrame(animate);
    resize();
    const t = clock.getElapsedTime();

    // Smooth emotion lerp
    emotionCurrent.bobSpeed += (emotionTarget.bobSpeed - emotionCurrent.bobSpeed) * K;
    emotionCurrent.lean     += (emotionTarget.lean     - emotionCurrent.lean)     * K;
    emotionCurrent.tilt     += (emotionTarget.tilt     - emotionCurrent.tilt)     * K;
    emotionCurrent.eyeScale += (emotionTarget.eyeScale - emotionCurrent.eyeScale) * K;

    // Body bob
    const bobY = Math.sin(t * Math.PI * 2 / 3 * emotionCurrent.bobSpeed) * 0.10;
    root.position.y  = currentEmotion === 'happy' ? bobY + Math.abs(Math.sin(t * 7)) * 0.09 : bobY;
    root.rotation.z  = emotionCurrent.lean;
    root.rotation.y  = Math.sin(t * 0.4) * 0.08;    // gentle idle sway

    // Head motion
    headGroup.rotation.x = emotionCurrent.tilt;
    headGroup.rotation.z = Math.sin(t * 0.7) * 0.04; // subtle head bob

    // Eye blink + scale
    const blinkCycle = t % 4.2;
    const blinkSq    = blinkCycle > 4.0 ? 0.08 : 1.0;
    eyeL.scale.set(1.0, emotionCurrent.eyeScale * blinkSq, 0.55);
    eyeR.scale.set(1.0, emotionCurrent.eyeScale * blinkSq, 0.55);

    // Eye glow pulse
    const ep = 0.88 + 0.12 * Math.sin(t * 4.5);
    eyeGlowL.intensity = emotionCurrent.eyeScale * ep * (LEVELS[_currentLevel]?.glow ?? 1.0) * 0.7;
    eyeGlowR.intensity = eyeGlowL.intensity;

    // Antenna tips pulse
    const ap = 0.5 + 0.5 * Math.abs(Math.sin(t * 2.5));
    antL.tipLight.intensity = ap * 0.5;
    antR.tipLight.intensity = ap * 0.5;

    // Arm animation
    armPoseCurrent.lz += (armPoseTarget.lz - armPoseCurrent.lz) * K;
    armPoseCurrent.rz += (armPoseTarget.rz - armPoseCurrent.rz) * K;
    armPoseCurrent.lx += (armPoseTarget.lx - armPoseCurrent.lx) * K;
    armPoseCurrent.rx += (armPoseTarget.rx - armPoseCurrent.rx) * K;
    armGroupL.rotation.z = armPoseCurrent.lz;
    armGroupR.rotation.z = armPoseCurrent.rz;
    armGroupL.rotation.x = armPoseCurrent.lx;
    armGroupR.rotation.x = armPoseCurrent.rx;
    // Idle arm swing
    if (currentEmotion === 'idle') {
      armGroupL.rotation.x = armPoseCurrent.lx + Math.sin(t * 1.2) * 0.05;
      armGroupR.rotation.x = armPoseCurrent.rx - Math.sin(t * 1.2) * 0.05;
    }

    // Badge pulse
    badgeMat.color.setHSL(
      (t * 0.08) % 1,
      0.9,
      0.55 + 0.1 * Math.sin(t * 3),
    );

    // Orbs orbit
    orbGroup.children.forEach(orb => {
      if (!orb.userData.angle) return;
      orb.userData.angle += orb.userData.speed * 0.012;
      orb.position.x = Math.cos(orb.userData.angle) * orb.userData.radius;
      orb.position.z = Math.sin(orb.userData.angle) * orb.userData.radius;
      orb.position.y = Math.sin(orb.userData.angle * 2) * 0.2;
    });

    // Crown spin
    if (crownMesh) crownMesh.rotation.z = t * 0.35;

    // Platform ring pulse
    platformRing.material.opacity = 0.4 + 0.3 * Math.sin(t * 2.2);

    // Burst particles
    for (let i = burstParticles.length - 1; i >= 0; i--) {
      const b = burstParticles[i];
      b.life -= 0.020;
      b.velocity.y -= 0.0018;
      b.mesh.position.addScaledVector(b.velocity, 1);
      b.mesh.material.opacity = Math.max(0, b.life);
      if (b.life <= 0) {
        burstGroup.remove(b.mesh);
        b.mesh.geometry.dispose(); b.mesh.material.dispose();
        burstParticles.splice(i, 1);
      }
    }

    renderer.render(scene, camera);
  }

  animate();

  // ── Public API ────────────────────────────────────────────────────────────
  function setEmotion(emotion) {
    currentEmotion  = emotion;
    emotionTarget   = { ...(EMOTIONS[emotion] || EMOTIONS.idle) };
    armPoseTarget   = { ...(ARM_POSES[emotion] || ARM_POSES.idle) };
    if (emotion === 'happy') spawnBurst();
  }

  function setLevel(level) {
    if (LEVELS[level]) { _currentLevel = level; applyLevel(level); }
  }

  function dispose() {
    window.removeEventListener('resize', resize);
    cancelAnimationFrame(animFrame);
    renderer.dispose();
  }

  return { setEmotion, setLevel, dispose };
}
