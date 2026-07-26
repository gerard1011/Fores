import streamlit as st
import sqlite3
from agent import ask  # import your working agent function

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

conn = sqlite3.connect("data/boroondara_census.db")
cursor = conn.cursor()

cursor.execute("SELECT DISTINCT category FROM census_data ORDER BY category")
categories = [row[0] for row in cursor.fetchall()]

selected_category = st.selectbox("Select a category", categories)

cursor.execute(
    "SELECT DISTINCT subcategory FROM census_data WHERE category = ? ORDER BY subcategory",
    (selected_category,)
)
subcategories = [row[0] for row in cursor.fetchall()]

selected_subcategory = st.selectbox("Select a subcategory", subcategories)

if st.button("Look up"):
    cursor.execute(
        "SELECT year, value FROM census_data WHERE category = ? AND subcategory = ? ORDER BY year",
        (selected_category, selected_subcategory)
    )
    results = cursor.fetchall()
    st.write(f"Results for {selected_category} — {selected_subcategory}:")
    for year, value in results:
        st.write(f"{year}: {value}")

conn.close()