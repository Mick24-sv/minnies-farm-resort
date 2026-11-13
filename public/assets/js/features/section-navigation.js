window.createSectionNavigation = function (getPage, setSection) {
  const sections = ['home', 'rooms', 'services', 'about'];
  let nav, lenis, mutation, resize, frame, pillAnimation, lastGeometry;
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  function sync() {
    if (!nav) return;
    if (sections.includes(getPage())) {
      let current = 'home';
      for (const name of sections) {
        const section = document.getElementById('section-' + name);
        if (section && section.getBoundingClientRect().top <= nav.offsetHeight + 36) current = name;
      }
      setSection(current);
    }
    paint();
  }
  function paint() {
    if (!nav) return;
    const links = nav.querySelector('#main-navigation');
    const pill = nav.querySelector('.sticky-nav-pill');
    const button = links.querySelector('[data-section="' + getPage() + '"]');
    if (!button || window.innerWidth <= 1100) { pill.style.opacity = '0'; lastGeometry = null; return; }
    const parent = links.getBoundingClientRect(), target = button.getBoundingClientRect();
    const geometry = [target.left-parent.left,target.top-parent.top,target.width,target.height].join(',');
    if (geometry === lastGeometry) return;
    lastGeometry = geometry;
    const previous = pill.getBoundingClientRect();
    const visible = pill.style.opacity === '1';
    pillAnimation?.cancel();
    const destination = { left: target.left - parent.left + 'px', top: target.top - parent.top + 'px', width: target.width + 'px', height: target.height + 'px' };
    Object.assign(pill.style, destination, { opacity: '1' });
    if (visible && !reduced.matches && pill.animate) pillAnimation = pill.animate([
      { left: previous.left - parent.left + 'px', top: previous.top - parent.top + 'px', width: previous.width + 'px', height: previous.height + 'px' }, destination,
    ], { duration: 320, easing: 'cubic-bezier(.22,.75,.25,1)' });
  }
  function schedule() { cancelAnimationFrame(frame); frame = requestAnimationFrame(sync); }
  function layout() { lenis?.resize(); schedule(); }
  function preferenceChanged() {
    if (reduced.matches) lenis?.scrollTo(window.scrollY, { immediate: true });
    layout();
  }
  return {
    jump(target) {
      const top = typeof target === 'number' ? target : Math.max(0, window.scrollY + target.getBoundingClientRect().top - window.innerHeight * .24);
      lenis?.resize();
      if (lenis) lenis.scrollTo(top, { immediate: true });
      else window.scrollTo({ top, behavior: 'instant' });
    },
    mount(element) {
      if (element === nav) return;
      mutation?.disconnect(); resize?.disconnect(); lenis?.destroy(); pillAnimation?.cancel(); cancelAnimationFrame(frame);
      window.removeEventListener('scroll', schedule); window.removeEventListener('resize', layout); reduced.removeEventListener('change', preferenceChanged);
      nav = element; lastGeometry = null;
      if (!nav) return;
      lenis = window.Lenis ? new window.Lenis({ autoRaf: true, smoothWheel: true, syncTouch: false,
        virtualScroll: () => sections.includes(getPage()) && !reduced.matches && document.body.style.overflow !== 'hidden',
        prevent: node => !!node.closest?.('.modal-overlay,.notification-inbox'),
      }) : null;
      mutation = new MutationObserver(() => requestAnimationFrame(paint));
      mutation.observe(nav, { subtree: true, childList: true, attributes: true, attributeFilter: ['class', 'data-section'] });
      resize = new ResizeObserver(layout); resize.observe(document.getElementById('app'));
      window.addEventListener('scroll', schedule, { passive: true }); window.addEventListener('resize', layout); reduced.addEventListener('change', preferenceChanged);
      schedule();
    },
    go(name) {
      const target = document.getElementById('section-' + name);
      const offset = -(nav?.getBoundingClientRect().bottom || 64);
      lenis?.resize();
      if (target && lenis) lenis.scrollTo(target, { offset, duration: 1.1, easing: t => 1 - Math.pow(1 - t, 4), immediate: reduced.matches });
      else if (target) window.scrollTo({ top: Math.max(0, window.scrollY + target.getBoundingClientRect().top + offset), behavior: reduced.matches ? 'instant' : 'smooth' });
      else if (lenis) lenis.scrollTo(0, { immediate: true });
      else window.scrollTo({ top: 0, behavior: 'instant' });
      requestAnimationFrame(paint);
    },
  };
};
