import streamlit as st
import sqlite3

st.title("Boroondara Census Lookup")

conn = sqlite3.connect("boroondara_census.db")
cursor = conn.cursor()

# Get available categories to populate a dropdown
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

#test