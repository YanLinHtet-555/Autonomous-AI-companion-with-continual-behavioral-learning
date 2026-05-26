/**
 * neon-char.js
 * ─────────────────────────────────────────────────────────────────────────────
 * Builds and animates Neon's holographic 3D character using Three.js primitives.
 * No external model files — everything is constructed from geometry + materials.
 *
 * Public API (returned object):
 *   setEmotion(emotion)   — 'idle' | 'talking' | 'thinking' | 'happy' | 'sleepy'
 *   setLevel(level)       — 'baby' | 'kid' | 'adult' | 'scholar' | 'professional'
 *   dispose()             — clean up WebGL resources
 * ─────────────────────────────────────────────────────────────────────────────
 */

import * as THREE from 'three';

// ── Level definitions ────────────────────────────────────────────────────────
const LEVELS = {
  baby:         { color: 0x8899aa, glow: 0.3,  hairCount: 40,  orbs: false, crown: false },
  kid:          { color: 0x44aaff, glow: 0.6,  hairCount: 80,  orbs: false, crown: false },
  adult:        { color: 0x00eeff, glow: 1.0,  hairCount: 130, orbs: false, crown: false },
  scholar:      { color: 0xaa66ff, glow: 1.3,  hairCount: 200, orbs: true,  crown: false },
  professional: { color: 0xff44ff, glow: 1.8,  hairCount: 300, orbs: true,  crown: true  },
};

// ── Emotion state descriptors ────────────────────────────────────────────────
const EMOTIONS = {
  idle:     { leanZ: 0,     eyeGlow: 1.0, bobSpeed: 1.0, tiltX: 0 },
  talking:  { leanZ: 0.08,  eyeGlow: 2.2, bobSpeed: 1.5, tiltX: 0 },
  thinking: { leanZ: 0,     eyeGlow: 0.4, bobSpeed: 0.6, tiltX: 0.26 }, // ~15°
  happy:    { leanZ: 0,     eyeGlow: 2.8, bobSpeed: 2.4, tiltX: -0.1 },
  sleepy:   { leanZ: 0.12,  eyeGlow: 0.2, bobSpeed: 0.4, tiltX: 0.15 },
};

/**
 * Initialise Neon's scene and attach to the given canvas element.
 * @param {HTMLCanvasElement} canvas
 * @returns {{ setEmotion, setLevel, dispose }}
 */
export function initNeon(canvas) {
  // ── Renderer ───────────────────────────────────────────────────────────────
  const renderer = new THREE.WebGLRenderer({
    canvas,
    alpha: true,        // transparent background — CSS bg shows through
    antialias: true,
  });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setClearColor(0x000000, 0);  // fully transparent clear

  // ── Scene ──────────────────────────────────────────────────────────────────
  const scene = new THREE.Scene();
  scene.fog = new THREE.Fog(0x07070f, 8, 22);

  // ── Camera ─────────────────────────────────────────────────────────────────
  const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 50);
  camera.position.set(0, 0.4, 5.2);

  // ── Lighting ───────────────────────────────────────────────────────────────
  const ambientLight = new THREE.AmbientLight(0x223344, 0.6);
  scene.add(ambientLight);

  // Main rim light from the upper-left
  const rimLight = new THREE.DirectionalLight(0x00eeff, 0.9);
  rimLight.position.set(-3, 4, 2);
  scene.add(rimLight);

  // Back fill
  const fillLight = new THREE.DirectionalLight(0xff44ff, 0.3);
  fillLight.position.set(3, -1, -3);
  scene.add(fillLight);

  // ── Character group (everything under this rotates/translates together) ────
  const neonGroup = new THREE.Group();
  scene.add(neonGroup);

  // ── HEAD ───────────────────────────────────────────────────────────────────
  const headGeo  = new THREE.SphereGeometry(0.55, 32, 32);
  const headMat  = new THREE.MeshToonMaterial({ color: 0x8899aa });
  const headMesh = new THREE.Mesh(headGeo, headMat);
  headMesh.position.y = 1.5;
  neonGroup.add(headMesh);

  // ── EYES (two glowing spheres) ─────────────────────────────────────────────
  const eyeGeo = new THREE.SphereGeometry(0.1, 16, 16);
  const eyeMatL = new THREE.MeshBasicMaterial({ color: 0x00eeff });
  const eyeMatR = new THREE.MeshBasicMaterial({ color: 0x00eeff });

  const eyeL = new THREE.Mesh(eyeGeo, eyeMatL);
  const eyeR = new THREE.Mesh(eyeGeo, eyeMatR);
  eyeL.position.set(-0.2, 1.55, 0.48);
  eyeR.position.set( 0.2, 1.55, 0.48);
  neonGroup.add(eyeL, eyeR);

  // Point lights behind the eyes for glow
  const eyeLightL = new THREE.PointLight(0x00eeff, 0.8, 1.5);
  const eyeLightR = new THREE.PointLight(0x00eeff, 0.8, 1.5);
  eyeLightL.position.copy(eyeL.position);
  eyeLightR.position.copy(eyeR.position);
  neonGroup.add(eyeLightL, eyeLightR);

  // ── BODY — torso cylinder ─────────────────────────────────────────────────
  const torsoGeo = new THREE.CylinderGeometry(0.32, 0.42, 1.05, 12, 1, true);
  const torsoMat = new THREE.MeshToonMaterial({
    color: 0x0a1a2a,
    side: THREE.DoubleSide,
    transparent: true,
    opacity: 0.85,
  });
  const torsoMesh = new THREE.Mesh(torsoGeo, torsoMat);
  torsoMesh.position.y = 0.55;
  neonGroup.add(torsoMesh);

  // Shoulder plane (flat disc) — gives a wider silhouette
  const shoulderGeo = new THREE.CylinderGeometry(0.7, 0.7, 0.06, 20);
  const shoulderMat = new THREE.MeshToonMaterial({
    color: 0x001122,
    transparent: true,
    opacity: 0.6,
  });
  const shoulderMesh = new THREE.Mesh(shoulderGeo, shoulderMat);
  shoulderMesh.position.y = 1.02;
  neonGroup.add(shoulderMesh);

  // Neck
  const neckGeo  = new THREE.CylinderGeometry(0.13, 0.16, 0.22, 10);
  const neckMat  = new THREE.MeshToonMaterial({ color: 0x8899aa });
  const neckMesh = new THREE.Mesh(neckGeo, neckMat);
  neckMesh.position.y = 1.12;
  neonGroup.add(neckMesh);

  // ── AURA — large transparent outer shell ──────────────────────────────────
  const auraGeo  = new THREE.SphereGeometry(1.2, 32, 32);
  const auraMat  = new THREE.MeshBasicMaterial({
    color: 0x00eeff,
    transparent: true,
    opacity: 0.06,
    side: THREE.BackSide,   // render inner face so it's visible from outside
    depthWrite: false,
  });
  const auraMesh = new THREE.Mesh(auraGeo, auraMat);
  auraMesh.position.y = 0.9;
  neonGroup.add(auraMesh);

  // ── SCAN LINES — thin rings that drift upward ─────────────────────────────
  const scanLines = [];
  const scanMat   = new THREE.MeshBasicMaterial({
    color: 0x00eeff,
    transparent: true,
    opacity: 0.18,
    side: THREE.DoubleSide,
    depthWrite: false,
  });

  for (let i = 0; i < 4; i++) {
    const ringGeo  = new THREE.TorusGeometry(0.48 - i * 0.04, 0.012, 4, 40);
    const ringMesh = new THREE.Mesh(ringGeo, scanMat.clone());
    // Initial Y spread across the body
    ringMesh.position.y = -0.3 + i * 0.5;
    ringMesh.rotation.x = Math.PI / 2;
    neonGroup.add(ringMesh);
    scanLines.push({ mesh: ringMesh, baseY: -0.3 + i * 0.5, speed: 0.18 + i * 0.04 });
  }

  // ── HAIR — particle system ────────────────────────────────────────────────
  // We keep a reference so we can rebuild on level change
  let hairSystem = null;

  /**
   * Build a hair particle system with `count` points.
   * Points are scattered in a flowing shape around/above the head.
   */
  function buildHair(count, color) {
    if (hairSystem) {
      neonGroup.remove(hairSystem);
      hairSystem.geometry.dispose();
      hairSystem.material.dispose();
    }

    const positions  = new Float32Array(count * 3);
    const velocities = new Float32Array(count * 3); // stored as userData

    for (let i = 0; i < count; i++) {
      const angle  = Math.random() * Math.PI * 2;
      // Radial spread: concentrated near head, fewer far strands
      const r      = 0.35 + Math.random() * 0.55;
      const ySpread = Math.random();                // 0 = head equator, 1 = above
      const height  = 1.45 + ySpread * 0.85 + Math.random() * 0.2;

      positions[i * 3]     = Math.cos(angle) * r * (1 - ySpread * 0.4);
      positions[i * 3 + 1] = height;
      positions[i * 3 + 2] = Math.sin(angle) * r * (1 - ySpread * 0.4);

      // Random drift velocity (Y dominant — hair flows upward)
      velocities[i * 3]     = (Math.random() - 0.5) * 0.004;
      velocities[i * 3 + 1] = 0.006 + Math.random() * 0.012;
      velocities[i * 3 + 2] = (Math.random() - 0.5) * 0.004;
    }

    const hairGeo = new THREE.BufferGeometry();
    hairGeo.setAttribute('position', new THREE.BufferAttribute(positions, 3));

    const hairMat = new THREE.PointsMaterial({
      color,
      size: 0.04,
      sizeAttenuation: true,
      transparent: true,
      opacity: 0.75,
      depthWrite: false,
    });

    hairSystem = new THREE.Points(hairGeo, hairMat);
    hairSystem.userData.velocities    = velocities;
    hairSystem.userData.initialPositions = positions.slice(); // clone
    hairSystem.userData.count         = count;
    neonGroup.add(hairSystem);
  }

  // ── AMBIENT PARTICLE FIELD — 200 slow-drifting white specks ───────────────
  {
    const count      = 200;
    const pPositions = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      pPositions[i * 3]     = (Math.random() - 0.5) * 12;
      pPositions[i * 3 + 1] = (Math.random() - 0.5) * 12;
      pPositions[i * 3 + 2] = (Math.random() - 0.5) * 6 - 2;
    }
    const pGeo = new THREE.BufferGeometry();
    pGeo.setAttribute('position', new THREE.BufferAttribute(pPositions, 3));
    const pMat = new THREE.PointsMaterial({
      color: 0xffffff,
      size: 0.025,
      transparent: true,
      opacity: 0.4,
      sizeAttenuation: true,
      depthWrite: false,
    });
    const particles = new THREE.Points(pGeo, pMat);
    scene.add(particles);

    // Store for animation
    scene.userData.ambientParticles = particles;
  }

  // ── KNOWLEDGE ORBS — scholar & professional ──────────────────────────────
  // Orbiting glowing spheres added when level >= scholar
  const orbGroup = new THREE.Group();
  orbGroup.position.y = 0.9;
  neonGroup.add(orbGroup);

  function buildOrbs(visible) {
    // Remove existing orbs
    while (orbGroup.children.length) {
      const child = orbGroup.children[0];
      child.geometry && child.geometry.dispose();
      child.material && child.material.dispose();
      orbGroup.remove(child);
    }
    if (!visible) return;

    const orbColors = [0x00eeff, 0xaa66ff, 0xff44ff, 0x44ffaa];
    for (let i = 0; i < 4; i++) {
      const orbGeo  = new THREE.SphereGeometry(0.09, 12, 12);
      const orbMat  = new THREE.MeshBasicMaterial({
        color: orbColors[i % orbColors.length],
        transparent: true,
        opacity: 0.9,
      });
      const orb = new THREE.Mesh(orbGeo, orbMat);
      // Place each orb at 90° intervals to start
      const angle = (i / 4) * Math.PI * 2;
      orb.userData.orbitAngle  = angle;
      orb.userData.orbitRadius = 1.05 + (i % 2) * 0.15;
      orb.userData.orbitSpeed  = 0.6 + i * 0.15;
      orb.userData.orbitY      = 0.2 * Math.sin(angle);
      orbGroup.add(orb);

      // Tiny glow light per orb
      const orbLight = new THREE.PointLight(orbColors[i % orbColors.length], 0.35, 1.8);
      orb.add(orbLight);
    }
  }

  // ── CROWN RING — professional level ──────────────────────────────────────
  let crownMesh = null;

  function buildCrown(visible) {
    if (crownMesh) {
      neonGroup.remove(crownMesh);
      crownMesh.geometry.dispose();
      crownMesh.material.dispose();
      crownMesh = null;
    }
    if (!visible) return;

    const crownGeo  = new THREE.TorusGeometry(0.62, 0.025, 6, 60);
    const crownMat  = new THREE.MeshBasicMaterial({
      color: 0xff44ff,
      transparent: true,
      opacity: 0.85,
    });
    crownMesh = new THREE.Mesh(crownGeo, crownMat);
    crownMesh.position.y = 2.12;
    // Tilt slightly for style
    crownMesh.rotation.x = 0.25;
    neonGroup.add(crownMesh);
  }

  // ── Happy burst particles ─────────────────────────────────────────────────
  // Temporary burst spawned on happy emotion
  const burstGroup = new THREE.Group();
  scene.add(burstGroup);
  let burstParticles = [];

  function spawnHappyBurst() {
    // Clear previous burst
    for (const bp of burstParticles) {
      burstGroup.remove(bp.mesh);
      bp.mesh.geometry.dispose();
      bp.mesh.material.dispose();
    }
    burstParticles = [];

    const count = 24;
    for (let i = 0; i < count; i++) {
      const geo = new THREE.SphereGeometry(0.035, 6, 6);
      const mat = new THREE.MeshBasicMaterial({
        color: i % 2 === 0 ? 0x00eeff : 0xff44ff,
        transparent: true,
        opacity: 1,
      });
      const mesh = new THREE.Mesh(geo, mat);
      mesh.position.set(
        (Math.random() - 0.5) * 0.6,
        1.5 + Math.random() * 0.5,
        (Math.random() - 0.5) * 0.6
      );
      const speed = 0.04 + Math.random() * 0.06;
      const dir   = new THREE.Vector3(
        (Math.random() - 0.5) * 2,
        Math.random() * 2,
        (Math.random() - 0.5) * 2
      ).normalize().multiplyScalar(speed);
      burstGroup.add(mesh);
      burstParticles.push({ mesh, velocity: dir, life: 1.0 });
    }
  }

  // ── State ──────────────────────────────────────────────────────────────────
  let currentEmotion = 'idle';
  let currentLevel   = 'baby';
  let emotionTarget  = { ...EMOTIONS.idle };
  let emotionCurrent = { ...EMOTIONS.idle };

  // Apply a level immediately — updates materials and rebuilds features
  function applyLevel(levelName) {
    const def = LEVELS[levelName] || LEVELS.baby;
    currentLevel = levelName;

    // Head and eye color
    headMat.color.setHex(def.color);
    eyeMatL.color.setHex(def.color);
    eyeMatR.color.setHex(def.color);
    eyeLightL.color.setHex(def.color);
    eyeLightR.color.setHex(def.color);
    auraMat.color.setHex(def.color);
    // Update each cloned scan line material (they are independent instances)
    scanLines.forEach(s => s.mesh.material.color.setHex(def.color));

    // Eye brightness
    eyeLightL.intensity = def.glow * 0.8;
    eyeLightR.intensity = def.glow * 0.8;

    // Rebuild hair
    buildHair(def.hairCount, def.color);

    // Orbs and crown
    buildOrbs(def.orbs);
    buildCrown(def.crown);
  }

  // Bootstrap with baby level
  applyLevel('baby');

  // ── Resize handling ────────────────────────────────────────────────────────
  function resize() {
    const w = canvas.clientWidth;
    const h = canvas.clientHeight;
    if (renderer.domElement.width !== w || renderer.domElement.height !== h) {
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    }
  }
  window.addEventListener('resize', resize);
  resize();

  // ── Animation clock ────────────────────────────────────────────────────────
  const clock = new THREE.Clock();
  let   animFrame = null;

  function animate() {
    animFrame = requestAnimationFrame(animate);
    resize();

    const elapsed = clock.getElapsedTime();

    // ── Smooth emotion interpolation ──────────────────────────────────────
    const lerpSpeed = 0.06;
    emotionCurrent.leanZ    += (emotionTarget.leanZ    - emotionCurrent.leanZ)    * lerpSpeed;
    emotionCurrent.eyeGlow  += (emotionTarget.eyeGlow  - emotionCurrent.eyeGlow)  * lerpSpeed;
    emotionCurrent.bobSpeed += (emotionTarget.bobSpeed - emotionCurrent.bobSpeed) * lerpSpeed;
    emotionCurrent.tiltX    += (emotionTarget.tiltX    - emotionCurrent.tiltX)    * lerpSpeed;

    // ── Character float (idle Y-bob) ──────────────────────────────────────
    const bobY = Math.sin(elapsed * (Math.PI * 2 / 3) * emotionCurrent.bobSpeed) * 0.12;
    neonGroup.position.y  = bobY;
    neonGroup.rotation.y  = elapsed * 0.18;          // slow Y-axis rotation
    neonGroup.rotation.z  = emotionCurrent.leanZ;    // forward lean (talking)
    headMesh.rotation.x   = emotionCurrent.tiltX;    // head tilt (thinking)

    // ── Eye glow pulse ────────────────────────────────────────────────────
    const eyePulse      = 0.8 + 0.2 * Math.sin(elapsed * 5);
    const glowIntensity = emotionCurrent.eyeGlow * eyePulse;
    eyeLightL.intensity = glowIntensity;
    eyeLightR.intensity = glowIntensity;

    // ── Happy bounce ──────────────────────────────────────────────────────
    if (currentEmotion === 'happy') {
      neonGroup.position.y = bobY + Math.abs(Math.sin(elapsed * 8)) * 0.12;
    }

    // ── Aura breath ───────────────────────────────────────────────────────
    const auraScale = 1 + 0.04 * Math.sin(elapsed * 1.1);
    auraMesh.scale.setScalar(auraScale);

    // ── Scan lines drift upward ────────────────────────────────────────────
    for (const sl of scanLines) {
      sl.mesh.position.y += sl.speed * 0.012;
      // Loop back to bottom when they pass shoulder height
      if (sl.mesh.position.y > 1.6) {
        sl.mesh.position.y = -0.5;
      }
      // Fade out near the top
      const prog = (sl.mesh.position.y + 0.5) / 2.1;
      sl.mesh.material.opacity = 0.22 * (1 - prog * prog);
    }

    // ── Hair drift upward then loop ────────────────────────────────────────
    if (hairSystem) {
      const pos    = hairSystem.geometry.attributes.position;
      const vel    = hairSystem.userData.velocities;
      const init   = hairSystem.userData.initialPositions;
      const count  = hairSystem.userData.count;

      for (let i = 0; i < count; i++) {
        const ix = i * 3, iy = i * 3 + 1, iz = i * 3 + 2;

        pos.array[ix] += vel[ix];
        pos.array[iy] += vel[iy];
        pos.array[iz] += vel[iz];

        // When a particle drifts too far from its initial position, reset it
        const dy = pos.array[iy] - init[iy];
        const dx = pos.array[ix] - init[ix];
        const dz = pos.array[iz] - init[iz];

        if (dy > 0.55 || Math.abs(dx) > 0.35 || Math.abs(dz) > 0.35) {
          pos.array[ix] = init[ix];
          pos.array[iy] = init[iy];
          pos.array[iz] = init[iz];
        }
      }
      pos.needsUpdate = true;
    }

    // ── Knowledge orbs orbit ──────────────────────────────────────────────
    for (const orb of orbGroup.children) {
      if (!(orb instanceof THREE.Mesh)) continue;
      orb.userData.orbitAngle += orb.userData.orbitSpeed * 0.012;
      const a = orb.userData.orbitAngle;
      const r = orb.userData.orbitRadius;
      orb.position.x = Math.cos(a) * r;
      orb.position.z = Math.sin(a) * r;
      orb.position.y = Math.sin(a * 2) * 0.25; // gentle vertical weave
    }

    // ── Crown ring slow spin ──────────────────────────────────────────────
    if (crownMesh) {
      crownMesh.rotation.z = elapsed * 0.4;
    }

    // ── Ambient particles gentle drift ────────────────────────────────────
    const ap = scene.userData.ambientParticles;
    if (ap) {
      ap.rotation.y = elapsed * 0.012;
      ap.rotation.x = elapsed * 0.006;
    }

    // ── Happy burst particle physics ──────────────────────────────────────
    for (let i = burstParticles.length - 1; i >= 0; i--) {
      const bp = burstParticles[i];
      bp.life -= 0.022;
      bp.velocity.y -= 0.002; // gravity
      bp.mesh.position.addScaledVector(bp.velocity, 1);
      bp.mesh.material.opacity = Math.max(0, bp.life);
      if (bp.life <= 0) {
        burstGroup.remove(bp.mesh);
        bp.mesh.geometry.dispose();
        bp.mesh.material.dispose();
        burstParticles.splice(i, 1);
      }
    }

    renderer.render(scene, camera);
  }

  animate();

  // ── Public API ─────────────────────────────────────────────────────────────

  /**
   * Change Neon's displayed emotion.
   * Smoothly interpolates animation parameters to the new state.
   * @param {'idle'|'talking'|'thinking'|'happy'|'sleepy'} emotion
   */
  function setEmotion(emotion) {
    const def = EMOTIONS[emotion] || EMOTIONS.idle;
    currentEmotion = emotion;
    emotionTarget  = { ...def };

    if (emotion === 'happy') {
      spawnHappyBurst();
    }
  }

  /**
   * Evolve Neon to a new level — updates color, hair, orbs, crown.
   * @param {'baby'|'kid'|'adult'|'scholar'|'professional'} level
   */
  function setLevel(level) {
    if (LEVELS[level]) {
      applyLevel(level);
    }
  }

  /** Release WebGL resources and stop the render loop. */
  function dispose() {
    window.removeEventListener('resize', resize);
    cancelAnimationFrame(animFrame);
    renderer.dispose();
  }

  return { setEmotion, setLevel, dispose };
}
