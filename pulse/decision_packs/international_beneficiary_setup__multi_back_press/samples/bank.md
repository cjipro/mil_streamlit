## international_beneficiary_setup__multi_back_press — Bank altitude

**2026-05-10 to 2026-05-16.** 387 sessions on `international.beneficiary.setup`
showed 5+ back-presses in 108s
(burst median; 81% above baseline, p=0.0004).
First-time intl sender · personal account bears 54% of the affected sessions
(2.3× vs the overall population).

**Decision needed:** corridor_fee_inline_summary — users are back-navigating
to recheck the fee / FX rate they saw on the corridor-select screen.
Pin a persistent inline summary card (corridor, FX rate, estimated arrival,
total fee) at the top of the beneficiary screen so users don't need to
leave it to verify the deal.

**Confidence:** high (band: 0.80–0.89).
