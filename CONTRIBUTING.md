# Contributing

Install Python 3.11+ and a Node version supported by frontend/package.json, then run the setup script for your platform.

Activate the project virtual environment before the commands below (`.venv\Scripts\Activate.ps1` on Windows; `. .venv/bin/activate` on Linux/macOS).

Before proposing a change:

```sh
python -m pip install -e './backend[test]'
python -m pytest backend/tests -q
npm ci --prefix frontend
npm test --prefix frontend
npm run build --prefix frontend
python scripts/check_release.py
```

Use isolated fixtures for default tests. Online academic API tests are opt-in and must never report invented evidence. Add regression coverage for identity conflicts, failure states and any file/security boundary affected by a change. Do not include keys, local config, task databases, paper PDFs or generated audit output in commits. Keep original user files unchanged.

This project currently supports installation from a source checkout. A standalone backend wheel does not include the React application; it is not the supported desktop distribution.
