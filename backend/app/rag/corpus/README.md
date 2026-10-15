# About this knowledge base

A small, fictional internal wiki for "Halcyon Robotics", used by the RAG demo. Most
pages are ordinary company documentation. Three pages contain planted indirect
prompt injections, the way a real attacker might hide instructions in a vendor
note, a user-editable wiki page or a customer ticket:

- `vendor-onboarding.md`: an obvious "ignore all previous instructions" payload.
- `wiki-community-tips.md`: a subtle note that tries to pass off a fake expense
  policy and asks the assistant to hide the note.
- `support-ticket-4471.md`: a customer ticket asking the assistant to reveal its
  system prompt and API keys.

The guardrail should quarantine those chunks before they reach the model, while
`it-security-policy.md` (which legitimately talks about passwords) stays usable.
This file itself is not indexed.
