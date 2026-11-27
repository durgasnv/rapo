"use client";

import { useEffect, useRef } from "react";
import * as THREE from "three";

const TEAMS = 6;
const TEAM_SIZE = 4;
const WAITLIST = 4;
const DRIFT = 0.5;
const FOV = 35;
const CAMERA_Z = 14;
const WIDE_BREAKPOINT = 1100;

type Vec3 = [number, number, number];

type SceneData = {
  participants: number;
  total: number;
  scatter: Vec3[];
  roster: Vec3[];
  teams: Vec3[];
  teamOf: number[];
  teamPairs: [number, number][];
  histPairs: [number, number][];
};

/** Deterministic LCG so every visitor sees the same arrangement. */
function rng(seed: number) {
  let s = seed >>> 0;
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 4294967296;
  };
}

function smoothstep(a: number, b: number, x: number) {
  const k = Math.max(0, Math.min(1, (x - a) / (b - a)));
  return k * k * (3 - 2 * k);
}

function buildData(): SceneData {
  const size = TEAM_SIZE;
  const N = TEAMS * size;
  const M = N + WAITLIST;
  const rand = rng(11);
  const scatter: Vec3[] = [];
  const roster: Vec3[] = [];
  const teams: Vec3[] = [];
  const teamOf: number[] = [];

  for (let i = 0; i < M; i++) {
    scatter.push([(rand() - 0.5) * 9, (rand() - 0.5) * 6, (rand() - 0.5) * 5]);
  }

  const rows = Math.ceil(N / 6);
  const gap = 0.82;
  for (let i = 0; i < N; i++) {
    const c = i % 6;
    const row = Math.floor(i / 6);
    roster.push([(c - 2.5) * gap, ((rows - 1) / 2 - row) * gap + 0.5, 0]);
  }
  for (let j = 0; j < WAITLIST; j++) {
    roster.push([(j - 1.5) * gap, ((rows - 1) / 2 - rows) * gap - 0.4, 0]);
  }

  const perm = [...Array(N).keys()];
  for (let i = N - 1; i > 0; i--) {
    const k = Math.floor(rand() * (i + 1));
    [perm[i], perm[k]] = [perm[k], perm[i]];
  }

  const members: number[][] = [];
  for (let t = 0; t < TEAMS; t++) {
    const cx = ((t % 3) - 1) * 2.7;
    const cy = (t < 3 ? 1.35 : -1.35) + 0.5;
    members.push([]);
    for (let k = 0; k < size; k++) {
      const id = perm[t * size + k];
      teamOf[id] = t;
      members[t].push(id);
      const a = Math.PI / 2 + Math.PI / size + (k / size) * Math.PI * 2;
      teams[id] = [cx + Math.cos(a) * 0.62, cy + Math.sin(a) * 0.62, 0];
    }
  }
  for (let j = 0; j < WAITLIST; j++) teams[N + j] = [(j - 1.5) * 0.6, -2.9, 0];

  const teamPairs: [number, number][] = [];
  for (const m of members) {
    for (let a = 0; a < m.length; a++) {
      for (let b = a + 1; b < m.length; b++) teamPairs.push([m[a], m[b]]);
    }
  }

  // History lines only connect people who end up on *different* teams:
  // that is the whole point of the regroup step.
  const histPairs: [number, number][] = [];
  const seen = new Set<string>();
  while (histPairs.length < 18) {
    const a = Math.floor(rand() * N);
    const b = Math.floor(rand() * N);
    const key = `${Math.min(a, b)}-${Math.max(a, b)}`;
    if (a !== b && teamOf[a] !== teamOf[b] && !seen.has(key)) {
      seen.add(key);
      histPairs.push([a, b]);
    }
  }

  return {
    participants: N,
    total: M,
    scatter,
    roster,
    teams,
    teamOf,
    teamPairs,
    histPairs,
  };
}

function makeLines(pairs: [number, number][], color: number) {
  const positions = new Float32Array(pairs.length * 6);
  const geometry = new THREE.BufferGeometry();
  const attribute = new THREE.BufferAttribute(positions, 3);
  geometry.setAttribute("position", attribute);
  const material = new THREE.LineBasicMaterial({
    color,
    transparent: true,
    opacity: 0,
  });
  return {
    lines: new THREE.LineSegments(geometry, material),
    positions,
    attribute,
    geometry,
    material,
  };
}

/**
 * Fixed, full-viewport WebGL backdrop for the landing page. Scroll progress
 * through `#how` drives four states: scatter → roster → history → teams →
 * confirmed.
 */
export default function TeamScene() {
  const mountRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;

    const reduceMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;

    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    } catch {
      // No WebGL: the page reads fine without the backdrop.
      return;
    }
    renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
    renderer.setClearColor(0x000000, 0);
    Object.assign(renderer.domElement.style, {
      display: "block",
      width: "100%",
      height: "100%",
    });
    mount.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(FOV, 1, 0.1, 100);
    camera.position.set(0, 0, CAMERA_Z);
    scene.add(new THREE.HemisphereLight(0xffffff, 0x888888, 2.2));
    const light = new THREE.DirectionalLight(0xffffff, 1.4);
    light.position.set(3, 5, 6);
    scene.add(light);
    const root = new THREE.Group();
    scene.add(root);

    const cInk = new THREE.Color("#2d2b2b");
    const cAccent = new THREE.Color("#ec3013");
    const cWait = new THREE.Color("#bab6b6");
    const cTmp = new THREE.Color();
    const dummy = new THREE.Object3D();

    const data = buildData();
    const cur = new Float32Array(data.total * 3);
    const boxGeometry = new THREE.BoxGeometry(0.24, 0.24, 0.24);
    const boxMaterial = new THREE.MeshLambertMaterial({ color: 0xffffff });
    const nodes = new THREE.InstancedMesh(boxGeometry, boxMaterial, data.total);
    for (let i = 0; i < data.total; i++) {
      nodes.setColorAt(i, i < data.participants ? cInk : cWait);
    }
    const team = makeLines(data.teamPairs, 0x201e1d);
    const hist = makeLines(data.histPairs, 0xec3013);
    root.add(hist.lines, team.lines, nodes);

    const size = (): [number, number] => {
      const w =
        mount.clientWidth ||
        window.innerWidth ||
        document.documentElement.clientWidth;
      const h =
        mount.clientHeight ||
        window.innerHeight ||
        document.documentElement.clientHeight;
      return [w, h];
    };

    const onResize = () => {
      const [w, h] = size();
      if (!w || !h) return;
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    };

    const mouse = { x: 0, y: 0 };
    const onMove = (e: PointerEvent) => {
      mouse.x = (e.clientX / window.innerWidth) * 2 - 1;
      mouse.y = (e.clientY / window.innerHeight) * 2 - 1;
    };

    const observer =
      typeof ResizeObserver === "undefined"
        ? null
        : new ResizeObserver(onResize);
    observer?.observe(mount);
    window.addEventListener("resize", onResize);
    if (!reduceMotion) window.addEventListener("pointermove", onMove);
    onResize();

    const clock = new THREE.Clock();
    let p = 0;
    let first = true;
    let raf = 0;
    let lastOpacity = "";

    const fill = (
      target: { positions: Float32Array; attribute: THREE.BufferAttribute },
      pairs: [number, number][],
    ) => {
      const arr = target.positions;
      pairs.forEach(([a, b], j) => {
        for (let k = 0; k < 3; k++) {
          arr[j * 6 + k] = cur[a * 3 + k];
          arr[j * 6 + 3 + k] = cur[b * 3 + k];
        }
      });
      target.attribute.needsUpdate = true;
    };

    const loop = () => {
      raf = requestAnimationFrame(loop);
      const [vw, vh] = size();
      if (!vw || !vh) return;

      const canvas = renderer.domElement;
      const ratio = renderer.getPixelRatio();
      if (
        Math.abs(canvas.width - vw * ratio) > 2 ||
        Math.abs(canvas.height - vh * ratio) > 2
      ) {
        onResize();
      }

      const how = document.getElementById("how");
      let target = 0;
      let pastSteps = false;
      if (how) {
        const rect = how.getBoundingClientRect();
        target = Math.max(0, Math.min(4, (vh - rect.top) / vh));
        pastSteps = rect.bottom <= 0;
      }
      if (!Number.isFinite(target)) target = 0;

      // Once #fair fully covers the canvas there is nothing to draw.
      const settled = Math.abs(target - p) < 0.001;
      if (pastSteps && settled && !first) return;

      p = reduceMotion ? target : p + (target - p) * 0.07;
      if (!Number.isFinite(p)) p = 0;

      const t = reduceMotion ? 0 : clock.getElapsedTime();
      const reg = smoothstep(0.25, 1, p);
      const grp = smoothstep(2.1, 2.9, p);
      const histOpacity = smoothstep(1.25, 1.85, p) * (1 - 0.75 * grp);
      const conf = smoothstep(3.1, 3.9, p);
      const amp = reduceMotion
        ? 0
        : DRIFT * 0.35 * (1 - reg * 0.85) * (1 - grp);
      const spin = 1 - Math.max(reg, grp);

      for (let i = 0; i < data.total; i++) {
        const a = data.scatter[i];
        const b = data.roster[i];
        const c = data.teams[i];
        for (let k = 0; k < 3; k++) {
          cur[i * 3 + k] =
            (a[k] + (b[k] - a[k]) * reg) * (1 - grp) + c[k] * grp;
        }
        cur[i * 3] += Math.sin(t * 0.5 + i * 1.7) * amp;
        cur[i * 3 + 1] += Math.cos(t * 0.4 + i * 2.3) * amp;
        cur[i * 3 + 2] += Math.sin(t * 0.3 + i) * amp;
        dummy.position.set(cur[i * 3], cur[i * 3 + 1], cur[i * 3 + 2]);
        dummy.rotation.set((t * 0.4 + i) * spin, (t * 0.3 + i * 0.5) * spin, 0);
        dummy.scale.setScalar(i < data.participants ? 1 : 0.75);
        dummy.updateMatrix();
        nodes.setMatrixAt(i, dummy.matrix);
        if (i < data.participants) {
          // Teams turn red one after another as `conf` sweeps 0 → 1.
          const k = Math.max(0, Math.min(1, conf * TEAMS - data.teamOf[i]));
          cTmp.copy(cInk).lerp(cAccent, k);
          nodes.setColorAt(i, cTmp);
        }
      }
      nodes.instanceMatrix.needsUpdate = true;
      if (nodes.instanceColor) nodes.instanceColor.needsUpdate = true;

      fill(team, data.teamPairs);
      fill(hist, data.histPairs);
      team.material.opacity = grp * 0.85;
      hist.material.opacity = histOpacity * 0.9;

      const wide = vw > WIDE_BREAKPOINT;
      const visibleWidth =
        2 * Math.tan(((FOV / 2) * Math.PI) / 180) * CAMERA_Z * (vw / vh);
      const offX = wide ? visibleWidth * 0.2 : 0;
      const scale = wide
        ? Math.min(1.15, (visibleWidth * 0.55) / 9)
        : Math.min(1, visibleWidth / 9.5);
      root.scale.setScalar(scale);

      if (reduceMotion || first) {
        root.position.x = offX;
      } else {
        root.position.x += (offX - root.position.x) * 0.1;
      }
      if (!reduceMotion) {
        const ry =
          mouse.x * 0.35 * (1 - grp * 0.6) +
          Math.sin(t * 0.2) * 0.25 * (1 - reg);
        const rx = mouse.y * 0.18 * (1 - grp * 0.6);
        root.rotation.y += (ry - root.rotation.y) * 0.05;
        root.rotation.x += (rx - root.rotation.x) * 0.05;
      }

      const opacity = wide ? "1" : "0.3";
      if (opacity !== lastOpacity) {
        mount.style.opacity = opacity;
        lastOpacity = opacity;
      }

      first = false;
      renderer.render(scene, camera);
    };
    loop();

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", onResize);
      window.removeEventListener("pointermove", onMove);
      observer?.disconnect();
      boxGeometry.dispose();
      boxMaterial.dispose();
      nodes.dispose();
      team.geometry.dispose();
      team.material.dispose();
      hist.geometry.dispose();
      hist.material.dispose();
      renderer.dispose();
      renderer.forceContextLoss();
      renderer.domElement.remove();
    };
  }, []);

  return (
    <div
      ref={mountRef}
      aria-hidden="true"
      className="pointer-events-none fixed inset-0 z-0"
    />
  );
}
