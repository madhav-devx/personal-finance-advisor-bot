# Personal Finance Advisor Bot

A Flask web app for tracking income and expenses, setting budgets, reaching savings goals and getting
data-driven suggestions. It runs entirely on your own machine with SQLite (no database server, no bank login).

**Features:** registration/login · dashboard with Chart.js charts · income & expense management with filters and search ·
monthly and per-category budgets with 80% / over-budget alerts · savings goals with contributions and projections ·
AI advisor (built-in engine works with no API key; optional external AI with automatic fallback) ·
monthly reports with CSV and PDF export · demo-data generator for four scenarios (salaried, student, freelancer, household).

> Insights are educational and based only on the data you enter. They are not personalised financial, tax or
> investment advice, and no investment returns are promised.

---

## Run it on macOS with VS Code

You need **Python 3.9 or newer** (`python3 --version`). Python 3.11/3.12 from <https://www.python.org/downloads/> or
Homebrew (`brew install python`) is recommended.

1. **Extract** the ZIP (double-click it) and open the `personal-finance-advisor-bot` folder in VS Code
   (*File → Open Folder…*).
2. **Open the terminal** in VS Code (*Terminal → New Terminal*). It opens in the project folder.
3. **Create a virtual environment**
   ```bash
   python3 -m venv .venv
   ```
4. **Activate it** (your prompt will show `(.venv)`)
   ```bash
   source .venv/bin/activate
   ```
   If VS Code asks which interpreter to use, choose the one inside `.venv`.
5. **Install dependencies** (needs an internet connection)
   ```bash
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```
6. **Configure environment variables**
   ```bash
   cp .env.example .env
   ```
   Nothing in `.env` is required for a local run. `SECRET_KEY` may stay blank (a private random key is created in
   `instance/.secret_key`). Set `SECRET_KEY` yourself if you ever share or deploy the app. AI settings are optional (see below).
7. **Initialise the database**
   ```bash
   flask --app run init-db
   ```
   This creates `instance/finance.db`. It is safe to repeat. (`python run.py` also creates missing tables on start.)
8. **Start the app**
   ```bash
   python run.py
   ```
9. **Open** <http://127.0.0.1:5001> in your browser. Click **Get started free**, create an account, then use
   **Profile & settings → Demo data** to load sample data for a scenario.

> **Why port 5001, not 5000?** On recent macOS versions the *AirPlay Receiver* already uses port 5000, which causes
> "403 Forbidden" or "address in use" errors. Change `PORT` in `.env` if you prefer another port.

Stop the server with `Ctrl+C`. Next time, just run steps 4 and 8.

### Optional: create a ready-made demo account
```bash
flask --app run create-demo-user                      # demo@example.com / DemoPass123, salaried scenario
flask --app run create-demo-user --scenario student   # or: freelancer, household
```
Demo records are labelled `[Demo]`, never overwrite existing data, and can be removed from *Profile & settings*.
Use a different `--password` if you ever expose the app beyond your own computer.

### Windows (PowerShell)
```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1        # if blocked: Set-ExecutionPolicy -Scope Process RemoteSigned
python -m pip install --upgrade pip
pip install -r requirements.txt
copy .env.example .env
flask --app run init-db
python run.py
```

---

## Running the tests
```bash
source .venv/bin/activate
pytest
```
Tests use a separate temporary SQLite database for every test and never touch `instance/finance.db`.

---

## Optional AI API integration

The built-in advisor needs no configuration. To get more conversational answers from an external model:

1. Put your key in `.env` (never in source code):
   ```
   AI_PROVIDER=anthropic        # or: openai
   AI_API_KEY=your-key-here
   AI_MODEL=                    # optional; see your provider's docs for current model names
   ```
2. Restart the app, then tick **Allow aggregated figures to be sent to my configured external AI provider** in
   *Profile & settings*. Without this per-user consent **nothing is ever sent**.
3. Only aggregated totals (income, expenses, category totals, budgets, goals) are sent - no name, email or individual
   transactions. If the AI call fails or times out, the built-in advisor answers automatically.

---

## Project layout
```
app/                 Flask package (factory in __init__.py)
  models.py          User, Income, Expense, Budget, SavingsGoal, SavingsContribution
  services.py        Builds the monthly "snapshot" from the database
  calculations.py    Pure helpers (money formatting, month maths, goal progress)
  advisor/engine.py  Built-in recommendation engine (pure Python, no DB)
  advisor/ai_client.py  Optional external AI call (standard library only)
  auth/ dashboard/ income/ expenses/ budgets/ savings/ advisor/ reports/   Blueprints (routes.py)
  demo.py            Demo-data generator / remover
  templates/ static/ Jinja2 templates, CSS, JS
tests/               pytest suite
config.py  run.py    Configuration and entry point
```
Amounts are stored exactly as integer minor units (value × 100) and handled as `Decimal` in Python - no floating-point rounding.

## Security notes
Passwords are hashed with PBKDF2-SHA256 · CSRF protection on all POST forms and the chat API · every query is scoped to the
logged-in user (other users' records return 404) · input validated server-side · CSV exports neutralise spreadsheet
formulas · debug mode is off by default · security headers set · secrets come from environment variables.

## Troubleshooting
| Problem | Fix |
|---|---|
| `command not found: python3` or version < 3.9 | Install Python from python.org or `brew install python`, then recreate `.venv`. |
| `(.venv)` not shown / `pip` installs globally | Re-run `source .venv/bin/activate` in the *same* terminal. |
| `ModuleNotFoundError: flask_sqlalchemy` (or similar) | The venv is not active or step 5 did not finish: activate, then `pip install -r requirements.txt`. |
| `Address already in use` / 403 on port 5000 | Use the default 5001, or set another `PORT` in `.env`; or find the process: `lsof -i :5001`. |
| `no such table` / database errors | Run `flask --app run init-db`. To start fresh, stop the app and delete `instance/finance.db`. |
| Charts or styling missing | Bootstrap/Chart.js load from a CDN - check your internet connection. |
| "Your session may have expired" (400) | Refresh the page and resubmit; sessions/forms expire after 8 hours. |
| `pip` fails building a package | Run `python -m pip install --upgrade pip` and retry; make sure you are on Python 3.9+. |

## Limitations
- No login rate-limiting, e-mail verification or password-reset flow (it is designed for local/personal use).
- Bootstrap and Chart.js are loaded from a CDN, so the UI needs internet access.
- The PDF uses built-in fonts, so the rupee sign is printed as "Rs." and non-Latin text is not supported in PDFs.
- Budget/advice rules are simple, transparent heuristics - not professional financial advice.
