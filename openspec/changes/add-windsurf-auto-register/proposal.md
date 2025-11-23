# Change: Add Windsurf auto registration mode

## Why
Manual interaction for clicking Continue after human verification and entering email verification codes slows down Windsurf batch registration and increases operator workload.

## What Changes
- Add a "全自动注册" button in the GUI to run Windsurf registration in a fully automated mode.
- In auto mode, after human verification succeeds and the Continue button is clickable, automatically click the Continue element `//button[contains(text(), 'Continue')]`.
- In auto mode, automatically paste the retrieved verification code into the OTP input elements matching `input[maxlength='1']`, starting from the first input.
- After each account registration flow finishes, automatically proceed to the next account in the batch without requiring manual start.

## Impact
- Affected specs: `windsurf-auto-register`
- Affected code (likely):
  - Tkinter GUI main window and controls (auto-mode entry point)
  - Flow configuration `flows/windsurf_register.toml`
  - Flow runner / engine logic for post-verification auto-continue and OTP input filling
  - OTP retrieval and integration with GUI/engine
