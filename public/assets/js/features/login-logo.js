window.createLoginLogo = function () {
  let element = null, context = null, complete = null;
  const preference = window.matchMedia('(prefers-reduced-motion: reduce)');
  function stop() { context?.revert(); context = null; complete?.(); complete = null; }
  function motionChanged() { if (preference.matches) stop(); }
  return {
    mount(node) {
      if (node === element) return;
      stop(); preference.removeEventListener('change', motionChanged); element = node;
      if (node) preference.addEventListener('change', motionChanged);
    },
    play() {
      stop();
      if (!element || !window.gsap || !window.DrawSVGPlugin || preference.matches) return Promise.resolve();
      window.gsap.registerPlugin(window.DrawSVGPlugin);
      return new Promise(resolve => {
        complete = resolve;
        context = window.gsap.context(() => {
          const outline = element.querySelectorAll('.login-logo-outline');
          const flood = element.querySelector('.login-logo-flood');
          window.gsap.set(outline, { drawSVG: '0% 0%', opacity: 1 });
          window.gsap.set(flood, { clipPath: 'inset(100% 0% 0% 0%)' });
          window.gsap.timeline({ onComplete: () => { complete = null; resolve(); } })
            .to(outline, { drawSVG: '0% 100%', duration: 1.2, ease: 'power1.inOut' })
            .to(flood, { clipPath: 'inset(0% 0% 0% 0%)', duration: 0.48, ease: 'power2.inOut' })
            .to(outline, { drawSVG: '100% 100%', duration: 0.42, ease: 'power2.in' });
        }, element);
      });
    },
  };
};
