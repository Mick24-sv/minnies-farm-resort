window.createPullRefresh = function (refresh, isBusy) {
  let root, panel, bars, label, start, distance = 0, pulling = false, busy = false, disposed = false;
  let savedOverscroll = '', generation = 0, overscrollLocked = false;
  const mobile = () => window.matchMedia('(max-width: 768px)').matches;
  const reduced = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const resistance = delta => 120 * (1 - Math.exp(-Math.max(0, delta) / 230));
  function paint(height) {
    panel.style.height = height + 'px';
    bars.forEach((bar, index) => { bar.style.transform = 'scaleY(' + Math.max(0, Math.min(1, distance / 76 * 5 - index)) + ')'; });
    label.textContent = distance >= 76 ? 'Release to refresh' : 'Pull to refresh';
  }
  function reset() {
    pulling = false; distance = 0;
    if (panel) { panel.classList.remove('is-pulling'); panel.style.height = '0px'; }
    if (overscrollLocked) document.documentElement.style.overscrollBehaviorY = savedOverscroll;
    overscrollLocked = false;
  }
  function begin(event) {
    if (!mobile() || busy || isBusy() || window.scrollY > 1 || event.touches.length !== 1 || event.target.closest('button,input,textarea,select,a,[role="dialog"]')) return;
    start = { x: event.touches[0].clientX, y: event.touches[0].clientY };
    savedOverscroll = document.documentElement.style.overscrollBehaviorY;
    overscrollLocked = true;
    document.documentElement.style.overscrollBehaviorY = 'none';
  }
  function move(event) {
    if (!start || busy) return;
    if (event.touches.length !== 1) { start = null; reset(); return; }
    const delta = event.touches[0].clientY - start.y;
    if (!pulling && (delta <= 0 || Math.abs(event.touches[0].clientX - start.x) > Math.abs(delta))) { start = null; reset(); return; }
    if (delta < 7 && !pulling) return;
    if (!event.cancelable) { start = null; reset(); return; }
    event.preventDefault();
    pulling = true; panel.classList.add('is-pulling');
    distance = resistance(delta); paint(distance);
  }
  async function release() {
    start = null;
    if (!pulling || distance < 76) { if (!busy) reset(); return; }
    busy = true; pulling = false;
    const requestGeneration = generation;
    panel.classList.remove('is-pulling'); panel.style.height = '60px';
    label.textContent = 'Getting the latest rows…';
    root.setAttribute('aria-busy', 'true');
    try {
      await refresh();
      if (disposed || requestGeneration !== generation) return;
      // Vue has patched the refreshed list before the next paint.
      await new Promise(resolve => requestAnimationFrame(resolve));
      if (disposed || requestGeneration !== generation) return;
      if (!reduced()) root.querySelectorAll('.guest-booking, .service-request-card, .data-table tbody tr').forEach((row, index) => {
        row.animate([{ opacity: 0, transform: 'translateY(-14px)' }, { opacity: 1, transform: 'translateY(2px)', offset: .8 }, { opacity: 1, transform: 'translateY(0)' }], { duration: 420, delay: Math.min(index, 7) * 35, easing: 'cubic-bezier(.2,.8,.2,1)' });
      });
    } catch (error) {
      if (!disposed && requestGeneration === generation) { label.textContent = 'Couldn’t refresh. Please try again.'; }
    } finally {
      if (requestGeneration === generation) {
        busy = false;
        if (!disposed) { root.removeAttribute('aria-busy'); reset(); }
      }
    }
  }
  function cancel() { start = null; if (!busy) reset(); }
  function resize() { if (!mobile()) cancel(); }
  return function setPullRefresh(element) {
    if (element === root) return;
    generation++;
    if (root) {
      root.removeEventListener('touchstart', begin); root.removeEventListener('touchmove', move);
      root.removeEventListener('touchend', release); root.removeEventListener('touchcancel', cancel);
      window.removeEventListener('resize', resize); reset(); start = null; root.removeAttribute('aria-busy'); panel.remove();
    }
    root = element; disposed = !element; busy = false;
    if (!root) return;
    panel = document.createElement('div'); panel.className = 'pull-refresh-panel';
    panel.innerHTML = '<div class="pull-refresh-bars" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i></div><span class="pull-refresh-label" role="status">Pull to refresh</span>';
    root.prepend(panel); bars = [...panel.querySelectorAll('i')]; label = panel.querySelector('span');
    root.addEventListener('touchstart', begin, { passive: true }); root.addEventListener('touchmove', move, { passive: false });
    root.addEventListener('touchend', release); root.addEventListener('touchcancel', cancel);
    window.addEventListener('resize', resize);
  };
};
