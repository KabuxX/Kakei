# Agent Chat send feedback — 2026-10-03

## Implemented behavior

- Sending immediately displays the user's bubble and clears the composer, including while a new conversation is still being created.
- An accessible status with three animated dots appears below the message during generation. Receipt upload and proposal operations retain their separate composer feedback.
- After the response and refreshed conversation arrive, the status disappears and the persisted answer and review cards appear.
- Failed sends keep the user bubble and restore the text and attachment. Retrying unchanged content uses the same client message ID; persisted and optimistic messages are reconciled by that ID.
- A conversation-list refresh error after successful generation does not mark the message as failed or invite duplicate submission.
- The current response scrolls into view. Reduced-motion preference disables the dots' animation while keeping the status readable.

## Verification

- Red/green: three new interaction tests initially failed against the previous implementation, then passed.
- Full frontend suite: 95 passed.
- Browser suite: 17 passed using disposable SQLite and the existing deterministic agent fixture.
- New browser test holds conversation creation and message requests separately, verifies the user message before either finishes, inspects loading on desktop/phone, checks reduced motion, simulates a lost response after server completion, and verifies retry payload identity plus exactly two persisted user messages for two distinct sends.
- Production build passed with an empty Mapbox build token. Existing large Mapbox bundle warning remains.
- `git diff --check` passed.
- Desktop 1440×900 and phone 375×812 screenshots inspected: both show the user bubble followed by processing status, with the composer remaining visible and no horizontal overflow. Existing layout test also covers phone landscape.
- No backend changes; no live AI calls or writes to the user's transaction data were needed. Screenshots use test data. Physical-device testing was not performed.

[Desktop](desktop.png) · [Phone](phone.png)
