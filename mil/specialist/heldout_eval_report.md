# MIL Specialist — Held-out Evaluation Report

- **Generated**: 2026-04-19T22:50:04.306180+00:00
- **Samples**: 30  (seed=20260419)
- **Haiku threshold**: 90% on P0 and P1
- **Uplift threshold**: +5.0pp over baseline on P0 or P1

## Summary

| Model | Overall | P0 | P1 | P2 |
|---|---:|---:|---:|---:|
| **Haiku** (ground truth) | 1.000 | 1.000 (12) | 1.000 (3) | 1.000 (15) |
| **qwen3:14b** baseline | 93.3% | 83.3% | 100.0% | 100.0% |
| **qwen3-mil-v1-4b** specialist | 83.3% | 75.0% | 100.0% | 86.7% |

## Gate
- Specialist ≥ 90% on P0: **FAIL** (75.0%)
- Specialist ≥ 90% on P1: **PASS** (100.0%)
- P0 uplift vs qwen3:14b: **-8.3pp**
- P1 uplift vs qwen3:14b: **+0.0pp**

## Decision: **KEEP**

Do not promote. Investigate specialist failures on P0/P1 samples where haiku and specialist disagree; consider retraining with additional pairs covering the missed patterns.

## Per-record detail

| # | Source | Haiku | Baseline | Specialist | Review snippet |
|---|---|---|---|---|---|
| 1 | google_play/natwest | P0 | P1 ✗ | P0 ✓ | Every single time I try to make a purchase, this useless app disconnects from th |
| 2 | app_store/monzo | P0 | P0 ✓ | P0 ✓ | Really want to get Monzo as I’ve heard many great reviews however I’ve been left |
| 3 | google_play/barclays | P2 | P2 ✓ | P2 ✓ | Very useful to easily monitor all my accounts. |
| 4 | google_play/revolut | P0 | P0 ✓ | P0 ✓ | My account was suddenly closed because it had been in the negative balance for a |
| 5 | app_store/natwest | P2 | P2 ✓ | P2 ✓ | I find this app really easy to use being a pensioner thank you |
| 6 | google_play/barclays | P2 | P2 ✓ | P2 ✓ | I never have a problem with this app. Barclays are always thorough with anything |
| 7 | app_store/revolut | P2 | P2 ✓ | P2 ✓ | everything and more all in one place. |
| 8 | google_play/revolut | P0 | P0 ✓ | P0 ✓ | I haven't been able to open the app ever since they started requiring play integ |
| 9 | google_play/revolut | P2 | P2 ✓ | P2 ✓ | This app is excellent. I consistently find the most competitive travel rates her |
| 10 | google_play/revolut | P0 | P0 ✓ | P0 ✓ | After latest update I'm unable to use the app. crashes immediately after trying  |
| 11 | youtube/revolut | P2 | P2 ✓ | P0 ✗ | All banks are scam and revolt is truth |
| 12 | google_play/natwest | P1 | P1 ✓ | P1 ✓ | Really frustrating, something has changed resulting in multiple failed online pu |
| 13 | app_store/monzo | P0 | P1 ✗ | P1 ✗ | i tried to log in on my iPad so i could purchase something and it logged out on  |
| 14 | app_store/monzo | P0 | P0 ✓ | P1 ✗ | Transferred devices recently and now won’t even send me a link to log in to my a |
| 15 | youtube/barclays | P2 | P2 ✓ | P2 ✓ | How does this video ONLY have 5 likes and 54 views? |
| 16 | google_play/hsbc | P0 | P0 ✓ | P0 ✓ | still unable to get into my account on my laptop please get this sorted out or w |
| 17 | youtube/barclays | P0 | P0 ✓ | P0 ✓ | No heating ,no food , and now because of barclys im overdrawn .  If i had come o |
| 18 | google_play/revolut | P0 | P0 ✓ | P0 ✓ | shocking I used it to transfer money to my wife's revolut account 14/3 the funds |
| 19 | app_store/lloyds | P2 | P2 ✓ | P2 ✓ | Great App  LLYODS BANK ***** GREAT MAHESWARARAJAH APP |
| 20 | google_play/revolut | P2 | P2 ✓ | P2 ✓ | used always when traveling, easy bill splitting |
| 21 | reddit/monzo | P2 | P2 ✓ | P2 ✓ | Guys i just made £20 literally for signing up to monzo and using the card once t |
| 22 | google_play/revolut | P0 | P0 ✓ | P1 ✗ | For refusing to take the CFD test they block me for 3 days. I don't even own and |
| 23 | google_play/barclays | P1 | P1 ✓ | P1 ✓ | Use to be a good app. Since the most recent update, I have to register every tim |
| 24 | google_play/barclays | P2 | P2 ✓ | P2 ✓ | very easy to use, great app. Very careful when transferring money. Well done Bar |
| 25 | google_play/natwest | P0 | P0 ✓ | P0 ✓ | the app won't let me transfer my money between accounts |
| 26 | google_play/natwest | P1 | P1 ✓ | P1 ✓ | login too complicated, takes me ages to log in to get my statement. |
| 27 | app_store/revolut | P2 | P2 ✓ | P0 ✗ | Love this financing app over all the other bloated apps , really smooth and clea |
| 28 | google_play/barclays | P2 | P2 ✓ | P2 ✓ | easy to use. I can find everything that I need |
| 29 | google_play/revolut | P2 | P2 ✓ | P2 ✓ | Revolut feels like a modern banking app. I like tracking my spending and managin |
| 30 | app_store/monzo | P2 | P2 ✓ | P2 ✓ | The best bank I’ve ever dealt with. |