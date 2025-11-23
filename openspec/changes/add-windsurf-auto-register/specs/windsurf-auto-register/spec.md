## ADDED Requirements

### Requirement: Windsurf auto registration mode
The system SHALL provide a "全自动注册" (fully automatic registration) mode for Windsurf account registration that minimizes manual interaction during batch runs.

#### Scenario: User starts auto registration from GUI
- **WHEN** the operator clicks the "全自动注册" button in the GUI for the Windsurf registration flow
- **THEN** the system starts a batch registration run in auto registration mode for the configured number of accounts

### Requirement: Auto-continue after human verification
The system SHALL, in auto registration mode, automatically click the Continue button after human verification succeeds, without changing how the verification itself is solved.

#### Scenario: Continue button becomes clickable after verification
- **GIVEN** the Windsurf registration flow has reached a human verification step
- **AND** the verification has been solved successfully (manually or automatically)
- **AND** the Continue button `//button[contains(text(), 'Continue')]` is present and clickable
- **WHEN** the flow is running in auto registration mode
- **THEN** the system automatically clicks the Continue button once
- **AND** the flow proceeds to the next step in the registration process

### Requirement: Auto fill OTP code via first digit input
The system SHALL, in auto registration mode, automatically fill the email verification code into the OTP input fields by pasting the full code into the first digit input when they are present.

#### Scenario: OTP inputs are available
- **GIVEN** the Windsurf verification page shows OTP input elements matching `input[maxlength='1']`
- **AND** the system has successfully retrieved the verification code for the current account
- **WHEN** the flow is running in auto registration mode
- **THEN** the system pastes the complete verification code string into the first such input element
- **AND** it relies on the page behavior (for example, Windsurf automatically distributing the code across 6 inputs and submitting) to handle splitting and submission

### Requirement: Auto-advance to next account
The system SHALL, in auto registration mode, automatically continue with the next account after the current registration flow is completed or reaches a terminal state.

#### Scenario: One registration finishes
- **GIVEN** a batch of accounts is being processed for Windsurf registration
- **AND** the current account's registration flow has reached a success or failure terminal state
- **WHEN** the flow is running in auto registration mode
- **THEN** the system automatically begins the registration flow for the next pending account
- **UNTIL** all accounts are processed or the operator stops the run
