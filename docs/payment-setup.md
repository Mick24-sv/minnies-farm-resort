# Manual deposits and counter payments

## Required setup

1. Run [the booking/payment migration](../database/migrations/20261025_booking_payments.sql) in the Supabase SQL Editor **before restarting or deploying this version**. It adds payment fields, a payment ledger, and transactional functions. Existing bookings remain unpaid in the application until staff record verified receipts; do not assume old bookings were never paid in real life.
2. The supplied MariBank QR is bundled at `public/assets/images/maribank-qr.png` and is available for room deposits and service payments. The original image is displayed without cropping and can be downloaded for payment on the same phone.

GCash remains unavailable until its verified QR is ready. Add the original image under `public/assets/images/` and configure:

```env
PAYMENT_GCASH_NAME=
PAYMENT_GCASH_QR_URL=/assets/images/gcash-qr.png
```

Keep the GCash QR URL empty until its image is supplied and verified. Only local PNG, JPG, JPEG, or WebP paths under `/assets/images/` are accepted. Redeploy after changing hosted environment settings. Local Flask debug mode rereads payment settings from `.env`.

Raw account numbers are no longer returned by the payment-options API or displayed in payment instructions. Legacy `PAYMENT_GCASH_NUMBER` and `PAYMENT_BANK_ACCOUNT_NUMBER` settings are unused and may be removed. QR codes still carry payment routing information, and banking apps can display the recipient name. Check the recipient before paying.

## Online reservations

- The server calculates nights, current room rate, the 10% resort fee, and a **50% deposit**.
- New reservations are pending/unpaid and hold the room for **3 hours**. Confirmation displays the exact deadline in Philippine time.
- Customers transfer funds outside the app, then submit a transaction reference and an optional JPG/PNG/WebP screenshot (2 MB maximum).
- Submission changes review status only. It never counts as payment or confirms the booking. A submission made before the deadline retains its hold while staff review it.
- Staff open **Dashboard → Bookings → Payments / Review deposit**, check the receiving account, enter the actual amount received and reference, and acknowledge verification. Recording the required deposit confirms the reservation. The remaining balance is collected at check-in using the same Payments form.
- Staff can reject an unverified submission with a reason. Rejection does not extend the original deadline. If the deadline has passed, the unpaid hold is cancelled.
- Expiration is enforced transactionally when bookings are read or created, or payment is submitted/recorded. No background scheduler is required for rooms to become bookable after expiry.

## Walk-ins

Use **Dashboard → Bookings → Add walk-in**. Enter the guest, room, dates, and guest count. Collect the displayed full amount at the counter. Choose cash, GCash, or bank transfer and acknowledge actual receipt. The server rechecks the current rate and availability. The booking and full-payment ledger entry are saved in one transaction. The confirmation shows paid status, amount received, and zero balance.

## Service payments

Run `database/migrations/20261025_service_payments.sql` **after** the room-payment migration. Service requests require **100% payment**, using the same receiving accounts and 3-hour submission window. No room resort fee is added to service prices.

Customers use **Services → Request & pay** and submit the transfer reference/screenshot. Staff use **Dashboard → Services → Service Requests → Payments** to verify the receiving account and record the full amount. Submitting evidence alone does not confirm the request. Staff can also choose **Add walk-in service**, collect the displayed full price, and save a paid request in one transaction. Historical service requests receive no fabricated receipts.

Finite stock is reserved when a request is created and released once on cancellation or unpaid expiry. A timely payment submission keeps its stock while staff review it. Completed services consume stock; staff can replenish inventory when appropriate. Service stock is not a date/time scheduling system.

Room and service payments have separate ledgers. A shared transfer-reference registry prevents recording the same bank/GCash transfer in both ledgers. Cash payments use independent retry keys. Cancellation retains payment history and does not issue a refund.

## Records and verification

### Service visitors paying at the counter

Run `database/migrations/20261025_service_counter.sql` after the service-payment migration. A customer can request an entrance ticket or another service without booking a room/cottage, then choose **Pay at the counter** in payment details. No screenshot or transaction reference is requested for this choice. The request remains pending/unpaid and shows its MFS reference and the original 3-hour payment deadline; selecting counter payment never extends that deadline or reserves stock indefinitely.

The cashier locates the service request and records the full verified payment using **Services → Service Requests → Payments → Cash at counter**. Only that recorded receipt changes the request to paid/confirmed. Walk-in visitors without an online account can still go directly to the cashier, who uses **Add walk-in service**. Online receiving-account configuration is not required for service requests that will be paid at the counter.

An existing transfer submission under review cannot be replaced with a counter choice until staff resolve it. Customers can instead submit a transfer after choosing counter payment; its method replaces the choice and still requires staff verification.

Payment and reservation status are separate. Booking requests and recorded payments use retry keys. Transfer references cannot be recorded twice for the same payment method. Payments cannot exceed the balance, and stays cannot be marked completed with an outstanding balance. Concurrent requests for the same room are serialized by a database room lock.

Cancelled bookings and payment history are retained. Cancellation does **not** issue a refund. Refund decisions and transfers remain a manual staff process; recorded receipts are displayed before refunds. Existing legacy reservations are not retroactively assigned fake receipts or new deposit deadlines.

The migration has to be applied to the real database separately. Local tests use mocked network/database responses; they do not prove that the migration ran or that real GCash/bank funds arrived.
