# Project Context

## Purpose
ConfigFlowRegister is a configuration-driven batch registration engine for websites.
Flows are defined in TOML (URLs, selectors, steps, variables) instead of hard-coded
Python scripts, so that registration logic can be changed or extended by editing
configuration files. The current primary use case is registering accounts for
Windsurf, but the architecture is generic enough to support other sites by
writing new flow TOML files.

The project exposes both a CLI and a Tkinter GUI. The CLI is suited for
non-interactive batch runs, while the GUI focuses on user interaction during
CAPTCHA / human verification and visual progress monitoring. The tool supports
packaging into standalone executables with PyInstaller.

## Tech Stack

- Python 3.x runtime (desktop environments; Windows as primary target)
- Selenium 4 for browser automation
- undetected-chromedriver for anti-detection Chrome/Chromium integration
- Tkinter for the desktop GUI
- TOML (via `tomli` for older Python versions) for flow configuration
- Custom logging utilities in `src/utils/logger.py`
- PyInstaller for building distributable executables (CLI and GUI variants)

## Project Conventions

### Code Style

- Python modules generally follow PEP 8 style:
  - `snake_case` for functions and variables
  - `PascalCase` for classes
  - Constants in `UPPER_SNAKE_CASE` where applicable
- Type hints are used throughout (`typing` and `from __future__ import annotations`).
- Data-rich structures are implemented via `@dataclass` (for configuration,
  accounts, tasks, statistics, etc.).
- Logging goes through the shared logger utilities instead of printing directly;
  logs are used consistently across CLI, engine, data manager and GUI.
- User-facing messages (especially errors and CLI/GUI texts) are written in
  Chinese, while internal identifiers and code remain English.

### Architecture Patterns

- **Configuration-driven engine**
  - Flows are defined as TOML files under `flows/` with sections such as:
    - `[flow]` (metadata like name, start URL, timeout)
    - `[selectors.*]` (named element locators)
    - `[[steps]]` (ordered actions: `navigate`, `type`, `click`, `pause_for_manual`, etc.).
  - The engine resolves variables like `{config.*}`, `{account.*}`, `{env.*}` and
    `{flow.*}` when executing steps.

- **Layered structure**
  - `src/engine/`: flow loading, validation, variable resolution, execution
    and actions.
  - `src/browser/`: `BrowserProvider` encapsulates starting/cleaning up
    undetected-chromedriver instances and anti-detection behavior.
  - `src/data/`: configuration dataclasses, account and task models,
    DataManager (account generation, persistence, CSV export, task checkpointing).
  - `src/utils/`: configuration loading (`config` and `config_loader`),
    path handling, logging, custom exceptions, email encryption and OTP fetcher.
  - `src/gui/`: Tkinter GUI (`MainWindow`) that orchestrates tasks, progress,
    manual steps and OTP display.
  - `src/cli.py`: CLI entrypoint wrapping configuration loading, flow
    selection, account generation and batch execution.

- **Packaging compatibility**
  - Import patterns deliberately support both "src package" layout and
    PyInstaller-frozen layouts using multiple `try/except` fallbacks.
  - `configflow.spec` and `configflow_gui.spec` declare hidden imports for the
    engine, browser, utils, data and external libraries so that executables work
    without missing modules.
  - Paths are resolved differently in frozen mode (using `sys.frozen` and
    `sys._MEIPASS`) to locate resources like `config.json` and flow files.

### Testing Strategy

- Tests use `pytest` and live under `tests/`.
- `pytest.ini` enforces coverage on core engine and utils modules:
  - `--cov=src/engine --cov=src/utils --cov-fail-under=80`
- There is a mix of unit tests and integration-style tests, for example:
  - Engine loading and variable resolution (`test_flow_loader_and_variable.py`)
  - Flow execution and runner behavior (`test_flow_engine_runner.py`)
  - Actions and runner behavior (`test_actions_and_runner.py`)
  - Configuration loading and path utilities (`test_config_loader.py`,
    `test_utils_config_and_path.py`)
  - Email crypto and OTP fetching (`test_email_crypto_unit.py`,
    `test_email_otp_unit.py`, `test_email_otp_integration.py`)
  - CLI behavior (`test_cli.py`).
- New code paths in engine/utils should normally come with corresponding tests,
  keeping overall coverage at or above the configured threshold.

### Git Workflow

- This repository does not strictly enforce a particular Git workflow in code,
  but the following conventions are assumed when reasoning about changes:
  - There is a primary long-lived branch used as the integration/main branch.
  - Feature work and refactors can be done in topic branches and merged back
    via pull requests.
  - Commit messages should clearly describe intent (e.g. "engine: improve flow
    validation" or "gui: fix OTP display bug"), but there is no hard requirement
    to follow a specific commit convention.

## Domain Context

- The main domain is **website account registration automation**.
- The current primary flow targets Windsurf account registration at
  `https://windsurf.com/account/register`, but the engine is intentionally
  generic.
- Accounts are typically email-based and follow patterns like
  `<random15>@yaoshangxian.top` by default. The domain and registration
  parameters can be overridden in `config.json` (and corresponding
  `Configuration` dataclasses).
- Names (first/last) are auto-generated from random letters and capitalized;
  they no longer depend on parsing the email local-part.
- Registration tasks can be persisted and resumed. Each task keeps statistics
  (total, completed, success, failed, success rate, progress percentage) and a
  `last_processed_id` for resuming.
- The GUI is designed for semi-automatic flows where human intervention is
  expected (e.g. manual CAPTCHA solving or challenge pages). The engine can
  pause with `pause_for_manual` steps and let the GUI user continue.
- The system integrates with an OTP mailbox to automatically retrieve email
  verification codes, display them in the GUI and copy them to clipboard.

## Important Constraints

- **Technical constraints**
  - Requires a desktop environment with a supported browser (Chrome/Chromium)
    installed; headless mode is technically supported but discouraged for
    flows involving heavy anti-bot/captcha challenges.
  - The project intentionally avoids heavy dependencies such as NumPy, pandas,
    matplotlib or PIL to keep PyInstaller bundles lightweight (they are
    explicitly excluded in the `.spec` files).
  - Data (tasks, CSV exports, history emails) is stored relative to the
    application working directory (`data/`, `registered_emails.txt`).

- **Security & privacy constraints**
  - Email credentials in `config.json` should use encrypted values in the form
    `enc:...`, generated by `src.utils.email_crypto.encrypt_email_secret`.
  - The decryption secret key is provided at runtime via the
    `CONFIGFLOW_EMAIL_SECRET_KEY` environment variable.
  - Decrypted credentials are held only in memory; the project avoids writing
    plaintext secrets back to disk or logs.

- **Operational considerations**
  - The tool is meant to be run by an operator who understands the target
    website's terms of service and anti-bot policies.
  - Excessive concurrency or aggressive retry strategies can trigger anti-abuse
    mechanisms; by default the configuration is conservative (limited retries,
    intervals between accounts).

## External Dependencies

- **Web targets**
  - Example flow targets `https://windsurf.com/account/register`.
  - Additional sites can be supported by writing new TOML flows under `flows/`.

- **Email infrastructure**
  - OTP mailbox (e.g. QQ Mail) accessible via IMAP. Defaults:
    - Server: `imap.qq.com`
    - Port: `993`
  - Subject and content filtering is used to match verification codes for the
    currently processed account.

- **System/software dependencies**
  - Google Chrome or compatible Chromium browser installed on the host.
  - Network access to both the target websites and the configured IMAP server.
