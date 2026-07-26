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




tools = [
    {
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
    },
    {
        "name": "calculate_change",
        "description": "Calculate the absolute and percentage change between two numeric values (e.g. comparing a metric between two years). Always use this instead of computing changes yourself.",
        "input_schema": {
            "type": "object",
            "properties": {
                "value_start": {"type": "number", "description": "The earlier/starting value"},
                "value_end": {"type": "number", "description": "The later/ending value"}
            },
            "required": ["value_start", "value_end"]
        }
    }
]
def calculate_change(value_start: float, value_end: float) -> dict:
    absolute_change = value_end - value_start
    percent_change = (absolute_change / value_start) * 100 if value_start != 0 else None
    return {
        "absolute_change": absolute_change,
        "percent_change": round(percent_change, 2) if percent_change is not None else None
    }

def ask(question: str):
    schema_summary = get_schema_summary()
    
    system_prompt = f"""You are a census data assistant for Boroondara, Australia.
You have access to a query_census tool. The database contains these exact 
categories and subcategories - always use these EXACT values, never guess 
or paraphrase them:

{schema_summary}

When comparing values across years or calculating growth/change, always 
use the calculate_change tool rather than computing the difference yourself."""



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
                if block.name == "query_census":
                    result = query_census(**block.input)
                elif block.name == "calculate_change":
                    result = calculate_change(**block.input)
                else:
                    result = {"error": f"Unknown tool: {block.name}"}
                
                print(f"Called {block.name} with: {block.input} -> {result}")
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": str(result)
                })
        
        messages.append({"role": "user", "content": tool_results})

if __name__ == "__main__":
    #print(ask("How many people were aged 20-24 in 2016?"))
    #print(ask("What's the breakdown of dwelling types in 2021?"))
     print(ask("How did the number of separate houses change between 2016 and 2021?"))