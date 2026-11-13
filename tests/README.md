# Tests

Run commands from the project root.

## Frontend structure

```powershell
node tests/frontend/structure-check.cjs
```

This checks local HTML asset paths, feature-script ordering, and JavaScript syntax without a server or database.

## Backend

Install the root Python requirements and configure `.env`, then run:

```powershell
python -m unittest discover -s tests/backend -p "test_*.py" -v
```

If Python is absent from PATH on this computer:

```powershell
& "$env:LOCALAPPDATA/Programs/Python/Python313/python.exe" -m unittest discover -s tests/backend -p "test_*.py" -v
```

Profile tests mock database calls. They do not change account records.

## Browser features

Start Flask on `http://127.0.0.1:5000`, and use an installed Playwright/Playwright Core module and Microsoft Edge:

```powershell
# Set this only if Playwright is installed outside the project:
$env:PLAYWRIGHT_PATH = "C:/path/to/node_modules/playwright-core"
node tests/frontend/features-smoke.cjs
```

The suite uses mocked localhost APIs and dummy accounts. The separate demo is resolved relative to the test file. See [the verification report](../docs/testing/feature-verification.md) for coverage and live-check limits.
