"""
mil/chat/retrievers — MIL-41.

Retriever pool. Every retriever returns an EvidenceBundle with
source-tagged, verbatim-text items that flow into synthesis.
"""
from mil.chat.retrievers.base import Evidence, EvidenceBundle, Retriever

__all__ = ["Evidence", "EvidenceBundle", "Retriever"]
