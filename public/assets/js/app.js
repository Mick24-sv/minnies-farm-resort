const { createApp, ref, computed, onMounted, watch, nextTick } = Vue;

const API_URL = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? 'http://127.0.0.1:5000/api'
  : '/api';

const __app = createApp({
  setup() {
    const page = ref('home');
    const authTab = ref('login');
    const dashTab = ref('upcoming');

    // Safe token retrieval
    let savedToken = '';
    try {
      savedToken = localStorage.getItem('token') || '';
    } catch (e) {
    }
    const token = ref(savedToken);
    const currentUser = ref(null);

    const notifications = ref([]), notificationUnread = ref(0), notificationsOpen = ref(false);
    const notificationsBusy = ref(false), notificationsError = ref(''), notificationsOlder = ref(false);
    let notificationPoll = null, notificationRequest = 0;
    async function fetchNotifications(older = false) {
      if (!currentUser.value || !token.value || notificationsBusy.value) return;
      const sequence = ++notificationRequest, session = token.value;
      notificationsBusy.value = true; notificationsError.value = '';
      try {
        const before = older ? notifications.value.at(-1)?.id : null;
        const response = await fetch(`${API_URL}/notifications${before ? '?before=' + before : ''}`, {
          headers: { Authorization: `Bearer ${session}` }, cache: 'no-store',
        });
        const data = await response.json();
        if (sequence !== notificationRequest || session !== token.value) return;
        if (!response.ok) throw new Error('Updates are unavailable. Please try again.');
        const items = data.notifications || [];
        const changed = !older && items[0]?.id !== notifications.value[0]?.id;
        const previous = notifications.value;
        notifications.value = older ? [...previous, ...items.filter(item => !previous.some(existing => existing.id === item.id))]
          : previous.length > 50 ? [...items, ...previous.filter(item => item.id < items.at(-1)?.id)] : items;
        notificationUnread.value = Number(data.unread_count || 0);
        if (older || previous.length <= 50) notificationsOlder.value = items.length === 50;
        if (changed && page.value === 'dashboard' && !showPaymentDialog.value) {
          if (currentUser.value.role === 'staff') fetchAllBookings(); else fetchUserBookings();
          fetchServiceAvails();
        }
      } catch (error) {
        if (sequence === notificationRequest && session === token.value) notificationsError.value = error.message;
      } finally { if (sequence === notificationRequest) notificationsBusy.value = false; }
    }
    async function toggleNotifications() {
      notificationsOpen.value = !notificationsOpen.value;
      if (notificationsOpen.value) {
        await nextTick(); document.getElementById('notification-heading')?.focus();
        await fetchNotifications();
      }
    }
    function closeNotifications() {
      notificationsOpen.value = false;
      const mobile = window.matchMedia?.('(max-width: 1100px)')?.matches;
      document.getElementById(mobile ? 'notification-bell-mobile' : 'notification-bell')?.focus();
    }
    async function markNotificationsRead(item = null) {
      const session = token.value;
      try {
        const response = await fetch(`${API_URL}/notifications/read`, { method: 'POST',
          headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${session}` },
          body: JSON.stringify(item ? { id: item.id } : {}),
        });
        if (session !== token.value) return;
        if (!response.ok) throw new Error('Could not mark notifications as read. Please retry.');
        const now = new Date().toISOString();
        if (item) {
          if (!item.read_at) { item.read_at = now; notificationUnread.value = Math.max(0, notificationUnread.value - 1); }
        } else { notifications.value.forEach(entry => { entry.read_at = entry.read_at || now; }); notificationUnread.value = 0; }
      } catch (error) { if (session === token.value) notificationsError.value = error.message; }
    }
    async function openNotification(item) {
      if (paymentBusy.value) return;
      const opened = await openPaymentDialog({ id: item.entity_id }, item.entity_kind);
      if (opened) {
        notificationsOpen.value = false;
        navigate('dashboard');
        await markNotificationsRead(item);
      }
    }
    function notificationDate(value) {
      return new Date(value).toLocaleString('en-PH', { timeZone: 'Asia/Manila', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
    }
    watch(() => currentUser.value?.id, () => {
      ++notificationRequest;
      if (notificationPoll) clearInterval(notificationPoll);
      notificationPoll = null;
      notifications.value = []; notificationUnread.value = 0; notificationsOpen.value = false;
      notificationsBusy.value = false; notificationsError.value = ''; notificationsOlder.value = false;
      if (currentUser.value) {
        fetchNotifications();
        notificationPoll = setInterval(() => {
          if (!document.hidden) fetchNotifications();
        }, 30000);
      }
    });

    const authMsg = ref('');
    const authMsgType = ref('');
    const authMsgKey = ref(0);
    const showRoomModal = ref(false);
    const showCancelBookingModal = ref(false);
    const pendingCancelBooking = ref(null);
    const bookingCancellationBusy = ref(false);
    const bookingCancellationError = ref('');
    const roomImageUploads = ref(0);
    const roomEditorBusy = computed(() => loading.value || roomImageUploads.value > 0);
    let roomDialogTrigger = null;
    let roomDialogBodyOverflow = '';
    watch(showRoomModal, async isOpen => {
      if (isOpen) {
        roomDialogTrigger = document.activeElement;
        roomDialogBodyOverflow = document.body.style.overflow;
        document.body.style.overflow = 'hidden';
        await nextTick();
        document.getElementById('editor-room-number')?.focus();
      } else {
        document.body.style.overflow = roomDialogBodyOverflow;
        await nextTick();
        if (roomDialogTrigger?.isConnected) roomDialogTrigger.focus();
      }
    });
    function closeRoomDialog() { if (!roomEditorBusy.value) showRoomModal.value = false; }
    function handleRoomDialogKeydown(event) {
      if (event.key === 'Escape') {
        event.preventDefault();
        event.stopPropagation();
        closeRoomDialog();
      } else if (event.key === 'Tab') {
        const controls = [...event.currentTarget.querySelectorAll('button:not(:disabled), input:not(:disabled):not([tabindex="-1"]), select:not(:disabled), textarea:not(:disabled)')]
          .filter(control => control.getClientRects().length);
        if (!controls.length) { event.preventDefault(); return; }
        const first = controls[0], last = controls[controls.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      }
    }
    const editingRoom = ref(null);
    const loading = ref(false);
    const serviceAvails = ref([]);
    const showDeleteModal = ref(false);
    const pendingDeleteId = ref(null);
    const showDeleteBookingModal = ref(false);
    const pendingDeleteBookingId = ref(null);
    const showDeleteRoomModal = ref(false);
    const pendingDeleteRoom = ref(null);
    const showServiceAdminModal = ref(false);
    const editingService = ref(null);
    const showDeleteServiceModal = ref(false);
    const pendingDeleteService = ref(null);
    const serviceForm = ref({ name: '', category: 'day_service', price: 0, stock_quantity: -1, description: '', is_active: true, image_url: '' });
    const serviceImageReading = ref(false);
    const serviceImageError = ref('');
    const serviceEditorBusy = computed(() => loading.value || serviceImageReading.value);
    let serviceDialogTrigger = null;
    let serviceDialogBodyOverflow = '';
    watch(showServiceAdminModal, async isOpen => {
      if (isOpen) {
        serviceDialogTrigger = document.activeElement;
        serviceDialogBodyOverflow = document.body.style.overflow;
        document.body.style.overflow = 'hidden';
        await nextTick();
        document.getElementById('service-editor-name')?.focus();
      } else {
        document.body.style.overflow = serviceDialogBodyOverflow;
        await nextTick();
        if (serviceDialogTrigger?.isConnected) serviceDialogTrigger.focus();
      }
    });
    function closeServiceDialog() { if (!serviceEditorBusy.value) showServiceAdminModal.value = false; }
    function handleServiceDialogKeydown(event) {
      if (event.key === 'Escape') {
        event.preventDefault(); event.stopPropagation(); closeServiceDialog();
      } else if (event.key === 'Tab') handleRoomDialogKeydown(event);
    }
    function chooseServicePhoto() { document.getElementById('service-photo-input')?.click(); }
    function removeServicePhoto() {
      serviceForm.value.image_url = '';
      serviceImageError.value = '';
      const input = document.getElementById('service-photo-input');
      if (input) input.value = '';
    }
    function handleServicePhoto(event) {
      if (serviceEditorBusy.value) return;
      const file = event.target.files?.[0];
      if (!file) return;
      serviceImageError.value = '';
      if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type) || file.size > 2 * 1024 * 1024) {
        serviceImageError.value = 'Choose a JPG, PNG or WebP image smaller than 2 MB.';
        event.target.value = ''; return;
      }
      serviceImageReading.value = true;
      const reader = new FileReader();
      reader.onload = () => { serviceForm.value.image_url = reader.result; serviceImageReading.value = false; };
      reader.onerror = () => { serviceImageError.value = 'Could not read this photo. Please try again.'; serviceImageReading.value = false; event.target.value = ''; };
      reader.readAsDataURL(file);
    }
    const staffTab = ref('bookings');
    const staffBookingSearch = ref('');
    const staffBookingStatus = ref('');
    const staffRefreshing = ref(false);
    const guestRefreshing = ref(false);
    async function refreshGuestDashboard() {
      if (guestRefreshing.value) return;
      guestRefreshing.value = true;
      try {
        await fetchRooms();
        await Promise.all([fetchUserBookings(), fetchServiceAvails()]);
      } finally {
        guestRefreshing.value = false;
      }
    }
    function formatGuestDate(value) {
      if (!value) return '—';
      const date = new Date(String(value).slice(0, 10) + 'T12:00:00');
      return Number.isNaN(date.getTime()) ? '—' : date.toLocaleDateString('en-PH', { month: 'short', day: 'numeric', year: 'numeric' });
    }
    const filteredStaffBookings = computed(() => {
      const query = staffBookingSearch.value.trim().toLowerCase();
      return allBookings.value.filter(b =>
        (!staffBookingStatus.value || b.status === staffBookingStatus.value) &&
        (!query || [b.guestName, b.room, b.id].some(value => String(value ?? '').toLowerCase().includes(query)))
      );
    });

    async function refreshStaffDashboard() {
      if (staffRefreshing.value) return;
      staffRefreshing.value = true;
      try {
        await fetchRooms();
        await Promise.all([fetchAllBookings(), fetchServices(), fetchServiceAvails()]);
      } finally {
        staffRefreshing.value = false;
      }
    }
    const toasts = ref([]);

    // Mobile menu state
    const mobileMenuOpen = ref(false);

    const today = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Manila', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());

    const loginForm = ref({ email: '', password: '' });
    const regForm = ref({ name: '', email: '', password: '', confirm: '', role: 'guest' });
    const showLoginPw = ref(false);
    const showRegPw = ref(false);
    const showRegConfirmPw = ref(false);

    const rooms = ref([]);
    const roomsLoading = ref(false);
    const roomLoadError = ref(false);
    const filters = ref({ checkIn: '', checkOut: '', type: '', maxPrice: '', capacity: '' });
    const selectedRoom = ref(null);
    const activeRoomPhoto = ref(0);
    const roomPhotos = computed(() => {
      const room = selectedRoom.value;
      if (!room) return [];
      return [...new Set([room.image_url, room.image_url_2, room.image_url_3, room.image_url_4, room.image_url_5]
        .filter(photo => typeof photo === 'string' && photo.trim()).map(photo => photo.trim()))];
    });
    function changeRoomPhoto(direction) {
      if (!roomPhotos.value.length) return;
      activeRoomPhoto.value = (activeRoomPhoto.value + direction + roomPhotos.value.length) % roomPhotos.value.length;
    }
    let roomPhotoGesture = null;
    function startRoomPhotoGesture(event) {
      if (roomPhotos.value.length < 2 || !event.isPrimary || event.button !== 0 || event.target.closest('button')) return;
      roomPhotoGesture = { id: event.pointerId, x: event.clientX, y: event.clientY };
      event.currentTarget.setPointerCapture(event.pointerId);
    }
    function endRoomPhotoGesture(event) {
      if (!roomPhotoGesture || event.pointerId !== roomPhotoGesture.id) return;
      const dx = event.clientX - roomPhotoGesture.x;
      const dy = event.clientY - roomPhotoGesture.y;
      roomPhotoGesture = null;
      if (Math.abs(dx) >= 50 && Math.abs(dx) > Math.abs(dy) * 1.3) changeRoomPhoto(dx < 0 ? 1 : -1);
    }
    function cancelRoomPhotoGesture() { roomPhotoGesture = null; }
    const bookingForm = ref({ checkIn: '', checkOut: '', guests: 1 });
    const roomForm = ref({
      room_number: '', name: '', type: 'Standard', capacity: 2, price_per_night: '',
      description: '', sqm: '', amenities: '', image_url: '', image_url_2: '', image_url_3: '',
      image_url_4: '', image_url_5: '', room_status: 'available'
    });
    const lastBooking = ref({});
    const paymentOptions = ref({ configured: false, accounts: [], deposit_percent: 50, hold_hours: 3 });
    const paymentOptionsLoading = ref(false);
    const paymentOptionsError = ref(false);
    const paymentBooking = ref(null);
    const paymentKind = ref('booking');
    const lastCounterService = ref(null);
    const editingServicePaymentMethod = ref(false);
    const savedServiceCounterChoice = computed(() => paymentKind.value === 'service' && currentUser.value?.role !== 'staff' && paymentBooking.value?.requested_payment_method === 'cash' && paymentBooking.value?.status === 'pending' && paymentBooking.value?.payment_status === 'unpaid');
    const customerPaymentFormVisible = computed(() => currentUser.value?.role !== 'staff' && paymentBooking.value?.status === 'pending' && paymentBooking.value?.payment_review_status !== 'pending_review' && (!savedServiceCounterChoice.value || editingServicePaymentMethod.value));
    const walkInKind = ref('booking');
    const paymentHistory = ref([]);
    const showPaymentDialog = ref(false);
    const showWalkInDialog = ref(false);
    const paymentBusy = ref(false);
    const paymentError = ref('');
    const paymentPhotoReading = ref(false);
    const paymentForm = ref({ method: 'gcash', reference: '', proof: '', amount: '', verified: false, note: '' });
    const walkInForm = ref({ room_id: '', guest_name: '', guest_phone: '', check_in_date: '', check_out_date: '', num_guests: 1, payment_method: 'cash', payment_reference: '', payment_received: false });
    const walkInRoom = computed(() => (walkInKind.value === 'service' ? services.value : rooms.value).find(room => String(room.id) === String(walkInForm.value.room_id)));
    const walkInTotal = computed(() => {
      if (walkInKind.value === 'service') return walkInRoom.value ? Math.round(Number(walkInRoom.value.price) * Number(walkInForm.value.num_guests) * 100) / 100 : 0;
      const nights = (new Date(walkInForm.value.check_out_date) - new Date(walkInForm.value.check_in_date)) / 86400000;
      return nights > 0 && walkInRoom.value ? Math.round(Number(walkInRoom.value.price_per_night) * nights * 110) / 100 : 0;
    });
    function bookingMoney(value) { return Number(value || 0).toLocaleString('en-PH', { minimumFractionDigits: 2, maximumFractionDigits: 2 }); }
    function paymentStatusLabel(booking) { return ({ paid: 'Paid', partially_paid: 'Deposit paid', unpaid: 'Unpaid' })[booking.payment_status] || 'Unpaid'; }
    function paymentProviderLogo(account) {
      if (account.method === 'gcash') return 'assets/images/gcash-logo.svg';
      if (account.method === 'bank_transfer' && /maribank/i.test(String(account.label || '').replace(/\s+/g, ''))) return 'assets/images/maribank-logo.png';
      return '';
    }
    function paymentDeadline(value) {
      return value ? new Date(value).toLocaleString('en-PH', { timeZone: 'Asia/Manila', dateStyle: 'medium', timeStyle: 'short' }) + ' (Philippine time)' : '';
    }
    function bookingReceipt(booking) {
      return { ...booking, ref: booking.reference_code || 'MFR-' + booking.id, room: booking.room_name || booking.room || rooms.value.find(room => String(room.id) === String(booking.room_id))?.name || (String(selectedRoom.value?.id) === String(booking.room_id) ? selectedRoom.value.name : 'Room ' + booking.room_id),
        checkIn: booking.check_in || booking.checkIn, checkOut: booking.check_out || booking.checkOut, guests: booking.guest_count || booking.guests, total: booking.total_price ?? booking.total };
    }
    function serviceReceipt(record, fallbackName = '') {
      const knownName = services.value.find(service => String(service.id) === String(record.service_id))?.name;
      return { ...record, ref: record.reference_code || 'MFS-' + record.id, room: record.service_name && record.service_name !== 'Service' ? record.service_name : knownName || fallbackName || 'Service', total: record.total_price };
    }
    function changeServicePaymentMethod() {
      editingServicePaymentMethod.value = true;
      paymentForm.value.method = paymentOptions.value.accounts[0]?.method || 'cash';
    }
    async function viewServiceRequests() {
      navigate('dashboard');
      await nextTick();
      document.getElementById('guest-services-heading')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
    async function fetchPaymentOptions() {
      if (paymentOptionsLoading.value) return;
      paymentOptionsLoading.value = true;
      paymentOptionsError.value = false;
      try {
        const res = await fetch(`${API_URL}/payment-options`, { cache: 'no-store' });
        if (!res.ok) throw new Error('Payment settings unavailable');
        paymentOptions.value = await res.json();
      } catch { paymentOptionsError.value = true; }
      finally { paymentOptionsLoading.value = false; }
    }
    async function paymentApi(path, payload) {
      const res = await fetch(`${API_URL}${path}`, { method: payload ? 'POST' : 'GET', headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token.value}` }, ...(payload ? { body: JSON.stringify(payload) } : {}) });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Could not complete this request.');
      if (payload) fetchNotifications();
      return data;
    }
    const paymentRequestKeys = new Map();
    function requestKey(kind, details) {
      const signature = kind + JSON.stringify(details);
      if (!paymentRequestKeys.has(signature)) paymentRequestKeys.set(signature, globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`);
      return paymentRequestKeys.get(signature);
    }
    function closePaymentDialogs() {
      if (paymentBusy.value || paymentPhotoReading.value) return;
      showPaymentDialog.value = false; showWalkInDialog.value = false; paymentError.value = '';
    }
    function paymentDialogKeydown(event) {
      if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); closePaymentDialogs(); }
      else if (event.key === 'Tab') handleRoomDialogKeydown(event);
    }
    let paymentDialogTrigger = null, paymentBodyOverflow = '';
    watch([showPaymentDialog, showWalkInDialog], async flags => {
      if (flags.some(Boolean)) {
        paymentDialogTrigger = document.activeElement; paymentBodyOverflow = document.body.style.overflow; document.body.style.overflow = 'hidden';
        await nextTick(); document.querySelector('.payment-dialog [data-payment-focus]')?.focus();
      } else {
        document.body.style.overflow = paymentBodyOverflow; await nextTick(); if (paymentDialogTrigger?.isConnected) paymentDialogTrigger.focus();
      }
    });
    async function openPaymentDialog(booking, kind = 'booking') {
      if (paymentBusy.value) return;
      const session = token.value;
      paymentBusy.value = true; paymentError.value = '';
      try {
        paymentKind.value = kind;
        editingServicePaymentMethod.value = false;
        const data = await paymentApi(`${kind === 'service' ? '/services/avails' : '/bookings'}/${booking.id}`);
        if (session !== token.value || !currentUser.value) return false;
        const record = kind === 'service' ? data.avail : data.booking;
        paymentBooking.value = kind === 'service' ? serviceReceipt(record) : bookingReceipt({ ...record, room: booking.room }); paymentHistory.value = data.payments || [];
        if (kind === 'booking' && lastBooking.value.id === record.id) lastBooking.value = { ...paymentBooking.value };
        paymentForm.value = { method: record.requested_payment_method || record.submitted_payment_method || (currentUser.value?.role === 'staff' ? 'cash' : paymentOptions.value.accounts[0]?.method || (kind === 'service' ? 'cash' : 'gcash')), reference: record.payment_review_status === 'pending_review' ? record.submitted_payment_reference || '' : '',
          proof: '', amount: record.deposit_due > 0 ? record.deposit_due : record.balance_due, verified: false, note: '' };
        if (currentUser.value?.role !== 'staff' && !(kind === 'service' && paymentForm.value.method === 'cash') && !paymentOptions.value.accounts.some(account => account.method === paymentForm.value.method)) {
          paymentForm.value.method = paymentOptions.value.accounts[0]?.method || (kind === 'service' ? 'cash' : '');
        }
        showPaymentDialog.value = true;
        return true;
      } catch (error) { if (session === token.value) showToast(error.message, 'error'); return false; } finally { paymentBusy.value = false; }
    }
    function readPaymentProof(event) {
      const file = event.target.files?.[0]; if (!file) return;
      if (!['image/jpeg','image/png','image/webp'].includes(file.type) || file.size > 2*1024*1024) { paymentError.value = 'Use a JPG, PNG or WebP screenshot up to 2 MB.'; event.target.value = ''; return; }
      paymentPhotoReading.value = true; paymentError.value = '';
      const reader = new FileReader();
      reader.onload = () => { paymentForm.value.proof = reader.result; paymentPhotoReading.value = false; };
      reader.onerror = () => { paymentError.value = 'Could not read this screenshot.'; paymentPhotoReading.value = false; };
      reader.readAsDataURL(file);
    }
    async function saveBookingPayment(reject = false) {
      if (paymentBusy.value || paymentPhotoReading.value || !paymentBooking.value) return;
      paymentBusy.value = true; paymentError.value = '';
      const staff = currentUser.value?.role === 'staff';
      const booking = paymentBooking.value;
      try {
        let path, body;
        if (reject) { path = 'payment-rejection'; body = { note: paymentForm.value.note }; }
        else if (staff) {
          path = 'payments'; body = { amount: paymentForm.value.amount, method: paymentForm.value.method, reference: paymentForm.value.reference, verified: paymentForm.value.verified };
          body.request_key = requestKey(paymentKind.value + '-payment', { id: booking.id, paid: booking.amount_paid, ...body });
        } else if (paymentKind.value === 'service' && paymentForm.value.method === 'cash') {
          path = 'pay-at-counter'; body = {};
        } else { path = 'payment-submission'; body = { method: paymentForm.value.method, reference: paymentForm.value.reference, proof: paymentForm.value.proof }; }
        const data = await paymentApi(`${paymentKind.value === 'service' ? '/services/avails' : '/bookings'}/${booking.id}/${path}`, body);
        if (paymentKind.value === 'service') {
          paymentBooking.value = serviceReceipt(data.avail, booking.room); await fetchServiceAvails(); await fetchServices();
        } else {
          paymentBooking.value = bookingReceipt(data.booking);
          if (lastBooking.value.id === data.booking.id) lastBooking.value = bookingReceipt(data.booking);
          if (staff) await fetchAllBookings(); else await fetchUserBookings();
        }
        const counterChoice = !staff && paymentKind.value === 'service' && path === 'pay-at-counter';
        showPaymentDialog.value = false;
        if (counterChoice) {
          lastCounterService.value = { ...paymentBooking.value };
          editingServicePaymentMethod.value = false;
          navigate('service-confirm');
          await nextTick();
          window.scrollTo?.({ top: 0, behavior: 'auto' });
          document.getElementById('service-counter-confirm-heading')?.focus();
        }
        showToast(counterChoice ? 'Pay at the counter selected. Show your request reference when you arrive.' : reject ? 'Payment submission rejected.' : staff ? 'Payment recorded.' : 'Submitted for verification. Payment is not confirmed until staff verify it.', 'success', 5000);
      } catch (error) { paymentError.value = error.message; } finally { paymentBusy.value = false; }
    }
    async function openWalkInDialog(kind = 'booking') {
      walkInKind.value = kind;
      paymentError.value = ''; if (kind === 'service') await fetchServices(); else await fetchRooms();
      walkInForm.value = { room_id: '', guest_name: '', guest_phone: '', check_in_date: today, check_out_date: '', num_guests: 1, payment_method: 'cash', payment_reference: '', payment_received: false };
      showWalkInDialog.value = true;
    }
    async function saveWalkIn() {
      if (paymentBusy.value) return;
      paymentBusy.value = true; paymentError.value = '';
      const body = { ...walkInForm.value, ...(walkInKind.value === 'service' ? { service_id: walkInForm.value.room_id, quantity: walkInForm.value.num_guests } : { booking_source: 'walk_in' }), expected_total: walkInTotal.value };
      body.request_key = requestKey(walkInKind.value + '-walk-in', body);
      try {
        const data = await paymentApi(walkInKind.value === 'service' ? '/services/avails/walk-in' : '/bookings', body);
        if (walkInKind.value === 'service') {
          showWalkInDialog.value = false; staffTab.value = 'services';
          await fetchServiceAvails(); await fetchServices();
          paymentRequestKeys.clear(); paymentBusy.value = false;
          await openPaymentDialog(data.avail, 'service');
          return;
        }
        lastBooking.value = bookingReceipt({ ...data.booking, room: walkInRoom.value?.name });
        paymentRequestKeys.clear(); bookingReferenceCopied.value = false; showWalkInDialog.value = false;
        staffTab.value = 'bookings'; navigate('confirm');
      } catch (error) { paymentError.value = error.message; } finally { paymentBusy.value = false; }
    }
    const bookingReferenceCopied = ref(false);
    async function copyBookingReference() {
      if (!lastBooking.value.ref) return;
      try {
        await navigator.clipboard.writeText(String(lastBooking.value.ref));
        bookingReferenceCopied.value = true;
      } catch {
        showToast('Please select and copy the booking reference.', 'info');
      }
    }
    const allBookings = ref([]);
    const services = ref([]);
    const staffPages = ref({ bookings: 1, services: 1, requests: 1, rooms: 1 });
    const staffPageSize = 10;
    const staffPagination = computed(() => {
      const sources = { bookings: filteredStaffBookings.value, services: services.value, requests: serviceAvails.value, rooms: rooms.value };
      return Object.fromEntries(Object.entries(sources).map(([key, records]) => {
        const total = records.length;
        const pages = Math.max(1, Math.ceil(total / staffPageSize));
        const page = Math.max(1, Math.min(staffPages.value[key], pages));
        const offset = (page - 1) * staffPageSize;
        return [key, { page, pages, total, start: total ? offset + 1 : 0, end: Math.min(offset + staffPageSize, total), rows: records.slice(offset, offset + staffPageSize) }];
      }));
    });
    function changeStaffPage(key, direction) {
      const pager = staffPagination.value[key];
      if (!pager) return;
      staffPages.value[key] = Math.max(1, Math.min(pager.page + direction, pager.pages));
    }
    watch([staffBookingSearch, staffBookingStatus], () => { staffPages.value.bookings = 1; });
    watch(() => [filteredStaffBookings.value.length, services.value.length, serviceAvails.value.length, rooms.value.length], () => {
      for (const key of Object.keys(staffPages.value)) staffPages.value[key] = staffPagination.value[key].page;
    });
    const showServiceModal = ref(false);
    const showForgotPassword = ref(false);
    const forgotEmail = ref('');
    const forgotMsg = ref('');
    const forgotMsgType = ref('');

    // THE GLOBAL KILL-SWITCH
    const showResetPassword = ref(false);
    const resetPassword = ref('');
    const resetPasswordConfirm = ref('');
    const resetMsg = ref('');
    const resetMsgType = ref('');
    const resetToken = ref('');

    // Emergency Kill-Switch for Reset Modal
    const hasProcessedToken = ref(false);

    onMounted(async () => {
      // ABSOLUTE UI RESET: Kill all popups immediately
      showResetPassword.value = false;
      showForgotPassword.value = false;
      showRoomModal.value = false;
      showServiceAdminModal.value = false;
      showServiceModal.value = false; // FORCE CLOSE SERVICE MODAL
      resetToken.value = '';

      // 1. COMPLETELY PURGE STATE
      showResetPassword.value = false;
      resetToken.value = '';

      const uParams = new URLSearchParams(window.location.search);
      const urlResetToken = uParams.get('reset_token');

      if (urlResetToken && !hasProcessedToken.value) {
        resetToken.value = urlResetToken;
        showResetPassword.value = true;
        hasProcessedToken.value = true;

        const cleanUrl = window.location.origin + window.location.pathname;
        window.history.replaceState({}, document.title, cleanUrl);
      } else {
        // FORCE EVERYTHING CLOSED
        showResetPassword.value = false;
        resetToken.value = '';
      }

      // Initial data bootstrap
      try {
        await fetchPaymentOptions();
        await fetchServices();
        if (token.value) {
          await fetchCurrentUser();
        }
        await fetchRooms();
        if (currentUser.value) {
          if (currentUser.value.role === 'staff') await fetchAllBookings();
          else await fetchUserBookings();
          await fetchServiceAvails();
        }
      } catch (e) {}
    });

    async function doResetPassword() {
      if (!resetPassword.value || !resetPasswordConfirm.value) return;
      if (resetPassword.value !== resetPasswordConfirm.value) {
        resetMsg.value = 'Passwords do not match.';
        resetMsgType.value = 'error';
        return;
      }
      try {
        const res = await fetch(`${API_URL}/auth/reset-password`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ token: resetToken.value, password: resetPassword.value })
        });
        const data = await res.json();
        if (!res.ok) {
          resetMsg.value = data.error || 'Reset failed.';
          resetMsgType.value = 'error';
        } else {
          resetMsg.value = '✅ Password reset successfully! You can now sign in with your new password.';
          resetMsgType.value = 'success';
          showToast('Password updated! Sign in with your new password. 🔐', 'success', 4000);
          setTimeout(() => { showResetPassword.value = false; navigate('auth'); }, 2500);
        }
      } catch (err) {
        resetMsg.value = 'Connection error: ' + err.message;
        resetMsgType.value = 'error';
      }
    }

    async function doForgotPassword() {
      if (!forgotEmail.value) return;
      
      // Validate email format
      const emailRegex = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
      if (!emailRegex.test(forgotEmail.value)) {
        forgotMsg.value = 'Please enter a valid email address.';
        forgotMsgType.value = 'error';
        return;
      }
      
      try {
        const res = await fetch(`${API_URL}/auth/forgot-password`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email: forgotEmail.value })
        });
        const data = await res.json();
        if (!res.ok) {
          forgotMsg.value = data.error || 'Something went wrong.';
          forgotMsgType.value = 'error';
        } else {
          forgotMsg.value = '✅ Password reset link has been sent to your email! Check your inbox.';
          forgotMsgType.value = 'success';
          showToast('Check your email for the reset link! 📧', 'success', 4000);
          forgotEmail.value = '';
          setTimeout(() => { showForgotPassword.value = false; }, 2500);
        }
      } catch (err) {
        forgotMsg.value = 'Connection error: ' + err.message;
        forgotMsgType.value = 'error';
      }
    }
    const serviceModalData = ref({ icon: '', name: '', price: '', guest: '' });

    // ── REVIEWS STATE ──────────────────────────────────────────────────────────
    const reviews = ref([]);
    const reviewsAvg = ref(0);
    const reviewsTotal = ref(0);
    const reviewForm = ref({ rating: 0, review: '' });
    const reviewHover = ref(0);

    // ── COMPUTED ───────────────────────────────────────────────────────────────
    const filteredRooms = computed(() => rooms.value.filter(r => {
      if (filters.value.type && r.type !== filters.value.type) return false;
      if (filters.value.maxPrice && r.price_per_night > Number(filters.value.maxPrice)) return false;
      if (filters.value.capacity && r.capacity < Number(filters.value.capacity)) return false;
      return true;
    }));

    const bookingNights = computed(() => {
      if (!bookingForm.value.checkIn || !bookingForm.value.checkOut) return 0;
      const d = (new Date(bookingForm.value.checkOut) - new Date(bookingForm.value.checkIn)) / 86400000;
      return d > 0 ? d : 0;
    });

    const bookingTotal = computed(() => {
      if (!selectedRoom.value || bookingNights.value <= 0) return 0;
      const sub = selectedRoom.value.price_per_night * bookingNights.value;
      return Math.round((sub + sub * 0.1) * 100) / 100;
    });

    const upcomingBookings = computed(() => {
      return allBookings.value.filter(b => (b.check_in || b.check_in_date) >= today && b.status !== 'cancelled' && b.status !== 'completed');
    });

    const pastBookings = computed(() => {
      return allBookings.value.filter(b => (b.check_in || b.check_in_date) < today || b.status === 'cancelled' || b.status === 'completed');
    });

    const guestBookingPage = ref(1);
    const guestBookingPageSize = 3;
    const activeGuestBookings = computed(() => dashTab.value === 'upcoming' ? upcomingBookings.value : pastBookings.value);
    const guestBookingPageCount = computed(() => Math.max(1, Math.ceil(activeGuestBookings.value.length / guestBookingPageSize)));
    const guestBookingRangeStart = computed(() => activeGuestBookings.value.length ? (guestBookingPage.value - 1) * guestBookingPageSize + 1 : 0);
    const guestBookingRangeEnd = computed(() => Math.min(guestBookingPage.value * guestBookingPageSize, activeGuestBookings.value.length));
    const pagedGuestBookings = computed(() => activeGuestBookings.value.slice((guestBookingPage.value - 1) * guestBookingPageSize, guestBookingPage.value * guestBookingPageSize));
    watch([dashTab, currentUser], () => { guestBookingPage.value = 1; }, { flush: 'sync' });
    watch(guestBookingPageCount, count => { guestBookingPage.value = Math.min(guestBookingPage.value, count); }, { flush: 'sync' });
    async function changeGuestBookingPage(direction) {
      guestBookingPage.value = Math.max(1, Math.min(guestBookingPageCount.value, guestBookingPage.value + direction));
      await nextTick();
      document.getElementById('guest-bookings-heading')?.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'start' });
    }

    const guestServicePage = ref(1);
    const guestServicePageSize = 3;
    const guestServicePageCount = computed(() => Math.max(1, Math.ceil(serviceAvails.value.length / guestServicePageSize)));
    const guestServiceRangeStart = computed(() => serviceAvails.value.length ? (guestServicePage.value - 1) * guestServicePageSize + 1 : 0);
    const guestServiceRangeEnd = computed(() => Math.min(guestServicePage.value * guestServicePageSize, serviceAvails.value.length));
    const pagedGuestServices = computed(() => serviceAvails.value.slice((guestServicePage.value - 1) * guestServicePageSize, guestServicePage.value * guestServicePageSize));
    watch(currentUser, () => { guestServicePage.value = 1; }, { flush: 'sync' });
    watch(guestServicePageCount, count => { guestServicePage.value = Math.min(guestServicePage.value, count); }, { flush: 'sync' });
    async function changeGuestServicePage(direction) {
      guestServicePage.value = Math.max(1, Math.min(guestServicePageCount.value, guestServicePage.value + direction));
      await nextTick();
      document.getElementById('guest-services-heading')?.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'start' });
    }

    // Finds a completed booking for the selected room that the current user
    // owns and hasn't reviewed yet — this unlocks the "Leave a Review" form.
    const eligibleBooking = computed(() => {
      if (!currentUser.value || !selectedRoom.value) return null;
      return allBookings.value.find(b =>
        b.user_id === currentUser.value.id &&
        b.room_id === selectedRoom.value.id &&
        b.status === 'completed' &&
        !reviews.value.find(r => r.booking_id === b.id)
      ) || null;
    });

    // ── HELPERS ────────────────────────────────────────────────────────────────
    function statusLabel(status) {
      if (status === 'fully_booked') return 'Fully Booked';
      if (status === 'under_maintenance') return 'Under Maintenance';
      return 'Available';
    }
    function statusClass(status) {
      if (status === 'fully_booked') return 'status-fully-booked';
      if (status === 'under_maintenance') return 'status-maintenance';
      return 'status-confirmed';
    }

    const features = [
      { title: 'Out in nature', desc: 'Open fields, fresh air, and the quieter pace of a day outdoors.' },
      { title: 'A comfortable room', desc: 'Farm-inspired rooms with wooden accents, comfortable bedding, and garden views.' },
      { title: 'A game together', desc: 'Bring your friends together for a game on our outdoor volleyball court.' },
      { title: 'Plan your stay', desc: 'Browse rooms, check availability, and send your booking request online.' },
    ];

    const teamMembers = [
      { name: 'Maximana Morales', initials: 'MM', role: 'Founder & Owner', photo: 'https://i.imgur.com/WOf3fU3.jpg', desc: 'The heart of the resort. Maximana turned her family farm into a beloved getaway with warmth and determination.', color: 'linear-gradient(135deg,#4a7c3f,#2d4a1e)' },
      { name: 'Mick Daniel Morales', initials: 'MD', role: 'Fullstack Developer', photo: 'https://i.imgur.com/izbkYqi.jpg', desc: "Built the resort's website and booking experience to help guests plan their stay.", color: 'linear-gradient(135deg,#2d6a5f,#1a2e2a)' },
    ];

    const faqs = ref([
      { q: 'Do I need to book in advance for day entrance?', a: 'No reservation needed! Just walk in and pay the ₱100 entrance fee at the gate. However, during peak seasons and holidays, we recommend arriving early as capacity may be limited.', open: false },
      { q: 'Can I book the karaoke room on the same day?', a: "Yes! You can walk in and use the karaoke room if it's available. But on weekends and holidays, we highly recommend reserving in advance to secure your slot.", open: false },
      { q: 'Is the entrance fee included when I book a room?', a: "Yes! Guests who book a room at Minnie's Farm Resort enjoy complimentary resort access throughout their stay. The entrance fee only applies to walk-in day guests.", open: false },
      { q: "What are the resort's operating hours?", a: 'The resort is open daily from 7:00 AM to 9:00 PM. Day guests must exit by 8:00 PM. Karaoke sessions must end by 8:30 PM.', open: false },
      { q: 'What is the entrance fee for children?', a: 'Children aged 3 years old and below enter for FREE. Children 4 to 12 years old pay the regular ₱100 entrance fee.', open: false },
    ]);

    // ── NAVIGATION ─────────────────────────────────────────────────────────────
    function showToast(message, type = 'success', duration = 3000) {
      const toastObj = { message, type, removing: false };
      toasts.value.push(toastObj);
      setTimeout(() => {
        toastObj.removing = true;
        setTimeout(() => {
          toasts.value.splice(toasts.value.indexOf(toastObj), 1);
        }, 300);
      }, duration);
    }

    function navigate(p) {
      page.value = p;
      mobileMenuOpen.value = false; // Close mobile menu on navigation
      authMsg.value = '';
      if (p === 'rooms') { rooms.value = []; setTimeout(fetchRooms, 50); }
      if (p === 'dashboard') {
        if (currentUser.value?.role === 'staff') { fetchAllBookings(); fetchServiceAvails(); }
        else { fetchUserBookings(); fetchServiceAvails(); }
      }
      if (p === 'services') { services.value = []; setTimeout(fetchServices, 50); }
    }

    // ── AUTH ───────────────────────────────────────────────────────────────────
    const GOOGLE_CLIENT_ID = '549203417668-bl1k05ionrenlhnukkui7b6hka24rbbe.apps.googleusercontent.com';

    function googleLogin() {
      if (!window.google || !window.google.accounts) {
        authMsg.value = 'Google services not loaded. Please refresh the page and try again.';
        authMsgType.value = 'error';
        authMsgKey.value++;
        return;
      }
      
      const client = google.accounts.oauth2.initTokenClient({
        client_id: GOOGLE_CLIENT_ID,
        scope: 'email profile',
        callback: async (tokenResponse) => {
          if (tokenResponse.error) {
            authMsg.value = 'Google login was cancelled.';
            authMsgType.value = 'error';
            authMsgKey.value++;
            return;
          }
          // Get user info from Google
          try {
            const res = await fetch('https://www.googleapis.com/oauth2/v3/userinfo', {
              headers: { Authorization: `Bearer ${tokenResponse.access_token}` }
            });
            const googleUser = await res.json();
            
            if (!googleUser.email) {
              authMsg.value = 'Could not get email from Google.';
              authMsgType.value = 'error';
              authMsgKey.value++;
              return;
            }
            
            // Send to our backend
            const backendRes = await fetch(`${API_URL}/auth/google`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                access_token: tokenResponse.access_token
              })
            });
            const data = await backendRes.json();
            
            if (!backendRes.ok) { 
              authMsg.value = data.error || 'Google login failed'; 
              authMsgType.value = 'error';
              authMsgKey.value++;
              return; 
            }
            
            token.value = data.token;
            localStorage.setItem('token', data.token);
            currentUser.value = data.user;
            authMsg.value = '✅ Logged in with Google!';
            authMsgType.value = 'success';
            showToast(`Welcome, ${data.user.name}! 🎉`, 'success', 3000);
            setTimeout(() => navigate(data.user.role === 'staff' ? 'dashboard' : 'rooms'), 800);
          } catch (err) {
            authMsg.value = 'Connection error: ' + err.message;
            authMsgType.value = 'error';
            authMsgKey.value++;
          }
        }
      });
      client.requestAccessToken();
    }

    async function doLogin() {
      if (!loginForm.value.email || !loginForm.value.password) {
        authMsg.value = 'Please fill in all fields.';
        authMsgType.value = 'error';
        authMsgKey.value++;
        return;
      }
      
      // Validate email format
      const emailRegex = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
      if (!emailRegex.test(loginForm.value.email)) {
        authMsg.value = 'Please enter a valid email address.';
        authMsgType.value = 'error';
        authMsgKey.value++;
        return;
      }
      
      loading.value = true;
      try {
        const res = await fetch(`${API_URL}/auth/login`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email: loginForm.value.email, password: loginForm.value.password })
        });
        const data = await res.json();
        if (!res.ok) {
          authMsg.value = data.error || 'Login failed';
          authMsgType.value = 'error';
          authMsgKey.value++;
          return;
        }
        token.value = data.token;
        localStorage.setItem('token', data.token);
        currentUser.value = data.user;
        authMsg.value = '✅ Logged in successfully!';
        authMsgType.value = 'success';
        showToast(`Welcome back, ${data.user.name}! 🎉`, 'success', 3000);
        loginForm.value = { email: '', password: '' };
        setTimeout(() => navigate(data.user.role === 'staff' ? 'dashboard' : 'rooms'), 800);
      } catch (err) {
        authMsg.value = 'Connection error: ' + err.message;
        authMsgType.value = 'error';
        authMsgKey.value++;
      } finally {
        loading.value = false;
      }
    }

    async function doRegister() {
      if (!regForm.value.name || !regForm.value.email || !regForm.value.password) {
        authMsg.value = 'Please fill in all fields.'; 
        authMsgType.value = 'error'; 
        authMsgKey.value++;
        return;
      }
      if (regForm.value.password !== regForm.value.confirm) {
        authMsg.value = 'Passwords do not match.'; 
        authMsgType.value = 'error'; 
        authMsgKey.value++;
        return;
      }
      
      // Validate email format
      const emailRegex = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
      if (!emailRegex.test(regForm.value.email)) {
        authMsg.value = 'Please enter a valid email address (e.g., user@example.com).'; 
        authMsgType.value = 'error'; 
        authMsgKey.value++;
        return;
      }
      
      loading.value = true;
      try {
        const res = await fetch(`${API_URL}/auth/register`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: regForm.value.name, email: regForm.value.email, password: regForm.value.password, role: 'guest' })
        });
        const data = await res.json();
        if (!res.ok) { 
          authMsg.value = data.error || 'Registration failed'; 
          authMsgType.value = 'error'; 
          authMsgKey.value++;
          return; 
        }
        // Success: account created, user is verified and can login
        authMsg.value = '✅ Account created! You can now sign in.';
        authMsgType.value = 'success';
        showToast('Account created! Sign in with your credentials. 🎉', 'success', 3000);
        regForm.value = { name: '', email: '', password: '', confirm: '', role: 'guest' };
        // Switch to login tab after 3 seconds
        setTimeout(() => {
          authTab.value = 'login';
          authMsg.value = '';
        }, 3000);
      } catch (err) { 
        authMsg.value = 'Connection error: ' + err.message; 
        authMsgType.value = 'error'; 
        authMsgKey.value++;
      } finally {
        loading.value = false;
      }
    }

    async function logout() {
      try {
        await fetch(`${API_URL}/auth/logout`, { method: 'POST', headers: { 'Authorization': `Bearer ${token.value}` } });
      } catch (err) {}
      currentUser.value = null;
      token.value = '';
      localStorage.removeItem('token');
      navigate('home');
    }

    async function fetchCurrentUser() {
      if (!token.value) return;
      try {
        const res = await fetch(`${API_URL}/auth/me`, { headers: { 'Authorization': `Bearer ${token.value}` } });
        if (res.ok) { const data = await res.json(); currentUser.value = data.user; }
        else { localStorage.removeItem('token'); token.value = ''; }
      } catch (err) {}
    }

    // ── ROOMS ──────────────────────────────────────────────────────────────────
    async function fetchRooms() {
      roomsLoading.value = true;
      roomLoadError.value = false;
      try {
        // Clear existing data first to force UI update
        rooms.value = [];
        // Force Vue to re-render by waiting a tick
        await new Promise(resolve => setTimeout(resolve, 50));
        // Build URL with cache-busting timestamp
        const params = new URLSearchParams();
        params.append('_t', Date.now()); // Cache buster
        if (currentUser.value?.role !== 'staff') {
          if (filters.value.type) params.append('type', filters.value.type);
          if (filters.value.maxPrice) params.append('max_price', filters.value.maxPrice);
          if (filters.value.capacity) params.append('capacity', filters.value.capacity);
        }
        const url = `${API_URL}/rooms?${params.toString()}`;
        const res = await fetch(url, {
          headers: { 'Cache-Control': 'no-cache', 'Pragma': 'no-cache' }
        });
        if (res.ok) {
          const data = await res.json();
          rooms.value = [...(data.rooms || [])]; // Force new array reference
          rooms.value.forEach(r => {
            if (!r.emoji) {
              const emojis = { 'Standard': '👤', 'Themed': '🎈', 'Deluxe': '👥', 'Suite': '🏠' };
              r.emoji = emojis[r.type] || '🏠';
            }
          });
        } else {
          throw new Error('Could not load rooms');
        }
      } catch (err) {
        roomLoadError.value = true;
      } finally {
        roomsLoading.value = false;
      }
    }

    // ── BOOKINGS ─────────────────────────────────────────
    function clearSessionAndGoToAuth(message = 'Your session expired. Please log in again.') {
      currentUser.value = null;
      token.value = '';
      try { localStorage.removeItem('token'); } catch (e) {}
      showToast(message, 'error');
      navigate('auth');
    }

    async function doBook() {
      if (loading.value) return;
      if (!currentUser.value || !token.value) {
        clearSessionAndGoToAuth('Please log in to continue booking. 🔐');
        return;
      }
      if (bookingNights.value <= 0) {
        showToast('Please select valid dates! 📅', 'error');
        return;
      }

      loading.value = true;

      try {
        const res = await fetch(`${API_URL}/bookings`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token.value}` },
          body: JSON.stringify({ 
            room_id: selectedRoom.value.id, 
            check_in_date: bookingForm.value.checkIn, 
            check_out_date: bookingForm.value.checkOut, 
            num_guests: bookingForm.value.guests,
            total_price: bookingTotal.value,
            request_key: requestKey('online-booking', { room: selectedRoom.value.id, ...bookingForm.value })
          })
        });

        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          showToast(data.error || 'Booking failed', 'error');
          return;
        }

        showToast('Reservation created. Submit your deposit within 3 hours.', 'success');
        bookingReferenceCopied.value = false;
        lastBooking.value = {
          ...data.booking,
          ref: data.booking.reference_code,
          room: selectedRoom.value.name,
          checkIn: data.booking.check_in || data.booking.check_in_date,
          checkOut: data.booking.check_out || data.booking.check_out_date,
          guests: data.booking.guest_count || data.booking.num_guests,
          total: data.booking.total_price
        };
        paymentRequestKeys.clear();
        await fetchUserBookings();
        navigate('confirm');
      } catch (err) {
        showToast('Connection error: ' + err.message, 'error');
      } finally {
        loading.value = false;
      }
    }

    async function fetchUserBookings() {
      if (!token.value || !currentUser.value) return;
      try {
        const res = await fetch(`${API_URL}/bookings?user_id=${currentUser.value.id}&_t=${Date.now()}`, { 
          headers: { 
            'Authorization': `Bearer ${token.value}`,
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache'
          } 
        });
        if (res.ok) {
          const data = await res.json();

          allBookings.value = (data.bookings || []).map(b => {
            const room = rooms.value.find(r => r.id === b.room_id);
            return {
              ...b,
              guestName: currentUser.value.name,
              emoji: room?.emoji || '🏠',
              room: b.room_name || room?.name || 'Room ' + b.room_id,
              checkIn: b.check_in || b.check_in_date,
              checkOut: b.check_out || b.check_out_date,
              guest_count: b.guest_count || b.num_guests || 1, // Add this
              total_price: b.total_price || b.total || 0, // Add this
              guests: b.guest_count || b.num_guests || 1,
              total: b.total_price || b.total || 0
            };
          });
        }
      } catch (err) {}
    }

    async function fetchAllBookings() {
      try {
        const res = await fetch(`${API_URL}/bookings?staff=true&_t=${Date.now()}`, { 
          headers: { 
            'Authorization': `Bearer ${token.value || localStorage.getItem('token')}`,
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache'
          } 
        });
        if (res.ok) {
          const data = await res.json();
          
          allBookings.value = (data.bookings || []).map(b => {
            const room = rooms.value.find(r => r.id === b.room_id);
            return {
              ...b, 
              guestName: b.walk_in_guest_name || b.guest_name || 'Guest ' + b.user_id,
              room: b.room_name || room?.name || 'Room ' + b.room_id,
              checkIn: b.check_in || b.check_in_date, 
              checkOut: b.check_out || b.check_out_date,
              guest_count: b.guest_count || b.num_guests || 1, // Add this
              total_price: b.total_price || b.total || 0, // Add this
              guests: b.guest_count || b.num_guests || 1,
              total: b.total_price || b.total || 0
            };
          });
        }
      } catch (e) {}
    }

    function cancelBooking(b) {
      pendingCancelBooking.value = b;
      bookingCancellationError.value = '';
      showCancelBookingModal.value = true;
    }
    async function confirmCancelBooking() {
      if (!pendingCancelBooking.value || bookingCancellationBusy.value) return;
      bookingCancellationBusy.value = true;
      bookingCancellationError.value = '';
      try {
        const res = await fetch(`${API_URL}/bookings/${pendingCancelBooking.value.id}`, { method: 'DELETE', headers: { 'Authorization': `Bearer ${token.value}` } });
        if (!res.ok) {
          bookingCancellationError.value = 'We could not cancel this reservation. Please try again.';
          return;
        }
        await fetchUserBookings();
        showCancelBookingModal.value = false;
        pendingCancelBooking.value = null;
        showToast('Your reservation has been cancelled.', 'success');
      } catch {
        bookingCancellationError.value = 'Could not connect. Please try again.';
      } finally {
        bookingCancellationBusy.value = false;
      }
    }

    async function updateBookingStatus(b, status) {
      try {
        const t = token.value || localStorage.getItem('token');
        const res = await fetch(`${API_URL}/bookings/${b.id}/status`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${t}` },
          body: JSON.stringify({ status })
        });
        if (res.ok) {
          await fetchAllBookings();
          return;
        }

        const contentType = res.headers.get('content-type') || '';
        const bodyText = await res.text();
        if (contentType.includes('application/json')) {
          try {
            const data = JSON.parse(bodyText || '{}');
            showToast(data.error || data.message || 'Error updating status', 'error');
          } catch {
            showToast('Error updating status', 'error');
          }
        } else {
          showToast('Could not update the booking. Please refresh and try again.', 'error');
        }
      } catch (e) { showToast('Could not connect. Please try again.', 'error'); }
    }

    function resetFilters() { filters.value = { checkIn: '', checkOut: '', type: '', maxPrice: '', capacity: '' }; fetchRooms(); }

    // Updated viewRoom — now resets and fetches reviews before navigating
    function viewRoom(room) {
      fetchPaymentOptions();
      selectedRoom.value = room;
      activeRoomPhoto.value = 0;
      cancelRoomPhotoGesture();
      bookingForm.value = { checkIn: filters.value.checkIn, checkOut: filters.value.checkOut, guests: 1 };
      // Reset reviews state for the new room
      reviews.value = [];
      reviewsAvg.value = 0;
      reviewsTotal.value = 0;
      reviewForm.value = { rating: 0, review: '' };
      reviewHover.value = 0;
      fetchReviews(room.id);
      navigate('detail');
    }

    // ── REVIEWS ─────────────────────────────────
    async function fetchReviews(roomId) {
      try {
        const res = await fetch(`${API_URL}/reviews?room_id=${roomId}`);
        if (res.ok) {
          const data = await res.json();
          reviews.value = data.reviews || [];
          reviewsAvg.value = data.average_rating || 0;
          reviewsTotal.value = data.total_reviews || 0;
        }
      } catch (err) {}
    }

    async function submitReview() {
      if (!reviewForm.value.rating) { showToast('Please select a star rating.', 'error'); return; }
      if (!eligibleBooking.value) return;
      try {
        const res = await fetch(`${API_URL}/reviews`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token.value}` },
          body: JSON.stringify({
            room_id: selectedRoom.value.id,
            booking_id: eligibleBooking.value.id,
            rating: reviewForm.value.rating,
            review: reviewForm.value.review,
          })
        });
        const data = await res.json();
        if (!res.ok) { showToast(data.error || 'Error submitting review', 'error'); return; }
        reviewForm.value = { rating: 0, review: '' };
        reviewHover.value = 0;
        await fetchReviews(selectedRoom.value.id);
      } catch (err) { showToast('Could not connect. Please try again.', 'error'); }
    }

    // ── ROOM MANAGEMENT (staff) ────────────────────────────
    function openAddRoom() {
      editingRoom.value = null;
      roomForm.value = {
        room_number: '', name: '', type: 'Standard', capacity: 2, price_per_night: '',
        description: '', sqm: '', amenities: '', image_url: '', image_url_2: '', image_url_3: '',
        image_url_4: '', image_url_5: '', room_status: 'available'
      };
      showRoomModal.value = true;
    }

    function editRoom(r) {
      editingRoom.value = r;
      roomForm.value = {
        room_number: r.room_number || '', name: r.name, type: r.type, capacity: r.capacity,
        price_per_night: r.price_per_night, description: r.description, sqm: r.sqm || '', amenities: Array.isArray(r.amenities) ? r.amenities.join(', ') : (r.amenities || ''),
        image_url: r.image_url || '',
        image_url_2: r.image_url_2 || '',
        image_url_3: r.image_url_3 || '',
        image_url_4: r.image_url_4 || '',
        image_url_5: r.image_url_5 || '',
        room_status: r.room_status || 'available'
      };
      showRoomModal.value = true;
    }

    async function saveRoom() {
      if (roomEditorBusy.value) return;
      if (!roomForm.value.room_number || !roomForm.value.name || !roomForm.value.price_per_night) { showToast('Please fill in Room Number, Room Name, and Price/Night', 'error'); return; }
      loading.value = true;
      try {
        const method = editingRoom.value ? 'PUT' : 'POST';
        const url = editingRoom.value ? `${API_URL}/rooms/${editingRoom.value.id}` : `${API_URL}/rooms`;
        const t = token.value || localStorage.getItem('token');
        const res = await fetch(url, {
          method,
          headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${t}` },
          body: JSON.stringify({
            room_number: roomForm.value.room_number,
            name: roomForm.value.name,
            type: roomForm.value.type,
            sqm: roomForm.value.sqm ? Number(roomForm.value.sqm) : null,
            amenities: roomForm.value.amenities ? roomForm.value.amenities.split(',').map(a => a.trim()).filter(a => a) : [],
            capacity: Number(roomForm.value.capacity),
            price_per_night: Number(roomForm.value.price_per_night),
            description: roomForm.value.description,
            image_url: roomForm.value.image_url,
            image_url_2: roomForm.value.image_url_2,
            image_url_3: roomForm.value.image_url_3,
            image_url_4: roomForm.value.image_url_4,
            image_url_5: roomForm.value.image_url_5,
            room_status: roomForm.value.room_status,
          })
        });
        if (res.ok) { 
          const data = await res.json();
          await fetchRooms(); 
          showRoomModal.value = false;
          showToast(editingRoom.value ? 'Room updated! 🏠' : 'Room created! 🏠', 'success');
        }
        else {
          const contentType = res.headers.get('content-type') || '';
          const bodyText = await res.text();
          if (contentType.includes('application/json')) {
            try {
              const data = JSON.parse(bodyText || '{}');
              showToast(data.error || 'Error saving room', 'error');
            } catch {
              showToast('Error saving room', 'error');
            }
          } else {
            showToast(`Error saving room (HTTP ${res.status})`, 'error');
          }
        }
      } catch (err) { showToast('Connection error: ' + err.message, 'error'); }
      loading.value = false;
    }

    function deleteRoom(r) {
      pendingDeleteRoom.value = r;
      showDeleteRoomModal.value = true;
    }

    async function confirmDeleteRoom() {
      loading.value = true;
      try {
        const t = token.value || localStorage.getItem('token');
        const res = await fetch(`${API_URL}/rooms/${pendingDeleteRoom.value.id}`, {
          method: 'DELETE',
          headers: { 'Authorization': `Bearer ${t}` }
        });
        if (res.ok) {
          await fetchRooms();
          showToast('Room deleted', 'success');
        } else {
          const contentType = res.headers.get('content-type') || '';
          const bodyText = await res.text();
          if (contentType.includes('application/json')) {
            try {
              const data = JSON.parse(bodyText || '{}');
              showToast(data.error || 'Error deleting room', 'error');
            } catch {
              showToast('Error deleting room', 'error');
            }
          } else {
            showToast(`Error deleting room (HTTP ${res.status})`, 'error');
          }
        }
      } catch (err) { showToast('Connection error: ' + err.message, 'error'); }
      showDeleteRoomModal.value = false;
      pendingDeleteRoom.value = null;
      loading.value = false;
    }

    function triggerUpload(index) {
      document.getElementById('file-input-' + index).click();
    }

    function removeImage(index) {
      const fieldName = 'image_url' + (index === 1 ? '' : '_' + index);
      roomForm.value[fieldName] = null;
      // Also clear the file input so it can be re-selected
      const input = document.getElementById('file-input-' + index);
      if (input) input.value = '';
      showToast(`Image ${index} removed. Save to apply.`, 'info');
    }

    const servicesLoading = ref(false);

    async function fetchServices() {
      servicesLoading.value = true;
      try {
        const isStaff = (currentUser.value && currentUser.value.role === 'staff') ? 'true' : 'false';
        const url = `${API_URL}/services?staff=${isStaff}&_t=${Date.now()}`;
        const res = await fetch(url, {
          headers: { 
            'Cache-Control': 'no-cache', 
            'Pragma': 'no-cache',
            'Authorization': token.value ? `Bearer ${token.value}` : ''
          }
        });
        if (res.ok) { 
          const data = await res.json(); 
          services.value = data.services || [];
        }
      } catch (err) {}
      servicesLoading.value = false;
    }

    async function handleFileUpload(event, index) {
      const file = event.target.files[0];
      if (!file) return;
      if (roomEditorBusy.value) return;
      roomImageUploads.value++;

      showToast(`Uploading image ${index}... 📤`, 'info');

      const reader = new FileReader();
      reader.onerror = () => {
        roomImageUploads.value--;
        showToast('Could not read that image. Please try again.', 'error');
      };
      reader.onload = async () => {
        const base64Data = reader.result;
        try {
          const res = await fetch(`${API_URL}/rooms/upload-image`, {
            method: 'POST',
            headers: { 
              'Content-Type': 'application/json',
              'Authorization': `Bearer ${token.value}` 
            },
            body: JSON.stringify({ image: base64Data })
          });

          const data = await res.json();
          if (res.ok) {
            const fieldName = 'image_url' + (index === 1 ? '' : '_' + index);
            roomForm.value[fieldName] = data.image_url;
            showToast(`Image ${index} uploaded! 📸`, 'success');
          } else {
            showToast(data.error || 'Upload failed', 'error');
          }
        } catch (err) {
          showToast('Upload error: ' + err.message, 'error');
        } finally {
          roomImageUploads.value--;
        }
      };
      reader.readAsDataURL(file);
    }

    function deleteServiceAvail(id) {
      pendingDeleteId.value = id;
      showDeleteModal.value = true;
    }

    async function confirmDeleteServiceAvail() {
      const t = token.value || localStorage.getItem('token');
      if (!pendingDeleteId.value) return;
      if (!t) { showToast('Please log in again.', 'error'); return; }
      loading.value = true;
      try {
        const res = await fetch(`${API_URL}/services/avails/${pendingDeleteId.value}`, {
          method: 'DELETE',
          headers: { 'Authorization': `Bearer ${t}` }
        });
        if (res.ok) {
          showToast('Service request cancelled. Payment history retained.', 'success');
          await fetchServices();
          await fetchServiceAvails();
        } else {
          const contentType = res.headers.get('content-type') || '';
          const bodyText = await res.text();
          if (contentType.includes('application/json')) {
            try {
              const d = JSON.parse(bodyText || '{}');
              showToast(d.error || 'Delete failed', 'error');
            } catch {
              showToast('Delete failed', 'error');
            }
          } else {
            showToast(`Delete failed (HTTP ${res.status})`, 'error');
          }
        }
      } catch (err) { showToast('Connection error.', 'error'); }
      showDeleteModal.value = false;
      pendingDeleteId.value = null;
      loading.value = false;
    }

    function deleteBooking(booking) {
      pendingDeleteBookingId.value = booking.id;
      showDeleteBookingModal.value = true;
    }

    async function confirmDeleteBooking() {
      try {
        const res = await fetch(`${API_URL}/bookings/${pendingDeleteBookingId.value}`, {
          method: 'DELETE',
          headers: { 'Authorization': `Bearer ${token.value}` }
        });
        if (res.ok) await fetchAllBookings();
      } catch (err) {}
      showDeleteBookingModal.value = false;
      pendingDeleteBookingId.value = null;
    }

    async function updateAvailStatus(id, newStatus) {
      const t = token.value || localStorage.getItem('token');
      if (!id) { showToast('Invalid request id.', 'error'); return; }
      if (!t) { showToast('Please log in again.', 'error'); return; }
      showToast('Updating service request...', 'info');
      loading.value = true;
      try {
        const res = await fetch(`${API_URL}/services/avails/${id}`, {
          method: 'PATCH',
          headers: { 
            'Content-Type': 'application/json', 
            'Authorization': `Bearer ${t}` 
          },
          body: JSON.stringify({ status: newStatus })
        });
        if (res.ok) {
          showToast(`Service request ${newStatus}`, 'success');
          await fetchServiceAvails();
        } else {
          const contentType = res.headers.get('content-type') || '';
          const bodyText = await res.text();
          if (contentType.includes('application/json')) {
            try {
              const d = JSON.parse(bodyText || '{}');
              showToast(d.error || 'Update failed', 'error');
            } catch {
              showToast('Update failed', 'error');
            }
          } else {
            showToast(`Update failed (HTTP ${res.status})`, 'error');
          }
        }
      } catch (err) { showToast('Connection error.', 'error'); }
      loading.value = false;
    }

    async function updateServiceStock(service) {
      try {
        const res = await fetch(`${API_URL}/services/${service.id}`, {
          method: 'PUT',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token.value}`
          },
          body: JSON.stringify({ stock_quantity: service.stock_quantity })
        });
        const data = await res.json();
        if (res.ok) {
          showToast(`Stock updated for ${service.name}! `, 'success');
        } else {
          showToast(data.error || 'Failed to update stock.', 'error');
        }
      } catch (err) {
        showToast('Connection error.', 'error');
      }
    }

    async function toggleService(service) {
      const newStatus = !service.is_active;
      loading.value = true;
      try {
        const res = await fetch(`${API_URL}/services/${service.id}`, {
          method: 'PUT',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token.value}`
          },
          body: JSON.stringify({ is_active: newStatus })
        });
        
        if (res.ok) {
          showToast(`${service.name} is now ${newStatus ? 'Public' : 'Hidden'}!`, 'success');
          await fetchServices(); // Force refresh everything
        } else {
          const data = await res.json();
          showToast(data.error || 'Failed to toggle service.', 'error');
        }
      } catch (err) {
        showToast('Connection error.', 'error');
      }
      loading.value = false;
    }

    function openAddService() {
      editingService.value = null;
      serviceForm.value = { name: '', category: 'day_service', price: 0, stock_quantity: -1, description: '', is_active: true, image_url: '' };
      serviceImageError.value = '';
      showServiceAdminModal.value = true;
    }

    function editService(s) {
      editingService.value = s;
      serviceForm.value = { ...s, image_url: s.image_url || '' };
      serviceImageError.value = '';
      showServiceAdminModal.value = true;
    }

    async function saveService() {
      if (serviceEditorBusy.value) return;
      if (!token.value && !localStorage.getItem('token')) { navigate('auth'); return; }
      if (!serviceForm.value.name) { showToast('Service name is required', 'error'); return; }

      loading.value = true;
      try {
        const t = token.value || localStorage.getItem('token');
        const isEdit = !!editingService.value;
        const url = isEdit
          ? `${API_URL}/services/${editingService.value.id}`
          : `${API_URL}/services`;

        const res = await fetch(url, {
          method: isEdit ? 'PUT' : 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${t}`
          },
          body: JSON.stringify({
            name: serviceForm.value.name,
            category: serviceForm.value.category,
            price: Number(serviceForm.value.price || 0),
            stock_quantity: Number(serviceForm.value.stock_quantity ?? -1),
            description: serviceForm.value.description,
            is_active: !!serviceForm.value.is_active,
            image_url: serviceForm.value.image_url || null
          })
        });

        if (res.ok) {
          await fetchServices();
          showServiceAdminModal.value = false;
          editingService.value = null;
          showToast(isEdit ? 'Service updated' : 'Service created', 'success');
        } else {
          const contentType = res.headers.get('content-type') || '';
          const bodyText = await res.text();
          if (contentType.includes('application/json')) {
            try {
              const data = JSON.parse(bodyText || '{}');
              showToast(data.error || 'Failed to save service', 'error');
            } catch {
              showToast('Failed to save service', 'error');
            }
          } else {
            showToast(`Failed to save service (HTTP ${res.status})`, 'error');
          }
        }
      } catch (err) {
        showToast('Connection error.', 'error');
      }
      loading.value = false;
    }

    function deleteService(s) {
      pendingDeleteService.value = s;
      showDeleteServiceModal.value = true;
    }

    async function confirmDeleteService() {
      loading.value = true;
      try {
        const t = token.value || localStorage.getItem('token');
        const res = await fetch(`${API_URL}/services/${pendingDeleteService.value.id}`, {
          method: 'DELETE',
          headers: { 'Authorization': `Bearer ${t}` }
        });
        if (res.ok) {
          await fetchServices();
          showToast('Service hidden. Payment history retained.', 'success');
        } else { 
          const contentType = res.headers.get('content-type') || '';
          const bodyText = await res.text();
          if (contentType.includes('application/json')) {
            try {
              const data = JSON.parse(bodyText || '{}');
              showToast(data.error || 'Error deleting service', 'error');
            } catch {
              showToast('Error deleting service', 'error');
            }
          } else {
            showToast(`Error deleting service (HTTP ${res.status})`, 'error');
          }
        }
      } catch (err) { showToast('Connection error.', 'error'); }
      showDeleteServiceModal.value = false;
      pendingDeleteService.value = null;
      loading.value = false;
    }

    async function availService(service) {
      if (!currentUser.value) { navigate('auth'); return; }
      if (paymentBusy.value) return;
      paymentBusy.value = true;
      try {
        const details = { quantity: 1 };
        details.request_key = requestKey('service-request', { service_id: service.id, quantity: 1 });
        const data = await paymentApi(`/services/${service.id}/avail`, details);
        paymentRequestKeys.clear();
        await fetchServiceAvails(); await fetchServices();
        paymentBusy.value = false;
        await openPaymentDialog(data.avail, 'service');
      } catch (error) { showToast(error.message, 'error'); }
      finally { paymentBusy.value = false; }
    }

    async function fetchServiceAvails() {
      if (!token.value || !currentUser.value) return;
      try {
        const isStaff = currentUser.value.role === 'staff';
        const url = isStaff
          ? `${API_URL}/services/avails?staff=true&_t=${Date.now()}`
          : `${API_URL}/services/avails?user_id=${currentUser.value.id}&_t=${Date.now()}`;
        
        const res = await fetch(url, {
          headers: { 
            'Authorization': `Bearer ${token.value}`,
            'Cache-Control': 'no-cache'
          }
        });
        if (res.ok) { 
          const data = await res.json(); 
          serviceAvails.value = (data.avails || []).map(a => ({
            ...a,
            guest_name:
              a.guest_name ||
              a.guestName ||
              a.guest ||
              a.user_name ||
              (a.user && a.user.name) ||
              a.email ||
              a.guest_email ||
              ''
          }));
        }
      } catch (err) {}
    }

    // ── WATCH staffTab ──────────
    const actionDialogBusy = computed(() => loading.value || bookingCancellationBusy.value);
    let actionDialogTrigger = null;
    let actionDialogBodyOverflow = '';
    watch([showCancelBookingModal, showDeleteModal, showDeleteRoomModal, showDeleteBookingModal, showDeleteServiceModal], async flags => {
      if (flags.some(Boolean)) {
        actionDialogTrigger = document.activeElement;
        actionDialogBodyOverflow = document.body.style.overflow;
        document.body.style.overflow = 'hidden';
        await nextTick();
        document.querySelector('.action-dialog [data-safe-action]')?.focus();
      } else {
        document.body.style.overflow = actionDialogBodyOverflow;
        await nextTick();
        if (actionDialogTrigger?.isConnected) actionDialogTrigger.focus();
      }
    });
    function closeActionDialog() {
      if (actionDialogBusy.value) return;
      showCancelBookingModal.value = false;
      showDeleteModal.value = false;
      showDeleteRoomModal.value = false;
      showDeleteBookingModal.value = false;
      showDeleteServiceModal.value = false;
      pendingCancelBooking.value = null;
      bookingCancellationError.value = '';
    }
    function handleActionDialogKeydown(event) {
      if (event.key === 'Escape') {
        event.preventDefault(); event.stopPropagation(); closeActionDialog();
      } else if (event.key === 'Tab') handleRoomDialogKeydown(event);
    }
    watch(staffTab, (newTab) => {
      if (newTab === 'rooms') { rooms.value = []; fetchRooms(); }
      if (newTab === 'services') { services.value = []; fetchServices(); }
    });

    // ── RETURN (all refs/functions exposed to template) ────────────────────────
    return {
      notifications, notificationUnread, notificationsOpen, notificationsBusy, notificationsError, notificationsOlder,
      fetchNotifications, toggleNotifications, closeNotifications, markNotificationsRead, openNotification, notificationDate,
      page, authTab, dashTab, authMsg, authMsgType, authMsgKey, showRoomModal, editingRoom, loading, mobileMenuOpen,
      today, currentUser, token, loginForm, regForm, showLoginPw, showRegPw, showRegConfirmPw, rooms, filters, selectedRoom,
      bookingForm, roomForm, lastBooking, allBookings, features, teamMembers, faqs,
      filteredRooms, bookingNights, bookingTotal, upcomingBookings, pastBookings,
      guestBookingPage, guestBookingPageCount, guestBookingRangeStart, guestBookingRangeEnd, activeGuestBookings, pagedGuestBookings, changeGuestBookingPage,
      guestServicePage, guestServicePageCount, guestServiceRangeStart, guestServiceRangeEnd, pagedGuestServices, changeGuestServicePage,
      navigate, doLogin, doRegister, logout, googleLogin, doForgotPassword, doResetPassword,
      showForgotPassword, forgotEmail, forgotMsg, forgotMsgType,
      showResetPassword, resetPassword, resetPasswordConfirm, resetMsg, resetMsgType, resetFilters, fetchRooms, fetchCurrentUser,
      fetchUserBookings, viewRoom, doBook, cancelBooking, openAddRoom, editRoom, saveRoom,
      deleteRoom, confirmDeleteRoom, showDeleteRoomModal, pendingDeleteRoom,
      updateBookingStatus, fetchAllBookings, services, fetchServices,
      statusLabel, statusClass, availService, showServiceModal, serviceModalData,
      serviceAvails, fetchServiceAvails, deleteServiceAvail, confirmDeleteServiceAvail,
      showDeleteModal, pendingDeleteId, deleteBooking, confirmDeleteBooking,
      showDeleteBookingModal, pendingDeleteBookingId, updateAvailStatus,
      updateServiceStock, servicesLoading,
      toggleService,
      openAddService,
      editService,
      saveService,
      deleteService,
      confirmDeleteService,
      showServiceAdminModal,
      editingService,
      showDeleteServiceModal,
      pendingDeleteService,
      serviceForm,
      triggerUpload,
      removeImage,
      handleFileUpload,
      staffTab, staffBookingSearch, staffBookingStatus, filteredStaffBookings, staffRefreshing, refreshStaffDashboard,
      guestRefreshing, refreshGuestDashboard, formatGuestDate, roomsLoading, roomLoadError,
      roomPhotos, activeRoomPhoto, changeRoomPhoto,
      startRoomPhotoGesture, endRoomPhotoGesture, cancelRoomPhotoGesture,
      closeRoomDialog, handleRoomDialogKeydown,
      roomEditorBusy, roomImageUploads,
      serviceEditorBusy, serviceImageReading, serviceImageError, closeServiceDialog, handleServiceDialogKeydown,
      staffPagination, changeStaffPage,
      bookingReferenceCopied, copyBookingReference,
      showCancelBookingModal, pendingCancelBooking, bookingCancellationBusy, bookingCancellationError, confirmCancelBooking,
      actionDialogBusy, closeActionDialog, handleActionDialogKeydown,
      toasts,
      paymentOptions, paymentBooking, paymentHistory, showPaymentDialog, showWalkInDialog, paymentBusy, paymentError, paymentPhotoReading, paymentForm,
      walkInForm, walkInRoom, walkInTotal, bookingMoney, paymentStatusLabel, paymentDeadline, openPaymentDialog, readPaymentProof, saveBookingPayment,
      openWalkInDialog, saveWalkIn, closePaymentDialogs, paymentDialogKeydown,
      paymentOptionsLoading, paymentOptionsError, fetchPaymentOptions,
      paymentKind, walkInKind,
      lastCounterService, editingServicePaymentMethod, savedServiceCounterChoice, customerPaymentFormVisible, changeServicePaymentMethod, viewServiceRequests,
      paymentProviderLogo,
      chooseServicePhoto, removeServicePhoto, handleServicePhoto,
      showToast,
      // ── reviews ──
      reviews, reviewsAvg, reviewsTotal, reviewForm, reviewHover,
      eligibleBooking, submitReview,
    };
  }
});

__app.mount('#app');
