window.createOnboardingTour = function ({ prepare = async () => {}, reveal = element => element.scrollIntoView({ block: 'center', behavior: 'instant' }), onStart = () => {}, onFinish = async () => {} } = {}) {
  let dialog, spotlight, card, index = 0, returnFocus, overflow, frame, version = 0, preparing = false;
  const steps = [
    { view: 'rooms', title: 'Plan your visit.', text: 'Choose your check-in and check-out dates, guest count, and budget in pesos. Compare rooms, then open View room to see photos, availability, and the total.', targets: ['#rooms-check-in'] },
    { view: 'rooms', title: 'Reserve your stay.', text: 'Sign in before reserving. A room is held for 3 hours while you pay the 50% deposit through the available GCash or MariBank QR. Submit your reference; the booking is confirmed only after staff verify the funds.', targets: ['.room-details-button:not(:disabled)', '#room-filter-heading'] },
    { view: 'services', title: 'Just visiting for the day?', text: 'Choose a day service or package here. Services require full payment, online or at the resort counter, before use. No room booking is required. A screenshot or payment choice alone does not mark a request paid.', targets: ['.service-request-button:not(:disabled)', '#services-hero-heading'] },
    { view: 'account', title: 'Track your bookings.', text: 'Open My Bookings to see upcoming and past stays, service requests, payment instructions, and balances. Check whether your reservation is pending or confirmed, and use the payment details to submit your reference.', targets: ['.guest-tabs', '#main-navigation [data-section="dashboard"]', '#main-navigation .nav-btn-primary', '.mobile-bottom-tabs button:nth-of-type(4)', '.mobile-menu-btn'] },
    { view: 'account', title: 'Keep your details up to date.', text: 'Inside My Bookings, choose Profile settings to update your name, then Save or Discard. The notification bell shows reservation and payment updates. If you are not signed in yet, start with Account or Sign in.', targets: ['.guest-account-nav button:nth-of-type(2)', '#main-navigation [data-section="dashboard"]', '#main-navigation .nav-btn-primary', '.mobile-bottom-tabs button:nth-of-type(4)', '.mobile-menu-btn'] },
  ];
  function targetFor(step) {
    return step.targets.map(selector => document.querySelector(selector)).find(node => node && node.getClientRects().length && getComputedStyle(node).visibility !== 'hidden');
  }
  function position() {
    if (!dialog?.open || preparing) return;
    const target = targetFor(steps[index]);
    if (!target) return;
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
  async function render() {
    const revision = ++version;
    preparing = true;
    const step = steps[index];
    dialog.querySelector('[data-next]').disabled = true;
    dialog.querySelector('[data-back]').disabled = true;
    await prepare(step);
    if (!dialog?.open || revision !== version) return;
    preparing = false;
    dialog.querySelector('#tour-title').textContent = step.title;
    dialog.querySelector('#tour-description').textContent = step.text;
    dialog.querySelector('.tour-progress').textContent = 'QUICK TOUR · ' + (index + 1) + ' OF ' + steps.length;
    dialog.querySelector('[data-back]').disabled = index === 0;
    dialog.querySelector('[data-next]').disabled = false;
    dialog.querySelector('[data-next]').textContent = index === steps.length - 1 ? 'All set ✓' : 'Next →';
    dialog.querySelectorAll('.tour-dot').forEach((dot, n) => dot.classList.toggle('active', n === index));
    const target = targetFor(step);
    if (target) reveal(target);
    position();
    if (dialog) dialog.querySelector('.tour-announcement').textContent = 'Step ' + (index + 1) + ' of ' + steps.length + '. ' + step.title + ' ' + step.text;
  }
  function cleanup() {
    version++; preparing = false;
    window.removeEventListener('resize', schedule); window.removeEventListener('scroll', schedule);
    cancelAnimationFrame(frame); document.body.style.overflow = overflow;
    dialog?.remove(); dialog = null;
    Promise.resolve(onFinish()).then(() => { if (returnFocus?.isConnected) returnFocus.focus({ preventScroll: true }); });
  }
  return function startTour() {
    if (dialog?.open) return;
    onStart();
    returnFocus = document.activeElement; overflow = document.body.style.overflow;
    index = 0;
    dialog = document.createElement('dialog'); dialog.className = 'onboarding-tour';
    dialog.setAttribute('data-lenis-prevent', '');
    dialog.setAttribute('aria-labelledby', 'tour-title'); dialog.setAttribute('aria-describedby', 'tour-description');
    dialog.innerHTML = '<div class="tour-spotlight" aria-hidden="true"></div><section class="tour-card"><div class="tour-card-top"><span class="tour-progress"></span><button type="button" class="tour-skip" data-skip>Skip tour</button></div><h2 id="tour-title"></h2><p id="tour-description"></p><div class="tour-card-bottom"><div class="tour-dots" aria-hidden="true"></div><div class="tour-actions"><button type="button" class="tour-back" data-back>Back</button><button type="button" class="tour-next" data-next>Next →</button></div></div><span class="tour-announcement" role="status" aria-live="polite"></span></section>';
    document.body.append(dialog); spotlight = dialog.querySelector('.tour-spotlight'); card = dialog.querySelector('.tour-card');
    dialog.querySelector('.tour-dots').innerHTML = steps.map(() => '<i class="tour-dot"></i>').join('');
    dialog.addEventListener('close', cleanup, { once: true });
    dialog.querySelector('[data-skip]').onclick = () => dialog.close();
    dialog.querySelector('[data-back]').onclick = () => { if (index > 0) { index--; render(); } };
    dialog.querySelector('[data-next]').onclick = () => { if (index === steps.length - 1) dialog.close(); else { index++; render(); } };
    dialog.addEventListener('wheel', event => event.preventDefault(), { passive: false });
    dialog.addEventListener('touchmove', event => event.preventDefault(), { passive: false });
    dialog.addEventListener('keydown', event => {
      if (event.key !== 'Tab') return;
      const buttons = [...dialog.querySelectorAll('button:not(:disabled)')];
      const first = buttons[0], last = buttons.at(-1);
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    });
    document.body.style.overflow = 'hidden'; dialog.showModal();
    render().then(() => {
      if (!dialog) return;
      dialog.querySelector('[data-next]').focus();
      frame = requestAnimationFrame(() => { if (dialog) dialog.classList.add('is-moving'); });
    });
    window.addEventListener('resize', schedule); window.addEventListener('scroll', schedule, { passive: true });
  };
};
