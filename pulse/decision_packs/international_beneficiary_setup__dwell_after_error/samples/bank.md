## international_beneficiary_setup__dwell_after_error — Bank altitude

**2026-05-10 to 2026-05-16.** 924 sessions on `international.beneficiary.setup`
stalled after an inline validation error
(62% above baseline, p=0.001).
First-time international sender · non-English language preference bears 47% of the affected sessions
(2.4× vs the overall population).

**Decision needed:** swift_lookup_affordance + latin_char_helper on the
beneficiary-name and SWIFT/BIC fields — surface a bank-lookup widget so
users don't have to know the BIC, and pre-translate the Latin-character
requirement into the user's chosen UI language with a transliteration helper.

**Confidence:** high (band: 0.81–0.90).
