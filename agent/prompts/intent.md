---
version: 1.1
---
Classify the client's latest message in a freelance marketplace conversation.

{untrusted_rules}

Intents: question (asks about approach, experience or timeline), negotiation (price or scope), interview_request
(asks for a call or meeting), scam_signal (asks to move off-platform, pay outside, share contact details), other.
If the message asks for a lower rate, extract requested_rate as a number.
