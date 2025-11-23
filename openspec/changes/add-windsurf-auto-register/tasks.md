## 1. GUI & Mode Wiring
- [ ] 1.1 Add a "全自动注册" button in the GUI for Windsurf registration.
- [ ] 1.2 Wire the button to start the Windsurf registration flow in an auto registration mode (e.g. a flag on the task/run).

## 2. Flow & Engine Behavior
- [ ] 2.1 Decide whether to reuse `flows/windsurf_register.toml` or add a dedicated auto-mode flow file; ensure configuration stays simple.
- [ ] 2.2 Implement behavior so that after human verification succeeds, the engine automatically clicks the Continue element `//button[contains(text(), 'Continue')]` when it is present and clickable, without changing how verification itself is solved.
- [ ] 2.3 Implement auto filling of the email verification code into OTP inputs by locating elements that match `input[maxlength='1']` and pasting the complete verification code string into the first such input element (for Windsurf, the page will automatically distribute the code across 6 inputs and submit), designing the mechanism so it can be reused by other flows with similar patterns.
- [ ] 2.4 Ensure that in auto registration mode, once one account's registration flow reaches a terminal state (success or failure), the engine automatically starts the next account's registration flow until all accounts are processed or the operator stops the run.

## 3. Testing & Validation
- [ ] 3.1 Add or update automated tests for the flow runner to cover auto-continue and auto OTP filling behavior (as feasible).
- [ ] 3.2 Manually validate a Windsurf batch run in auto registration mode (including captcha success path, Continue auto-click, OTP auto fill, and automatic progression across multiple accounts).
