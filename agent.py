import os
import sqlite3
from dotenv import load_dotenv
import anthropic

load_dotenv()
client = anthropic.Anthropic()

def query_census(category: str, subcategory: str) -> list:
    conn = sqlite3.connect("boroondara_census.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT year, value FROM census_data WHERE category = ? AND subcategory = ? ORDER BY year",
        (category, subcategory)
    )
    results = cursor.fetchall()
    conn.close()
    return results


def get_schema_summary():
    conn = sqlite3.connect("boroondara_census.db")
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT category, subcategory FROM census_data ORDER BY category, subcategory")
    rows = cursor.fetchall()
    conn.close()
    
    schema = {}
    for category, subcategory in rows:
        schema.setdefault(category, []).append(subcategory)
    
    lines = []
    for category, subcats in schema.items():
        lines.append(f"- {category}: {', '.join(subcats)}")
    
    return "\n".join(lines)

tools = [{
    "name": "query_census",
    "description": "Query Boroondara census data by category and subcategory. Returns year/value pairs.",
    "input_schema": {
        "type": "object",
        "properties": {
            "category": {"type": "string"},
            "subcategory": {"type": "string"}
        },
        "required": ["category", "subcategory"]
    }
}]

def ask(question: str):
    schema_summary = get_schema_summary()
    
    system_prompt = f"""You are a census data assistant for Boroondara, Australia.
You have access to a query_census tool. The database contains these exact 
categories and subcategories - always use these EXACT values, never guess 
or paraphrase them:

{schema_summary}

When answering, only use category/subcategory values from this list.
If a question requires multiple subcategories (e.g. a full breakdown), 
call the tool once for each relevant subcategory."""

    messages = [{"role": "user", "content": question}]
    
    while True:
        response = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1024,
            system=system_prompt,
            tools=tools,
            messages=messages
        )
        
        if response.stop_reason != "tool_use":
            return response.content[0].text
        
        messages.append({"role": "assistant", "content": response.content})
        
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                result = query_census(**block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": str(result)
                })
                # temporarily add inside the tool_use loop, right after getting `result`
                print(f"Called with: {block.input} -> {result}")
        
        messages.append({"role": "user", "content": tool_results})

if __name__ == "__main__":
    print(ask("How many people were aged 20-24 in 2016?"))
    print(ask("What's the breakdown of dwelling types in 2021?"))
