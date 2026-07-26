import os
import sqlite3
from dotenv import load_dotenv
import anthropic

load_dotenv()
client = anthropic.Anthropic()  # automatically reads ANTHROPIC_API_KEY from environment

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

tools = [{
    "name": "query_census",
    "description": "Query Boroondara census data by category and subcategory. Returns year/value pairs.",
    "input_schema": {
        "type": "object",
        "properties": {
            "category": {"type": "string", "description": "e.g. 'population', 'age', 'dwelling_structure'"},
            "subcategory": {"type": "string", "description": "e.g. 'total', '20-24 years'"}
        },
        "required": ["category", "subcategory"]
    }
}]

def ask(question: str):
    messages = [{"role": "user", "content": question}]
    
    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=1024,
        tools=tools,
        messages=messages
    )
    
    # If Claude wants to use the tool
    if response.stop_reason == "tool_use":
        tool_use = next(block for block in response.content if block.type == "tool_use")
        result = query_census(**tool_use.input)
        
        messages.append({"role": "assistant", "content": response.content})
        messages.append({
            "role": "user",
            "content": [{
                "type": "tool_result",
                "tool_use_id": tool_use.id,
                "content": str(result)
            }]
        })
        
        final_response = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1024,
            tools=tools,
            messages=messages
        )
        return final_response.content[0].text
    
    return response.content[0].text

if __name__ == "__main__":
    answer = ask("What was the population in 2011?")
    print(answer)