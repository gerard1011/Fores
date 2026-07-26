import pandas as pd
import sqlite3
import warnings

warnings.filterwarnings("ignore")

# Load the Excel file, see what sheets exist
file_path = "/Users/gerardczerwik/boroondara-project/TimeSeries_Boroondara_2021.xlsx"

db_path = "/Users/gerardczerwik/boroondara-project/boroondara_census.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS census_data (
    lga TEXT,
    year INTEGER,
    category TEXT,
    subcategory TEXT,
    value INTEGER
)
""")

xl = pd.ExcelFile(file_path)
YEARS = [2011, 2016, 2021]

records = []  # (lga, year, category, subcategory, value)


def add(year, category, subcategory, value):
    if pd.isna(value):
        return
    records.append(("Boroondara", year, category, subcategory, int(value)))


# =================================================================
# T01: Selected person characteristics by sex (population)
# =================================================================
df = xl.parse("T01", header=None)
df.columns = [
    "label",
    "2011_Males", "2011_Females", "2011_Persons",
    "spacer1",
    "2016_Males", "2016_Females", "2016_Persons",
    "spacer2",
    "2021_Males", "2021_Females", "2021_Persons",
]
df = df.drop(columns=["spacer1", "spacer2"])
df = df.set_index("label")
total_pop = df.loc["Total persons(a)"]
for year, col in [(2011, "2011_Persons"), (2016, "2016_Persons"), (2021, "2021_Persons")]:
    add(year, "population", "total", total_pop[col])


# =================================================================
# GROUP 1 helper: single sheet, years as column-blocks, M/F/Persons
# sub-cols, flat row list. Persons column = block_start_col + 2.
# =================================================================
YEAR_COLS_PERSONS = {2011: 3, 2016: 7, 2021: 11}


def extract_group1(sheet, category, rows_map, year_cols=YEAR_COLS_PERSONS):
    """rows_map: {row_index: subcategory_label}"""
    d = xl.parse(sheet, header=None)
    for row_idx, subcat in rows_map.items():
        for year, col in year_cols.items():
            add(year, category, subcat, d.iat[row_idx, col])


# T03: age by sex -- combine T03a (ages 0-39) + T03b (ages 40-85+), 5-year bands only
# (single-year-of-age rows are skipped to avoid double-counting against the band rows)
df_a = xl.parse("T03a", header=None)
df_b = xl.parse("T03b", header=None)
t03_bands_a = {16: "0-4 years", 22: "5-9 years", 28: "10-14 years", 34: "15-19 years",
               40: "20-24 years", 46: "25-29 years", 52: "30-34 years", 58: "35-39 years"}
t03_bands_b = {16: "40-44 years", 22: "45-49 years", 28: "50-54 years", 34: "55-59 years",
               40: "60-64 years", 46: "65-69 years", 52: "70-74 years", 58: "75-79 years",
               59: "80-84 years", 60: "85 years and over"}
for row_idx, subcat in t03_bands_a.items():
    for year, col in YEAR_COLS_PERSONS.items():
        add(year, "age", subcat, df_a.iat[row_idx, col])
for row_idx, subcat in t03_bands_b.items():
    for year, col in YEAR_COLS_PERSONS.items():
        add(year, "age", subcat, df_b.iat[row_idx, col])

# T08: country of birth (flat list)
df08 = xl.parse("T08", header=None)
for r in range(10, 45):
    label = df08.iat[r, 0]
    if pd.notna(label):
        for year, col in YEAR_COLS_PERSONS.items():
            add(year, "country_of_birth", str(label).strip(), df08.iat[r, col])

# T10: language used at home (flat, with one nested subtotal: Chinese languages)
df10 = xl.parse("T10", header=None)
t10_rows = {10: "Uses English only", 13: "Arabic", 14: "Australian Indigenous Languages",
            15: "Bengali", 20: "Chinese languages", 21: "Croatian", 22: "Filipino",
            23: "French", 24: "German", 25: "Greek", 26: "Gujarati", 27: "Hindi",
            28: "Indonesian", 29: "Italian", 30: "Japanese", 31: "Korean", 32: "Macedonian",
            33: "Malayalam", 34: "Nepali", 35: "Persian (excluding Dari)", 36: "Portuguese",
            37: "Punjabi", 38: "Russian", 39: "Serbian", 40: "Sinhalese", 41: "Spanish",
            42: "Tagalog", 43: "Tamil", 44: "Thai"}
extract_group1("T10", "language_at_home", t10_rows)

# T13: type of educational institution (top-level totals only)
t13_rows = {10: "Preschool", 16: "Primary", 22: "Secondary",
            33: "Vocational education (TAFE etc.)", 43: "University or other higher education"}
extract_group1("T13", "education_institution", t13_rows)

# T29: selected labour force / education / migration characteristics
# (curated rows; percentage-rate rows like "% Unemployment" are skipped since the
# schema stores integer counts, not rates)
t29_rows = {11: "Persons aged 15 years and over", 14: "Employed, worked full-time",
            15: "Employed, worked part-time", 16: "Employed, away from work",
            17: "Unemployed, looking for work", 18: "Total labour force",
            20: "Not in the labour force", 27: "Postgraduate Degree Level",
            28: "Graduate Diploma and Graduate Certificate Level", 29: "Bachelor Degree Level",
            30: "Advanced Diploma and Diploma Level", 35: "Total non-school qualification",
            38: "Lived at same address 1 year ago", 39: "Lived at different address 1 year ago",
            41: "Lived at same address 5 years ago", 42: "Lived at different address 5 years ago"}
extract_group1("T29", "labour_force_education_migration", t29_rows)

# T34: industry of employment (flat)
df34 = xl.parse("T34", header=None)
for r in list(range(10, 29)) + [30]:
    label = df34.iat[r, 0]
    if pd.notna(label):
        for year, col in YEAR_COLS_PERSONS.items():
            add(year, "industry_of_employment", str(label).strip(), df34.iat[r, col])

# T35: occupation (flat)
df35 = xl.parse("T35", header=None)
for r in range(10, 19):
    label = df35.iat[r, 0]
    if pd.notna(label):
        for year, col in YEAR_COLS_PERSONS.items():
            add(year, "occupation", str(label).strip(), df35.iat[r, col])


# =================================================================
# GROUP 2 helper: single sheet, years as ROW-blocks, category as columns.
# subcategory = column category; value = the "Total" row (marginalizing
# the row dimension, e.g. age).
# =================================================================
def extract_group2(sheet, category, markers, persons_cols, total_label="Total"):
    """markers: [row_of_2011_marker, row_of_2016_marker, row_of_2021_marker]
    persons_cols: {subcategory_label: persons_column_index}"""
    d = xl.parse(sheet, header=None)
    delta1 = markers[1] - markers[0]
    delta2 = markers[2] - markers[0]
    for year, delta in zip(YEARS, [0, delta1, delta2]):
        start = markers[0] + delta
        end = markers[1] + delta if delta != delta2 else len(d)
        total_row = None
        for r in range(start, min(end, len(d))):
            v = d.iat[r, 0]
            if isinstance(v, str) and v.strip() == total_label:
                total_row = r
                break
        if total_row is None:
            print(f"  !! {sheet} {year}: could not find '{total_label}' row in block, skipping")
            continue
        for subcat, col in persons_cols.items():
            add(year, category, subcat, d.iat[total_row, col])


extract_group2("T04", "marital_status_registered", [9, 29, 49],
               {"married": 3, "separated": 7, "divorced": 11, "widowed": 15, "never married": 19})
extract_group2("T05", "marital_status_social", [10, 30, 50],
               {"married - registered marriage": 3, "married - de facto": 7, "not married": 11})
extract_group2("T06", "indigenous_status", [9, 28, 47],
               {"aboriginal and/or torres strait islander": 3, "non-indigenous": 7, "not stated": 11})
extract_group2("T07", "children_ever_born", [10, 31, 52],
               {"no children": 1, "one child": 2, "two children": 3, "three children": 4,
                "four children": 5, "five children": 6, "six or more children": 7, "not stated": 8})
extract_group2("T11", "english_proficiency", [10, 24, 38],
               {"speaks english only": 1, "very well or well": 3, "not well or not at all": 4,
                "proficiency in english not stated": 5, "language and proficiency not stated": 7})
extract_group2("T28", "core_activity_need_for_assistance", [9, 25, 41],
               {"has need for assistance": 3, "does not have need for assistance": 7,
                "need for assistance not stated": 11})


# =================================================================
# GROUP 3 helper: single sheet, years as ROW-blocks, ROW = category
# (subcategory), column = secondary dimension with a "Total" column
# marginalizing it.
# =================================================================
def extract_group3(sheet, category, markers, total_col, row_labels_block1):
    d = xl.parse(sheet, header=None)
    deltas = [0, markers[1] - markers[0], markers[2] - markers[0]]
    for year, delta in zip(YEARS, deltas):
        for row_idx, subcat in row_labels_block1.items():
            add(year, category, subcat, d.iat[row_idx + delta, total_col])


extract_group3("T18", "tenure_landlord_type", [12, 31, 50], total_col=6,
               row_labels_block1={14: "owned outright", 15: "owned with a mortgage",
                                   18: "real estate agent", 19: "state or territory housing authority",
                                   20: "community housing provider", 21: "person not in same household",
                                   22: "other landlord type", 23: "landlord type not stated",
                                   26: "other tenure type", 27: "tenure type not stated"})

extract_group3("T19", "rent_weekly", [10, 30, 50], total_col=7,
               row_labels_block1={12: "$1-$74", 13: "$75-$99", 14: "$100-$149", 15: "$150-$199",
                                   16: "$200-$224", 17: "$225-$274", 18: "$275-$349", 19: "$350-$449",
                                   20: "$450-$549", 21: "$550-$649", 22: "$650-$749", 23: "$750-$849",
                                   24: "$850-$949", 25: "$950 and over", 26: "rent not stated"})

extract_group3("T20", "rent_couple_families", [12, 32, 52], total_col=6,
               row_labels_block1={14: "$1-$74", 15: "$75-$99", 16: "$100-$149", 17: "$150-$199",
                                   18: "$200-$224", 19: "$225-$274", 20: "$275-$349", 21: "$350-$449",
                                   22: "$450-$549", 23: "$550-$649", 24: "$650-$749", 25: "$750-$849",
                                   26: "$850-$949"})

extract_group3("T21", "rent_one_parent_families", [12, 32, 52], total_col=5,
               row_labels_block1={14: "$1-$74", 15: "$75-$99", 16: "$100-$149", 17: "$150-$199",
                                   18: "$200-$224", 19: "$225-$274", 20: "$275-$349", 21: "$350-$449",
                                   22: "$450-$549", 23: "$550-$649", 24: "$650-$749", 25: "$750-$849"})

extract_group3("T22", "family_income_couple_by_children", [9, 30, 51], total_col=5,
               row_labels_block1={11: "negative/nil income", 12: "$1-$149", 13: "$150-$299",
                                   14: "$300-$399", 15: "$400-$499", 16: "$500-$649", 17: "$650-$799",
                                   18: "$800-$999", 19: "$1,000-$1,499", 20: "$1,500-$1,999",
                                   21: "$2,000-$2,499", 22: "$2,500-$2,999", 23: "$3,000-$3,999",
                                   24: "$4,000 or more", 25: "partial income stated"})

extract_group3("T23", "family_income_oneparent_by_children", [9, 30, 51], total_col=5,
               row_labels_block1={11: "negative/nil income", 12: "$1-$149", 13: "$150-$299",
                                   14: "$300-$399", 15: "$400-$499", 16: "$500-$649", 17: "$650-$799",
                                   18: "$800-$999", 19: "$1,000-$1,499", 20: "$1,500-$1,999",
                                   21: "$2,000-$2,499", 22: "$2,500-$2,999", 23: "$3,000-$3,999",
                                   24: "$4,000 or more", 25: "partial income stated"})

extract_group3("T24", "household_income_by_rent", [10, 32, 54], total_col=13,
               row_labels_block1={12: "negative/nil income", 13: "$1-$149", 14: "$150-$299",
                                   15: "$300-$399", 16: "$400-$499", 17: "$500-$649", 18: "$650-$799",
                                   19: "$800-$999", 20: "$1,000-$1,249", 21: "$1,250-$1,499",
                                   22: "$1,500-$1,999", 23: "$2,000-$2,499", 24: "$2,500-$2,999",
                                   25: "$3,000-$3,999", 26: "$4,000 or more"})

extract_group3("T27", "family_composition_dependent_children", [10, 20, 30], total_col=5,
               row_labels_block1={16: "couple family with children", 18: "one parent family"})


# =================================================================
# GROUP 4: dwelling-structure family (T14-T17), split into a/b/c = year
# (one block per file). Rows have one level of nesting (group header +
# Total); column = Total (marginalizing the secondary dimension).
# =================================================================
def extract_group4(sheet_prefix, category, total_col, row_labels):
    for suffix, year in zip("abc", YEARS):
        d = xl.parse(f"{sheet_prefix}{suffix}", header=None)
        for row_idx, subcat in row_labels.items():
            add(year, category, subcat, d.iat[row_idx, total_col])


extract_group4("T14", "dwelling_structure", total_col=9,
               row_labels={12: "separate house", 17: "semi-detached, row or terrace house",
                           25: "flat or apartment", 31: "other dwelling",
                           33: "dwelling structure not stated"})

extract_group4("T15", "dwelling_structure_by_occupants", total_col=7,
               row_labels={12: "separate house", 17: "semi-detached, row or terrace house",
                           25: "flat or apartment", 31: "other dwelling",
                           33: "dwelling structure not stated"})

extract_group4("T16", "dwelling_bedrooms_family_households", total_col=6,
               row_labels={19: "separate house", 29: "semi-detached, row or terrace house",
                           37: "flat or apartment", 46: "other dwelling",
                           48: "dwelling structure not stated"})

extract_group4("T17", "dwelling_bedrooms_group_households", total_col=6,
               row_labels={19: "separate house", 29: "semi-detached, row or terrace house",
                           37: "flat or apartment", 46: "other dwelling",
                           48: "dwelling structure not stated"})


# =================================================================
# GROUP 5: year-split a/b/c files (T09, T12), rows flat/grouped,
# Total column marginal.
# =================================================================
def extract_group5(sheet_prefix, category, total_col, row_labels):
    for suffix, year in zip("abc", YEARS):
        d = xl.parse(f"{sheet_prefix}{suffix}", header=None)
        for row_idx, subcat in row_labels.items():
            add(year, category, subcat, d.iat[row_idx, total_col])


t09_rows = {}
df09a = xl.parse("T09a", header=None)
for r in range(11, 43):
    label = df09a.iat[r, 0]
    if pd.notna(label):
        t09_rows[r] = str(label).strip()
extract_group5("T09", "ancestry", total_col=6, row_labels=t09_rows)

t12_rows = {12: "buddhism", 33: "christianity", 34: "hinduism", 35: "islam", 36: "judaism",
            41: "other religions", 42: "secular beliefs and other spiritual beliefs and no religious affiliation",
            44: "religious affiliation not stated"}
extract_group5("T12", "religious_affiliation", total_col=10, row_labels=t12_rows)


# =================================================================
# GROUP 6: sex-split a/b/c files (T31, T32, T33) -- use 'c' (Persons)
# only, matching the Persons-only convention used everywhere else.
# Years are row-blocks WITHIN the c file.
# =================================================================
df31c = xl.parse("T31c", header=None)
t31_markers = [9, 25, 41]
t31_rows_block1 = {11: "postgraduate degree level", 12: "graduate diploma and graduate certificate level",
                    13: "bachelor degree level", 14: "advanced diploma and diploma level",
                    19: "certificate level", 20: "level of education inadequately described",
                    21: "level of education not stated"}
deltas = [0, t31_markers[1] - t31_markers[0], t31_markers[2] - t31_markers[0]]
for year, delta in zip(YEARS, deltas):
    for row_idx, subcat in t31_rows_block1.items():
        add(year, "education_qualification_level", subcat, df31c.iat[row_idx + delta, 10])

df32c = xl.parse("T32c", header=None)
t32_markers = [10, 29, 48]
t32_rows_block1 = {12: "natural and physical sciences", 13: "information technology",
                    14: "engineering and related technologies", 15: "architecture and building",
                    16: "agriculture, environmental and related studies", 17: "health",
                    18: "education", 19: "management and commerce", 20: "society and culture",
                    21: "creative arts", 22: "food, hospitality and personal services",
                    23: "mixed field programmes", 24: "field of study inadequately described"}
deltas = [0, t32_markers[1] - t32_markers[0], t32_markers[2] - t32_markers[0]]
for year, delta in zip(YEARS, deltas):
    for row_idx, subcat in t32_rows_block1.items():
        add(year, "education_field_of_study", subcat, df32c.iat[row_idx + delta, 10])

# T33: rows=age, columns=labour force status categories -> use the Total
# ROW (marginalizing age), matching Group 2's convention.
df33c = xl.parse("T33c", header=None)
t33_markers = [10, 28, 46]
t33_cols = {"employed - worked full-time": 1, "employed - worked part-time": 2,
            "employed - away from work": 3, "unemployed - looking for full-time work": 7,
            "unemployed - looking for part-time work": 8, "total labour force": 10,
            "not in the labour force": 11}
deltas = [0, t33_markers[1] - t33_markers[0], t33_markers[2] - t33_markers[0]]
for year, delta in zip(YEARS, deltas):
    start = t33_markers[0] + delta
    total_row = None
    for r in range(start, start + 20):
        v = df33c.iat[r, 0]
        if isinstance(v, str) and v.strip() == "Total":
            total_row = r
            break
    if total_row is None:
        print(f"  !! T33 {year}: could not find Total row, skipping")
        continue
    for subcat, col in t33_cols.items():
        add(year, "labour_force_status", subcat, df33c.iat[total_row, col])


# =================================================================
# NOTE on tables intentionally NOT extracted:
#   T02 - "Selected medians and averages": not a category/value table at
#         all (named statistics in a free-form two-panel layout), and
#         several values are decimals (e.g. 0.9 persons/bedroom) that
#         don't fit this schema's integer counts.
#   T25 - "Family composition by mortgage repayment": category labels are
#         split across two physical rows (e.g. "Couple family with
#         children under 15:" + "and dependent students(d)") nested three
#         levels deep -- too ambiguous to name a clean subcategory
#         without guessing.
#   T26 - "Couple families by income comparison for parents/partners":
#         same multi-line nested label problem as T25, plus the only
#         other metric besides "Families" is a Percentage (non-count).
#   T30 - "Family composition and labour force status of parent(s)/
#         partners by total family income": three family-type sections
#         each with ~10 nested employment-status combinations and
#         multi-line labels -- same issue as T25/T26, at greater depth.
# =================================================================


# --- Write to SQLite (idempotent: replace any previous run's rows for
#     the categories we're about to (re)insert, so re-running this
#     script doesn't create duplicates) ---
categories_in_this_run = sorted(set(r[2] for r in records))
cursor.executemany(
    "DELETE FROM census_data WHERE category = ?",
    [(c,) for c in categories_in_this_run],
)
cursor.executemany(
    "INSERT INTO census_data (lga, year, category, subcategory, value) VALUES (?, ?, ?, ?, ?)",
    records,
)
conn.commit()

# --- Verify: row counts per category ---
print(f"Inserted {len(records)} rows across {len(categories_in_this_run)} categories.\n")
cursor.execute("SELECT category, COUNT(*) FROM census_data GROUP BY category ORDER BY category")
for category, n in cursor.fetchall():
    print(f"  {category}: {n}")

conn.close()



#test