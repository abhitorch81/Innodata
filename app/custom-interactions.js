// Drop-in interactions. Loaded after app.js; window.TaskFactoryApp exposes the scene, GSAP, state and helpers.
(function boot() {
  const A = window.TaskFactoryApp;
  if (!A) return setTimeout(boot, 200);
  A.registerInteraction({
    id: 'confetti', icon: '🎉', label: 'Confetti', desc: 'burst of glow at the variant core',
    run({ THREE, gsap, scene, P, shockwave, glow }) {
      const o = P.core.getWorldPosition(new THREE.Vector3());
      for (let i = 0; i < 50; i++) {
        const s = glow(Math.random() * 0xffffff, 1.4); s.position.copy(o); scene.add(s);
        gsap.to(s.position, { x: '+=' + (Math.random() - .5) * 16, y: '+=' + Math.random() * 11, z: '+=' + (Math.random() - .5) * 16,
          duration: 1.7, ease: 'power2.out', onComplete: () => scene.remove(s) });
      }
      shockwave(o, 0xffffff, 6);
    }
  });
})();
