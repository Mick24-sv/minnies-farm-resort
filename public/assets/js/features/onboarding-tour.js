window.createOnboardingTour = function () {
  let dialog, spotlight, card, index = 0, returnFocus, overflow, frame;
  const steps = [
    { title: 'Welcome to the farm.', text: 'Your next getaway starts here. The resort logo always brings you back to the top.', targets: ['.nav-brand'] },
    { title: 'Find your kind of stay.', text: 'Browse rooms, compare details, and choose the space that feels right for you.', targets: ['#main-navigation [data-section="rooms"]', '.mobile-bottom-tabs button:nth-of-type(2)'] },
    { title: 'Make a day of it.', text: 'Explore day visits and resort services for a little escape, even without an overnight stay.', targets: ['#main-navigation [data-section="services"]', '.mobile-bottom-tabs button:nth-of-type(3)'] },
    { title: 'Everything in one place.', text: 'Sign in to manage your bookings. Staff can open their dashboard, and signed-in guests can update their profile.', targets: ['#main-navigation [data-section="profile"]', '#main-navigation .nav-btn-primary', '.mobile-bottom-tabs button:nth-of-type(4)'] },
  ];
  function targetFor(step) {
    return step.targets.map(selector => document.querySelector(selector)).find(node => node && node.getClientRects().length && getComputedStyle(node).visibility !== 'hidden');
  }
  function position() {
    if (!dialog?.open) return;
    const target = targetFor(steps[index]);
    if (!target) { dialog.close(); return; }
    const bounds = target.getBoundingClientRect(), width = window.innerWidth, height = window.innerHeight;
    const x = Math.max(6, bounds.left - 8), y = Math.max(6, bounds.top - 8);
    const w = Math.min(width - x - 6, bounds.width + 16), h = Math.min(height - y - 6, bounds.height + 16);
    Object.assign(spotlight.style, { left: x + 'px', top: y + 'px', width: w + 'px', height: h + 'px' });
    const cardWidth = Math.min(324, width - 32), cardHeight = card.offsetHeight;
    const left = Math.max(16, Math.min(x + w / 2 - cardWidth / 2, width - cardWidth - 16));
    const below = y + h + 18;
    const top = below + cardHeight <= height - 16 ? below : Math.max(16, y - cardHeight - 18);
    Object.assign(card.style, { left: left + 'px', top: top + 'px', width: cardWidth + 'px' });
    card.dataset.placement = top < y ? 'above' : 'below';
  }
  function schedule() { cancelAnimationFrame(frame); frame = requestAnimationFrame(position); }
  function render() {
    const step = steps[index];
    dialog.querySelector('#tour-title').textContent = step.title;
    dialog.querySelector('#tour-description').textContent = step.text;
    dialog.querySelector('.tour-progress').textContent = 'QUICK TOUR · ' + (index + 1) + ' OF ' + steps.length;
    dialog.querySelector('[data-back]').disabled = index === 0;
    dialog.querySelector('[data-next]').textContent = index === steps.length - 1 ? 'All set ✓' : 'Next →';
    dialog.querySelectorAll('.tour-dot').forEach((dot, n) => dot.classList.toggle('active', n === index));
    position();
  }
  function cleanup() {
    window.removeEventListener('resize', schedule); window.removeEventListener('scroll', schedule);
    cancelAnimationFrame(frame); document.body.style.overflow = overflow;
    dialog?.remove(); dialog = null;
    if (returnFocus?.isConnected) returnFocus.focus({ preventScroll: true });
  }
  return function startTour() {
    if (dialog?.open) return;
    returnFocus = document.activeElement; overflow = document.body.style.overflow;
    index = 0;
    dialog = document.createElement('dialog'); dialog.className = 'onboarding-tour';
    dialog.setAttribute('data-lenis-prevent', '');
    dialog.setAttribute('aria-labelledby', 'tour-title'); dialog.setAttribute('aria-describedby', 'tour-description');
    dialog.innerHTML = '<div class="tour-spotlight" aria-hidden="true"></div><section class="tour-card"><div class="tour-card-top"><span class="tour-progress"></span><button type="button" class="tour-skip" data-skip>Skip tour</button></div><h2 id="tour-title"></h2><p id="tour-description"></p><div class="tour-card-bottom"><div class="tour-dots" aria-hidden="true"><i class="tour-dot"></i><i class="tour-dot"></i><i class="tour-dot"></i><i class="tour-dot"></i></div><div class="tour-actions"><button type="button" class="tour-back" data-back>Back</button><button type="button" class="tour-next" data-next>Next →</button></div></div><span class="tour-announcement" role="status" aria-live="polite"></span></section>';
    document.body.append(dialog); spotlight = dialog.querySelector('.tour-spotlight'); card = dialog.querySelector('.tour-card');
    dialog.addEventListener('close', cleanup, { once: true });
    dialog.querySelector('[data-skip]').onclick = () => dialog.close();
    dialog.querySelector('[data-back]').onclick = () => { if (index > 0) { index--; render(); announce(); } };
    dialog.querySelector('[data-next]').onclick = () => { if (index === steps.length - 1) dialog.close(); else { index++; render(); announce(); } };
    function announce() { dialog.querySelector('.tour-announcement').textContent = 'Step ' + (index + 1) + ' of ' + steps.length + '. ' + steps[index].title + ' ' + steps[index].text; }
    dialog.addEventListener('wheel', event => event.preventDefault(), { passive: false });
    dialog.addEventListener('touchmove', event => event.preventDefault(), { passive: false });
    dialog.addEventListener('keydown', event => {
      if (event.key !== 'Tab') return;
      const buttons = [...dialog.querySelectorAll('button:not(:disabled)')];
      const first = buttons[0], last = buttons.at(-1);
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    });
    document.body.style.overflow = 'hidden'; dialog.showModal(); render();
    dialog.querySelector('[data-next]').focus();
    frame = requestAnimationFrame(() => { if (dialog) dialog.classList.add('is-moving'); });
    window.addEventListener('resize', schedule); window.addEventListener('scroll', schedule, { passive: true });
  };
};
