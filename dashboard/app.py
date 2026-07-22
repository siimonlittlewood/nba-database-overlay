import pandas as pd
import requests
import streamlit as st

from db.config import get_settings

st.set_page_config(page_title="NBA Stats Agent", layout="wide")


def _check_password() -> bool:
    """No-op if DASHBOARD_PASSWORD is unset (local dev). Set it before
    deploying publicly -- every question here costs real Anthropic API
    usage, so an open deployment is an open tab."""
    required = get_settings().dashboard_password
    if not required:
        return True
    if st.session_state.get("password_correct"):
        return True

    def _on_submit():
        st.session_state["password_correct"] = st.session_state["password_input"] == required
        del st.session_state["password_input"]

    st.text_input("Password", type="password", on_change=_on_submit, key="password_input")
    if st.session_state.get("password_correct") is False:
        st.error("Incorrect password.")
    return False


if not _check_password():
    st.stop()

st.title("Ask the Agent")
st.caption(
    "Plain-English questions answered by a read-only text-to-SQL agent. "
    "The SQL it ran is always shown alongside the answer, for transparency."
)

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

for message in st.session_state.chat_history:
    with st.chat_message(message["role"]):
        st.write(message["content"])
        if message.get("sql"):
            with st.expander("SQL"):
                st.code(message["sql"], language="sql")
            if message.get("rows"):
                st.dataframe(pd.DataFrame(message["rows"]), width="stretch", hide_index=True)

question = st.chat_input("e.g. What did Kevin Durant average in MVP season?")

if question:
    st.session_state.chat_history.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.write(question)

    with st.chat_message("assistant"):
        with st.spinner("Querying..."):
            try:
                response = requests.post(
                    f"{get_settings().agent_service_url}/ask",
                    json={"question": question},
                    timeout=60,
                )
                response.raise_for_status()
                result = response.json()
            except requests.RequestException as exc:
                result = {
                    "answer": f"Couldn't reach the agent service at {get_settings().agent_service_url} -- "
                    f"is it running? (`uvicorn agent_service.main:app --port 8000`)\n\n{exc}",
                    "sql": None,
                    "rows": None,
                }

        st.write(result["answer"])
        if result.get("sql"):
            with st.expander("SQL"):
                st.code(result["sql"], language="sql")
            if result.get("rows"):
                st.dataframe(pd.DataFrame(result["rows"]), width="stretch", hide_index=True)

    st.session_state.chat_history.append(
        {"role": "assistant", "content": result["answer"], "sql": result.get("sql"), "rows": result.get("rows")}
    )
