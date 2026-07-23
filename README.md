# Fores
Application that utilises agentic capabilites that provides companies with accurate and on demand knowledge about their internal systems

## Census Data Pipeline

Extracts ABS Census Time Series data (2011/2016/2021) for Boroondara LGA
from raw Excel spreadsheets into a structured SQLite database.

### What it does
Parses 30+ ABS census tables (population, age, dwellings, income, etc.)
 Handles ABS's non-standard Excel layout (merged cells, multi-year 
  column blocks)
Loads into a normalized `census_data` table: (lga, year, category, 
  subcategory, value)
Idempotent safe to re-run without duplicating data

### Usage
python3 census_script.py

### Data source
Australian Bureau of Statistics, 2021 Census Time Series Profile