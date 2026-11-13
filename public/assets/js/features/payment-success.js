// One scoped timeline per mounted confirmation icon.
window.createPaymentSuccessMotion = function () {
  let mounted = null;
  let context = null;
  let motionPreference = null;
  const dispose = () => {
    context?.revert();
    context = null;
    motionPreference?.removeEventListener('change', render);
    motionPreference = null;
  };
  function render() {
    context?.revert();
    context = null;
    const gsap = window.gsap;
    if (!mounted || !gsap || !window.DrawSVGPlugin || motionPreference?.matches) return;
    gsap.registerPlugin(window.DrawSVGPlugin);
    context = gsap.context(() => {
      const ring = mounted.querySelector('.payment-draw-ring');
      const check = mounted.querySelector('.payment-draw-check');
      const pulse = mounted.querySelector('.payment-pulse-ring');
      const ticks = mounted.querySelectorAll('.payment-radial-tick');
      gsap.set([ring, check], { drawSVG: '0% 0%' });
      gsap.set(pulse, { opacity: 0, attr: { r: 34 } });
      gsap.set(ticks, { opacity: 0, drawSVG: '0% 0%' });
      gsap.timeline()
        .to(ring, { drawSVG: '0% 100%', duration: 0.72, ease: 'power2.inOut' })
        .to(check, { drawSVG: '0% 100%', duration: 0.34, ease: 'power2.out' }, '>-0.03')
        .set(pulse, { opacity: 0.5 }, '>')
        .to(pulse, { attr: { r: 46 }, opacity: 0, duration: 0.7, ease: 'power2.out' }, '<')
        .to(ticks, { opacity: 0.8, drawSVG: '0% 100%', duration: 0.2, ease: 'power2.out' }, '<')
        .to(ticks, { opacity: 0, drawSVG: '100% 100%', duration: 0.4, ease: 'power1.in' }, '>-0.02');
    }, mounted);
  }
  return function setPaymentSuccessIcon(element) {
    if (element === mounted) return;
    dispose();
    mounted = element;
    if (!mounted) return;
    motionPreference = window.matchMedia('(prefers-reduced-motion: reduce)');
    motionPreference.addEventListener('change', render);
    render();
  };
};
