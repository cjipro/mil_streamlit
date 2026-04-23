"""
mil/command/ask_page.py — MIL-45.

Ask CJI Pro — two-column Streamlit page. Left: the query box, examples,
and a short history. Right: the rendered answer (prose + citations + chart
+ verbatim quotes + verifier status).

Exposed as `render_ask_page()` — wired into app/pages/08_ask_cji_pro.py.
"""
from __future__ import annotations

import html

import streamlit as st

from mil.chat import charts, feedback
from mil.chat.pipeline import ask


_EXAMPLE_QUERIES = [
    "show me recent Barclays reviews about login failures",
    "rank the UK banks on app crashes in the last 30 days",
    "how has Monzo sentiment trended over the last 30 days",
    "what does CHRONICLE say about TSB 2018",
    "compare Barclays and NatWest on login issues in the last 30 days",
]


def _format_refusal(resp) -> None:
    st.error(resp.answer)
    st.caption(f"refusal_class = `{resp.refusal}` · trace = `{resp.trace_id}`")


def _render_answer_block(resp) -> None:
    conf = (resp.confidence or "unknown").upper()
    conf_color = {
        "EVIDENCED":   "#1AB0A1",
        "DIRECTIONAL": "#FF8A00",
        "UNKNOWN":     "#CC3333",
    }.get(conf, "#90B0C0")

    st.markdown(
        f"<div style='font-size:13px;letter-spacing:0.8px;color:{conf_color};"
        f"font-weight:600;margin-bottom:10px'>"
        f"CONFIDENCE: {conf}</div>",
        unsafe_allow_html=True,
    )
    st.markdown(resp.answer)

    if resp.chart_hint and resp.chart_hint in charts.TEMPLATES:
        _render_chart_from_evidence(resp)

    if resp.quotes:
        st.markdown("#### Verbatim quotes")
        for q in resp.quotes:
            st.markdown(charts.quote(q), unsafe_allow_html=True)

    if resp.citations:
        st.markdown("#### Citations")
        for ev in resp.evidence:
            if ev["id"] not in resp.citations:
                continue
            st.markdown(
                f"**`{ev['id']}`** · {ev['source']} · score {ev['score']:.2f}  \n"
                f"<span style='color:#90B0C0;font-size:13px'>"
                f"{html.escape(ev['text'][:240])}…</span>",
                unsafe_allow_html=True,
            )

    if resp.verifier_violations:
        st.warning(
            "Verifier flagged:\n\n- "
            + "\n- ".join(resp.verifier_violations)
        )

    st.caption(
        f"intent `{resp.intent}` · retrievers {resp.retrievers_used} · "
        f"{len(resp.evidence)} evidence · {resp.latency_ms} ms"
        + (" · cached" if resp.cache_hit else "")
        + f" · model `{resp.model_used}`"
        + f" · trace `{resp.trace_id}`"
    )


def _render_chart_from_evidence(resp) -> None:
    """Best-effort chart rendering from evidence metadata for the hint."""
    hint = resp.chart_hint
    if hint == "peer_rank":
        items = []
        for ev in resp.evidence:
            meta = ev["metadata"]
            if meta.get("intent") != "peer_rank":
                continue
            label = meta.get("competitor")
            rating = meta.get("avg_rating")
            if label and rating is not None:
                items.append((str(label), float(rating)))
        if items:
            st.plotly_chart(charts.peer_rank(items, y_label="avg rating (lower = worse)"),
                            use_container_width=True)
    elif hint == "compare":
        values = {}
        for ev in resp.evidence:
            meta = ev["metadata"]
            if meta.get("intent") != "compare":
                continue
            label = meta.get("competitor")
            rating = meta.get("avg_rating")
            if label and rating is not None:
                values[str(label)] = float(rating)
        if values:
            st.plotly_chart(charts.compare(values, y_label="avg rating"),
                            use_container_width=True)
    elif hint == "trend":
        series: dict[str, list[tuple[str, float]]] = {}
        for ev in resp.evidence:
            meta = ev["metadata"]
            if meta.get("intent") != "trend":
                continue
            label = meta.get("competitor") or "series"
            date = meta.get("date")
            rating = meta.get("avg_rating")
            if date is None or rating is None:
                continue
            series.setdefault(str(label), []).append((str(date), float(rating)))
        for name in series:
            series[name].sort(key=lambda t: t[0])
        if series:
            st.plotly_chart(charts.trend(series, y_label="avg rating"),
                            use_container_width=True)


def render_ask_page() -> None:
    st.title("Ask CJI Pro")
    st.caption("Conversational intelligence over public UK banking market signals.")

    if "ask_history" not in st.session_state:
        st.session_state["ask_history"] = []  # list of AskResponse dicts

    left, right = st.columns([1, 2], gap="large")

    with left:
        st.markdown("### Ask")
        query = st.text_area(
            "Your question",
            key="ask_query",
            height=120,
            placeholder="e.g. rank the UK banks on app crashes in the last 30 days",
        )
        deep = st.checkbox("Deep reasoning (Opus)", value=False,
                           help="Routes synthesis to ask_synthesis_deep. Slower, costlier.")
        go = st.button("Ask", use_container_width=True, type="primary")

        st.markdown("### Examples")
        for example in _EXAMPLE_QUERIES:
            if st.button(example, key=f"ex_{hash(example)}", use_container_width=True):
                st.session_state["ask_query"] = example
                query = example
                go = True

        if st.session_state["ask_history"]:
            st.markdown("### History")
            for i, prior in enumerate(reversed(st.session_state["ask_history"][-8:])):
                label = f"{prior['intent']} · {prior['confidence']}"
                st.caption(f"**{label}**  \n_{prior['query'][:80]}_")

    with right:
        if go and query.strip():
            with st.spinner("Retrieving evidence + synthesising…"):
                resp = ask(query, deep=deep)
            st.session_state["ask_history"].append({
                "query": query, "intent": resp.intent,
                "confidence": resp.confidence, "trace_id": resp.trace_id,
            })

            if resp.refusal:
                _format_refusal(resp)
            else:
                _render_answer_block(resp)

            col_up, col_dn, col_note = st.columns([1, 1, 4])
            with col_up:
                if st.button("👍", key=f"up_{resp.trace_id}"):
                    feedback.log(feedback.FeedbackEntry(
                        trace_id=resp.trace_id, verdict="up"))
                    st.toast("Feedback recorded.")
            with col_dn:
                if st.button("👎", key=f"dn_{resp.trace_id}"):
                    feedback.log(feedback.FeedbackEntry(
                        trace_id=resp.trace_id, verdict="down"))
                    st.toast("Feedback recorded.")
            with col_note:
                note = st.text_input("Note (optional)", key=f"note_{resp.trace_id}")
                if note:
                    feedback.log(feedback.FeedbackEntry(
                        trace_id=resp.trace_id, verdict="down", note=note))
        else:
            st.markdown(
                "<div style='color:#90B0C0;padding:40px;text-align:center'>"
                "Ask a question about public UK banking signals. "
                "Every claim will be cited back to evidence in the vault."
                "</div>",
                unsafe_allow_html=True,
            )
