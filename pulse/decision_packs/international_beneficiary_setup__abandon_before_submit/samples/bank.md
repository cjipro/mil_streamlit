## international_beneficiary_setup__abandon_before_submit — Bank altitude

**2026-05-10 to 2026-05-16.** 718 high-intent sessions abandoned
`international.beneficiary.setup` before initiating payment
(44% above baseline, p=0.0006).
Final-focused field: `intermediary_bank_swift` in 39% of abandonments.
Age 35–54 · personal account · high-risk corridor bears 38% of the affected sessions
(2.0× vs the overall population).

**Decision needed:** intermediary_bank_auto_suggest +
sanctions_disclosure_clarity — the intermediary-bank field is the modal
abandonment point and almost always optional in our routing; default it to
"none required, auto-select if needed" and remove it from the visible review
screen. Pair with a plain-English sanctions disclosure ("we'll screen this
payment against UK and EU sanctions lists; this is normal and takes ~10s")
so the high-risk corridor cohort doesn't bail thinking they did something wrong.

**Estimated opportunity cost:** £840k/week in foregone fee + FX-margin revenue
(assuming historical fee + FX-margin conversion rates apply to recovered sessions).

**Confidence:** medium-high (band: 0.76–0.87).
