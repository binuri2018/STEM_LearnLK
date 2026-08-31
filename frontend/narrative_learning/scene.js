import * as THREE from "three";

const canvas = document.getElementById("fx-canvas");
if (!canvas) {
  /* page without canvas */
} else {
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 100);
  camera.position.z = 8;

  const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setClearColor(0xf5f7f9, 0);

  const colors = [0x6366f1, 0x00c896, 0xf59e0b, 0xa78bfa, 0x34d399];
  const orbs = colors.map((hex, i) => {
    const geo = new THREE.SphereGeometry(1.1 + (i % 3) * 0.25, 32, 32);
    const mat = new THREE.MeshBasicMaterial({
      color: hex,
      transparent: true,
      opacity: 0.22,
    });
    const mesh = new THREE.Mesh(geo, mat);
    mesh.userData = {
      ax: 0.18 + i * 0.07,
      ay: 0.12 + i * 0.05,
      phase: i * 1.1,
    };
    scene.add(mesh);
    return mesh;
  });

  function resize() {
    const parent = canvas.parentElement;
    const w = parent.clientWidth;
    const h = parent.clientHeight;
    renderer.setSize(w, h, false);
    camera.aspect = w / Math.max(h, 1);
    camera.updateProjectionMatrix();
  }

  window.addEventListener("resize", resize);
  resize();

  const clock = new THREE.Clock();
  function tick() {
    const t = clock.getElapsedTime();
    orbs.forEach((mesh, i) => {
      const { ax, ay, phase } = mesh.userData;
      mesh.position.x = Math.sin(t * ax + phase) * 3.2;
      mesh.position.y = Math.cos(t * ay + phase) * 2.1;
      mesh.position.z = Math.sin(t * 0.2 + i) * 1.4;
      mesh.scale.setScalar(1 + Math.sin(t * 0.6 + i) * 0.12);
    });
    renderer.render(scene, camera);
    requestAnimationFrame(tick);
  }
  tick();
}
