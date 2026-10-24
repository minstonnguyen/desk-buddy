// desk-buddy character page.
//
// Avatar priority:
//   1. Video avatar — realistic clips in character/media/ (idle.mp4,
//      listening.mp4, working.mp4, speaking.mp4), crossfaded per state.
//   2. character/model.vrm (three-vrm), when present.
//   3. A cute procedural placeholder character from three.js primitives.
// All share the same four animation states, driven by the controller's
// /api/state endpoint (polled every 200 ms):
//   idle      - gentle bobbing
//   listening - lean in, head tilted toward the speaker
//   working   - typing arm bobbing + slight body sway
//   speaking  - mouth driven by the real TTS audio amplitude envelope
//               (VRM: 'aa' expression; placeholder: mouth mesh scale)

import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { VRMLoaderPlugin } from '@pixiv/three-vrm';

const stage = document.getElementById('stage');
const stateLabel = document.getElementById('state');

const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
renderer.setPixelRatio(window.devicePixelRatio);
renderer.setSize(window.innerWidth, window.innerHeight);
stage.appendChild(renderer.domElement);

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(30, window.innerWidth / window.innerHeight, 0.1, 20);
camera.position.set(0, 1.35, 3.2);

scene.add(new THREE.AmbientLight(0xffffff, 0.9));
const dir = new THREE.DirectionalLight(0xffffff, 1.2);
dir.position.set(2, 4, 3);
scene.add(dir);

let currentState = 'idle';
let amplitude = 0;
let videoActive = false;
let lastVideoState = null;
const vidEls = [];
let vidFront = 0;
let vrm = null;          // three-vrm model, when loaded
let rig = null;          // placeholder rig (meshes), when used

// ---------- placeholder character (three.js primitives) ----------
function buildPlaceholder() {
  const g = new THREE.Group();
  const mat = (c) => new THREE.MeshStandardMaterial({ color: c, roughness: 0.7 });

  const body = new THREE.Mesh(new THREE.SphereGeometry(0.55, 32, 32), mat(0x7fd4c1));
  body.scale.set(1, 1.15, 0.9);
  body.position.y = 0.62;
  g.add(body);

  const head = new THREE.Mesh(new THREE.SphereGeometry(0.42, 32, 32), mat(0xffe3c2));
  head.position.y = 1.55;
  g.add(head);

  const eyeMat = new THREE.MeshStandardMaterial({ color: 0x222222, roughness: 0.3 });
  for (const side of [-1, 1]) {
    const eye = new THREE.Mesh(new THREE.SphereGeometry(0.05, 16, 16), eyeMat);
    eye.position.set(0.16 * side, 1.6, 0.38);
    g.add(eye);
    const blush = new THREE.Mesh(
      new THREE.SphereGeometry(0.07, 16, 16),
      new THREE.MeshStandardMaterial({ color: 0xffa8a8, roughness: 1 })
    );
    blush.scale.set(1, 0.6, 0.3);
    blush.position.set(0.3 * side, 1.45, 0.36);
    g.add(blush);
  }

  // Mouth: scaled vertically by speaking amplitude.
  const mouth = new THREE.Mesh(
    new THREE.SphereGeometry(0.06, 16, 16),
    new THREE.MeshStandardMaterial({ color: 0x5b3a3a, roughness: 0.6 })
  );
  mouth.scale.set(1.4, 0.25, 0.5);
  mouth.position.set(0, 1.38, 0.4);
  g.add(mouth);

  // Arms on shoulder pivots so typing can rotate them.
  const armGeo = new THREE.CapsuleGeometry(0.09, 0.4, 8, 16);
  const arms = {};
  for (const side of ['left', 'right']) {
    const pivot = new THREE.Group();
    pivot.position.set(0.55 * (side === 'left' ? -1 : 1), 1.0, 0);
    const arm = new THREE.Mesh(armGeo, mat(0x7fd4c1));
    arm.position.y = -0.28;
    pivot.add(arm);
    pivot.rotation.z = (side === 'left' ? -1 : 1) * 0.5;
    g.add(pivot);
    arms[side] = pivot;
  }

  // A tiny laptop in front, for the working state.
  const laptopBase = new THREE.Mesh(new THREE.BoxGeometry(0.6, 0.03, 0.4), mat(0x4a5568));
  laptopBase.position.set(0, 0.32, 0.55);
  g.add(laptopBase);
  const laptopScreen = new THREE.Mesh(new THREE.BoxGeometry(0.6, 0.4, 0.03), mat(0x4a5568));
  laptopScreen.position.set(0, 0.52, 0.38);
  laptopScreen.rotation.x = -0.3;
  g.add(laptopScreen);

  scene.add(g);
  return { group: g, head, arms, mouth };
}

// ---------- VRM loading (optional) ----------
async function tryLoadVrm() {
  try {
    const head = await fetch('model.vrm', { method: 'HEAD' });
    if (!head.ok) return null;
  } catch {
    return null; // no model file -> placeholder
  }
  try {
    const loader = new GLTFLoader();
    loader.register((parser) => new VRMLoaderPlugin(parser));
    const gltf = await loader.loadAsync('model.vrm');
    const model = gltf.userData.vrm;
    model.scene.position.y = 0;
    scene.add(model.scene);
    return model;
  } catch (err) {
    console.warn('VRM load failed, using placeholder character:', err);
    return null;
  }
}

// ---------- video avatar (character/media/*.mp4) ----------
async function tryVideoMode() {
  try {
    const head = await fetch('media/idle.mp4', { method: 'HEAD' });
    if (!head.ok) return false;
  } catch {
    return false; // no clips -> fall through to VRM / placeholder
  }
  for (let i = 0; i < 2; i++) {
    const v = document.createElement('video');
    v.className = 'vid';
    v.muted = true;
    v.loop = true;
    v.playsInline = true;
    v.autoplay = true;
    stage.appendChild(v);
    vidEls.push(v);
  }
  // Preload the other state clips so state switches are instant.
  for (const s of ['listening', 'working', 'speaking']) {
    const pre = document.createElement('video');
    pre.muted = true;
    pre.preload = 'auto';
    pre.src = `media/${s}.mp4`;
    pre.style.display = 'none';
    stage.appendChild(pre);
  }
  document.getElementById('hint').textContent =
    'desk-buddy · video avatar (character/media/)';
  videoActive = true;
  syncVideo();
  // Gentle scale pulse while speaking, driven by the TTS envelope.
  setInterval(() => {
    const target = currentState === 'speaking' ? 1 + amplitude * 0.03 : 1;
    for (const v of vidEls) v.style.transform = `scale(${target})`;
  }, 100);
  return true;
}

function syncVideo() {
  if (!videoActive || currentState === lastVideoState) return;
  lastVideoState = currentState;
  const back = vidEls[1 - vidFront];
  const front = vidEls[vidFront];
  back.onerror = () => {
    // A missing state clip falls back to the idle clip.
    if (!back.src.endsWith('media/idle.mp4')) back.src = 'media/idle.mp4';
  };
  back.src = `media/${currentState}.mp4`;
  const swap = () => {
    back.classList.add('on');
    front.classList.remove('on');
    vidFront = 1 - vidFront;
    back.oncanplay = null;
  };
  back.oncanplay = swap;
  back.play().catch(() => {});
  if (back.readyState >= 3) swap();
}

// ---------- state polling ----------
async function pollState() {
  try {
    const res = await fetch('/api/state');
    if (res.ok) {
      const data = await res.json();
      currentState = data.state || 'idle';
      amplitude = data.amplitude || 0;
      stateLabel.textContent = currentState;
      if (videoActive) syncVideo();
    }
  } catch {
    // Controller not reachable (e.g. page opened as a file): stay idle.
  }
}
setInterval(pollState, 200);
pollState();

// ---------- animation ----------
const clock = new THREE.Clock();

function animatePlaceholder(t) {
  const { group, head, arms, mouth } = rig;
  group.position.y = 0;
  group.rotation.set(0, 0, 0);
  head.rotation.set(0, 0, 0);
  if (currentState === 'idle') {
    group.position.y = Math.sin(t * 1.5) * 0.03;
  } else if (currentState === 'listening') {
    group.rotation.z = 0.08;
    head.rotation.z = 0.12;
    head.rotation.y = Math.sin(t * 1.2) * 0.15;
  } else if (currentState === 'working') {
    group.rotation.z = Math.sin(t * 2) * 0.02;
    const bob = Math.sin(t * 10) * 0.35;
    arms.left.rotation.x = bob;
    arms.right.rotation.x = -bob;
  }
  if (currentState === 'speaking') {
    mouth.scale.y = 0.25 + amplitude * 1.4;
  } else {
    mouth.scale.y = 0.25;
  }
}

function bone(model, name) {
  try {
    return model.humanoid.getNormalizedBoneNode(name);
  } catch {
    return null;
  }
}

function animateVrm(t) {
  const s = vrm.scene;
  s.position.y = 0;
  s.rotation.set(0, 0, 0);
  const head = bone(vrm, 'head');
  const neck = bone(vrm, 'neck');
  const armL = bone(vrm, 'leftUpperArm');
  const armR = bone(vrm, 'rightUpperArm');
  if (currentState === 'idle') {
    s.position.y = Math.sin(t * 1.5) * 0.02;
  } else if (currentState === 'listening') {
    s.rotation.z = 0.05;
    if (head) head.rotation.z = 0.12;
  } else if (currentState === 'working') {
    s.rotation.z = Math.sin(t * 2) * 0.015;
    const bob = Math.sin(t * 10) * 0.25;
    if (armL) armL.rotation.x = bob;
    if (armR) armR.rotation.x = -bob;
  }
  if (vrm.expressionManager) {
    const open = currentState === 'speaking' ? amplitude : 0;
    vrm.expressionManager.setValue('aa', open);
    vrm.expressionManager.update();
  }
  if (neck && currentState !== 'listening') neck.rotation.z = 0;
}

function loop() {
  requestAnimationFrame(loop);
  const t = clock.getElapsedTime();
  if (vrm) animateVrm(t);
  else if (rig) animatePlaceholder(t);
  renderer.render(scene, camera);
}

window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});

// ---------- boot ----------
const videoMode = await tryVideoMode();
if (!videoMode) {
  vrm = await tryLoadVrm();
  if (!vrm) rig = buildPlaceholder();
  loop();
}
