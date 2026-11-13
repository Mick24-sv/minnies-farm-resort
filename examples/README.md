# Standalone examples

`stillwell-booking/dist/index.html` contains the session-booking page and animated delete-confirmation demo. Open it directly in a browser.

It is independent of the resort's Flask/Vue application. It does not create real reservations or delete project files. Its existing nested Git history and Sites configuration are preserved inside `stillwell-booking/`.

The resort deployment excludes this directory. Production frontend assets belong in `public/`, not in this directory.
