# Customer payment receipts

Open a room reservation's payment details or a service request's payment history in My Bookings, then choose **View receipt**. It appears only when the authenticated details endpoint returns at least one positive verified payment. Payment submissions awaiting review do not produce a receipt. Staff can also view receipts through Payments.

The receipt shows the customer, reservation/request reference, room or service, stay dates and selected times or service quantity, verified payment IDs, dates in Philippine time, methods, references, total charges, amounts received, and the recorded remaining balance in pesos. A deposit produces a partial-payment receipt. This summarizes payment records; it is not a tax invoice and no tax registration details or official invoice numbers are invented.

Choose **Print / Save as PDF**, then use the device's print or PDF destination. Mobile availability of Save as PDF depends on the browser's print/share interface. Only the receipt is printed. The receipt is not automatically emailed or stored on the device.

Data comes from the existing authenticated room/service details APIs. Room details now include the actual customer and room names after ownership verification. No schema change is needed. Text is rendered by Vue escaping, and the receipt does not include uploaded payment screenshots or account credentials. Signing out clears the receipt view. Existing verified-payment recording and ownership rules remain unchanged.

Verification: 48 backend tests pass, including owner access, denial for another guest, and signed-out access. `tests/frontend/receipts-smoke.cjs` checks room deposits, fully paid services, mobile controls, escaped text, print isolation, generated PDF bytes, and absence of a receipt for unpaid/unverified records, using mocked APIs and no live database writes.

Start Flask on port 5000 and run `node tests/frontend/receipts-smoke.cjs` with `PLAYWRIGHT_PATH` pointing to an installed Playwright/Playwright Core module. Microsoft Edge is used by the test.

Deploy the updated Flask and public files to make the feature available on the hosted website.
