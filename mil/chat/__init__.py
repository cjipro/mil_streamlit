"""
mil/chat — Ask CJI Pro v1.

Conversational intelligence layer over the MIL public-signal vault.
Scope is MIL-only: app reviews, DownDetector, City A.M., Reddit, YouTube.
Any internal-telemetry question triggers the logic_probe refusal class.

Pipeline:
    intent.classify(query)
        -> retrievers.{bm25, embedding, sql, structured}.retrieve()
        -> synthesis.synthesise(EvidenceBundle)
        -> verifier.verify()
        -> audit.log()

Tickets: MIL-39 (tracker) through MIL-48 (alpha onboarding).
"""
