"""Streamlit UI — being replaced by web/ and deleted in a later commit.

Left runnable so this commit stands on its own. It now goes through api.db
rather than opening its own SQLite connection on a relative path, so it keeps
working with the bind-mounted database.
"""

import streamlit as st

from api.agent import ask
from api.db import category_series, list_categories

st.title("Boroondara Census Assistant")

# --- Section 1: AI Chat Interface ---
st.header("Ask a question")

if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.write(message["content"])

user_question = st.chat_input("Ask about Boroondara census data...")

if user_question:
    st.session_state.messages.append({"role": "user", "content": user_question})
    with st.chat_message("user"):
        st.write(user_question)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            answer = ask(user_question)
        st.write(answer)
    st.session_state.messages.append({"role": "assistant", "content": answer})

st.divider()

# --- Section 2: Manual lookup (ground truth checker) ---
st.header("Manual lookup (verify the AI's answers)")

categories = [c["category"] for c in list_categories()]
selected_category = st.selectbox("Select a category", categories)

rows = category_series(selected_category)
subcategories = sorted({r["subcategory"] for r in rows})
selected_subcategory = st.selectbox("Select a subcategory", subcategories)

if st.button("Look up"):
    st.write(f"Results for {selected_category} — {selected_subcategory}:")
    for row in rows:
        if row["subcategory"] == selected_subcategory:
            st.write(f"{row['year']}: {row['value']}")
