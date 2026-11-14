window.createLiquidTabs = function () {
  let root, indicator, observer, resizeObserver, animation, lastTab, frame;
  const media = window.matchMedia('(prefers-reduced-motion: reduce)');
  let scrollAnchor = 0;
  function showTabs() {
    root?.classList.remove('is-scroll-hidden');
    if (root) root.inert = false;
    scrollAnchor = Math.max(0, window.scrollY);
  }
  function scroll() {
    if (!root || window.innerWidth > 768 || document.body.style.overflow === 'hidden') return;
    const y = Math.max(0, Math.min(window.scrollY, document.documentElement.scrollHeight - window.innerHeight));
    const delta = y - scrollAnchor;
    if (Math.abs(delta) < 12) return;
    const hidden = delta < 0 && !root.contains(document.activeElement);
    root.classList.toggle('is-scroll-hidden', hidden);
    root.inert = hidden;
    scrollAnchor = y;
  }
  function position(animate = true) {
    if (!root || !root.getClientRects().length) return;
    const tab = root.querySelector('[aria-current="page"]');
    if (!tab) { indicator.style.opacity = '0'; lastTab = null; return; }
    const parent = root.getBoundingClientRect();
    const target = tab.getBoundingClientRect();
    const current = indicator.getBoundingClientRect();
    const from = { left: current.left - parent.left, width: current.width };
    const to = { left: target.left - parent.left + 4, width: target.width - 8 };
    animation?.cancel();
    indicator.style.left = to.left + 'px';
    indicator.style.width = to.width + 'px';
    indicator.style.opacity = '1';
    if (animate && lastTab && lastTab !== tab && !media.matches && indicator.animate) {
      const stretchLeft = Math.min(from.left, to.left);
      const stretchRight = Math.max(from.left + from.width, to.left + to.width);
      const direction = to.left > from.left ? 1 : -1;
      animation = indicator.animate([
        { left: from.left + 'px', width: from.width + 'px', transform: 'scaleY(1)', offset: 0 },
        { left: stretchLeft + 'px', width: stretchRight - stretchLeft + 'px', transform: 'scaleY(.72)', offset: .42 },
        { left: to.left + direction * 3 + 'px', width: to.width + 'px', transform: 'scaleY(1.06)', offset: .83 },
        { left: to.left + 'px', width: to.width + 'px', transform: 'scaleY(1)', offset: 1 },
      ], { duration: 560, easing: 'cubic-bezier(.22,.7,.25,1)' });
    }
    lastTab = tab;
  }
  function sync() { showTabs(); cancelAnimationFrame(frame); frame = requestAnimationFrame(() => position(true)); }
  function resize() { showTabs(); cancelAnimationFrame(frame); frame = requestAnimationFrame(() => position(false)); }
  return function setLiquidTabs(element) {
    if (element === root) return;
    observer?.disconnect(); resizeObserver?.disconnect(); animation?.cancel(); cancelAnimationFrame(frame);
    window.removeEventListener('resize', resize); media.removeEventListener('change', resize);
    window.removeEventListener('scroll', scroll);
    root = element; lastTab = null;
    if (!root) return;
    indicator = root.querySelector('.liquid-tab-indicator');
    observer = new MutationObserver(sync);
    observer.observe(root, { subtree: true, attributes: true, attributeFilter: ['aria-current'] });
    if ('ResizeObserver' in window) { resizeObserver = new ResizeObserver(resize); resizeObserver.observe(root); }
    window.addEventListener('resize', resize); media.addEventListener('change', resize);
    window.addEventListener('scroll', scroll, { passive: true });
    resize();
  };
};
