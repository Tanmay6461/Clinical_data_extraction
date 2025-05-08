# prompt_get_drug_names = """
# You are a biomedical research assistant.

# Given the text below, extract all **drug program names** or **candidate names** associated with the company ticker "{ticker}". These may include:
# - Code names (e.g., WVE-N531, BLU-808, ALN-AT3)
# - Scientific names (e.g., Avapritinib, Inclisiran)
# - Commercial names (e.g., Onpattro, Gleevec)

# Important:
# - A single program may have multiple names over its development.
# - Company-specific prefixes (like WVE, BLU, ALN) often appear, but not always.
# - Return the result as a plain Python list (e.g., ["WVE-N531", "Avapritinib"]).
# - Do **not** include any Markdown formatting (e.g., no triple backticks or ```python).
# - Do not include any explanation or extra text—just return the list.
# - Do not include unrelated drugs or names.

# Text:
# {content}

# Answer:
# """
prompt_get_drug_names = """
You are a biomedical research assistant.

Given the text below, extract all drug development program names, candidate drugs, or therapeutics associated with the company ticker "{ticker}". These may fall into three categories:
- **Code names**: Internal or development-stage identifiers (e.g., WVE-N531, BLU-808, ALN-AT3)
- **Scientific names**: Generic or International Nonproprietary Names (e.g., Inclisiran, Avapritinib)
- **Commercial names**: Marketed or branded names (e.g., Onpattro, Gleevec)

Instructions:
- A single drug program may have multiple names throughout its lifecycle. Include all relevant names for a single program.
- Company-specific prefixes like WVE, BLU, or ALN often appear in development-stage names.
- **Only include actual drug or program names. Do not include:**
  - General disease areas (e.g., "AATD", "C9orf72", "ATXN3")
  - Platform names, technology platforms, or discovery initiatives (e.g., "ADAR editing program")
  - Partial or descriptive identifiers (e.g., "Exon 51")
  - Duplicates (ensure each name appears only once, case-insensitive)
- Do not include any names that refer to diseases, mechanisms, or platforms rather than specific drugs.

Return the extracted program or drug names in **a valid Python list** (e.g., ["WVE-N531", "Avapritinib", "Onpattro"]) with **no markdown, code fencing, or explanatory text**.

Text:
{content}

Answer:

"""
