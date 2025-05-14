
# prompt_get_drug_names = """
# You are an expert biomedical assistant building a drug pipeline knowledge base from SEC filings.

# Your task is to extract and summarize **only actual drug development programs** from the text below — one per row — and return them in a structured JSON format.

# ---

# 🔍 Your approach must:

# - Thoroughly scan **every sentence and line** in the input — do not skip partial mentions.
# - Capture drugs even if **some fields (e.g., trials or MoA)** are not available.
# - Always include any **renaming clues**, such as "formerly ALN-TTRsc04" or "also known as ...".

# ---

# For each valid drug, extract:

# - **name**: The main internal code or commercial name (e.g., WVE-120101, suvodirsen, ALN-TTRsc02)
# - **mechanism_of_action**: e.g., “Splicing oligonucleotide promoting exon 53 skipping”
# - **target**: e.g., dystrophin pre-mRNA
# - **indication**: e.g., Duchenne muscular dystrophy (DMD), ATTR amyloidosis
# - **preclinical_data**: List key animal or in vitro results (model type, result, year/reference if mentioned)
# - **clinical_trials**: Bullet list by phase and part (e.g., “Phase 2 Part A”), trial size, endpoints, dates, results
# - **upcoming_milestones**: Future FDA interactions, readouts, regulatory events
# - **references**: List SEC filing section(s), filing date, and URL (if available)
# - **aliases**: If the drug has other names (e.g., “nucresiran (formerly ALN-TTRsc04)”), list all of them in exact casing

# ---

# 🚫 STRICT EXCLUSION RULES — DO NOT include the following:

# ❌ Mentions of **only targets** (e.g., “ATXN3 program”, “PCSK9si”)
# ❌ Mentions of **only platforms** or **technologies** (e.g., “GalNAc conjugate”, “RNA editing platform”)
# ❌ Placeholder or vague descriptions (e.g., “our lead candidate”, “Compound 1”, “Phase 1 program”)
# ❌ Umbrella labels (e.g., “PRECISION-HD platform”, “AIMer pipeline”)

# ---

# 📦 FORMAT: Return raw JSON like this:

# {{
#   "programs": [
#     {{
#       "name": "string",
#       "mechanism_of_action": "string",
#       "target": "string",
#       "indication": "string",
#       "preclinical_data": ["string"],
#       "clinical_trials": ["string"],
#       "upcoming_milestones": ["string"],
#       "references": ["string"],
#     }}
#   ]
# }}

# ---

# ✅ Format rules:
# - Do NOT include markdown formatting or triple backticks
# - Use "" or [] if a field is missing
# - Return an empty array if no valid drugs are found
# - **Preserve original casing, spacing, and punctuation** for all values — especially for drug names and aliases
# - Do NOT normalize to lowercase or standardize spellings
# - If aliases like “formerly ALN-TTRsc04” are mentioned, extract both names and place them in the `aliases` array.

# ---

# TEXT TO ANALYZE:
# {content}

# ---
# JSON:
# """


prompt_get_drug_names = """
You are an expert biomedical assistant building a drug pipeline knowledge base from SEC filings.

Your task is to extract and summarize **only actual drug development programs** from the text below — one per row — and return them in a structured JSON format.

---

🔍 Your approach must:

- Thoroughly scan **every sentence and line** in the input — do not skip partial mentions.
- Capture drugs even if **some fields (e.g., trials or MoA)** are not available.
- Always include any **renaming clues**, such as "formerly ALN-TTRsc04" or "also known as ...".

---

For each valid drug, extract:

- **name**: The main internal code or commercial name (e.g., WVE-120101, suvodirsen, ALN-TTRsc02)
- **mechanism_of_action**: e.g., “Splicing oligonucleotide promoting exon 53 skipping”
- **target**: e.g., dystrophin pre-mRNA
- **indication**: e.g., Duchenne muscular dystrophy (DMD), ATTR amyloidosis
- **preclinical_data**: List key animal or in vitro results (model type, result, year/reference if mentioned)
- **clinical_trials**: Bullet list by phase and part (e.g., “Phase 2 Part A”), trial size, endpoints, dates, results
- **upcoming_milestones**: Future FDA interactions, readouts, regulatory events
- **references**: List SEC filing section(s), filing date, and URL (if available)
- **aliases**: If the drug has other names (e.g., “nucresiran (formerly ALN-TTRsc04)”), list all of them in exact casing

---

🚫 STRICT EXCLUSION RULES — DO NOT include the following:

❌ Mentions of **only targets** (e.g., “ATXN3 program”, “PCSK9si”)
❌ Mentions of **only platforms** or **technologies** (e.g., “GalNAc conjugate”, “RNA editing platform”)
❌ Placeholder or vague descriptions (e.g., “our lead candidate”, “Compound 1”, “Phase 1 program”)
❌ Umbrella labels (e.g., “PRECISION-HD platform”, “AIMer pipeline”)

---

📦 FORMAT: Return raw JSON like this:

{{
  "programs": [
    {{
      "name": "string",
      "mechanism_of_action": "string",
      "target": "string",
      "indication": "string",
      "preclinical_data": ["string"],
      "clinical_trials": ["string"],
      "upcoming_milestones": ["string"],
      "references": ["string"],
      "aliases": ["string"]
    }}
  ]
}}

---

✅ Format rules:
- Do NOT include markdown formatting or triple backticks
- Use "" or [] if a field is missing
- Return an empty array if no valid drugs are found
- **Preserve original casing, spacing, and punctuation** for all values — especially for drug names and aliases
- If aliases like “formerly ALN-TTRsc04” are mentioned, extract both names and place them in the `aliases` array.
- **Strip trademark, copyright, and registration symbols** like ™, ®, and © from all drug names and aliases (e.g., return "AMVUTTRA" not "AMVUTTRA™")

---

TEXT TO ANALYZE:
{content}

---
JSON:

"""



prompt_group_drug_names = """"
You are a biomedical text mining assistant working with drug filings and disclosures.

Your task is to extract a **mapping of canonical drug names to all known aliases**, including:
- Internal codes (e.g., ALN-TTR02, ALN-AT3, WVE-120101)
- Commercial or branded names (e.g., ONPATTRO, AMVUTTRA)
- Generic names (e.g., patisiran, inclisiran)
- Compound naming formats (e.g., “patisiran (ALN-TTR02)”, “ONPATTRO (patisiran)”)

---

💡 INSTRUCTIONS:

- Go through the list of drug names **line by line** and group any entries that clearly refer to the **same drug**.
- You must include:
  - Exact aliases, including all spelling and casing variations (e.g., “ONPATTRO”, “ONPATTRO®”, “ONPATTRO™”)
  - Compound forms like “patisiran (ALN-TTR02)” or “Leqvio (inclisiran)”
  - Former or alternate names (e.g., “formerly ALN-TTRsc04”)
- **If a drug appears in multiple entries under different names, unify them into a single object**.
- If a drug name appears once with no known aliases, still include it in the result with its name repeated in the `aliases` field.

---

📦 FORMAT:

Return a raw JSON list like this:

[
  {{
    "name": "ALN-TTR02",
    "aliases": [
      "ALN-TTR02",
      "patisiran",
      "Patisiran",
      "ONPATTRO",
      "ONPATTRO®",
      "ONPATTRO™",
      "patisiran (ALN-TTR02)",
      "ONPATTRO (patisiran)"
    ]
  }},
  {{
    "name": "cemdisiran",
    "aliases": [
      "cemdisiran"
    ]
  }}
]

---

✅ REQUIRED RULES:

- Every alias **must come directly from the provided list** (preserve original spelling and casing).
- Choose the **internal code as `name`** if available, else use the most unique or specific generic/commercial name.
- If multiple internal codes exist for a drug, choose the earliest or most specific one.
- Strip trailing trademark/copyright/registration symbols (™ ® ©) when determining the canonical `name`, but preserve them in the `aliases` field.
- **No duplicates allowed across alias groups** — each alias should appear in only one group.

---

❌ DO NOT INCLUDE:
- Mentions of targets, biological pathways, platform names (e.g., “PCSK9si”, “ADAR editing”)
- Placeholder terms like “lead candidate”, “undisclosed program”
- Any program not linked to a valid drug name

---

TEXT TO ANALYZE:
{content}
---
JSON:

"""

prompt_summarize_drug_data= """
You are a biomedical summarization assistant.

You are given a JSON object where each top-level key is a drug name, and its value contains structured fields including:
- mechanism_of_action
- indication
- preclinical_data
- clinical_trials
- upcoming_milestones
- references
- aliases

Your goal:
Transform this detailed JSON into a summarized version that keeps the exact structure but rewrites the content of each field into short, clear, and clinically meaningful bullet points.

Do:
- Rewrite each field into short, clear, and clinically meaningful bullet points.
- Deduplicate repetitive lines.
- Keep all drugs and all fields in the same structure.
- Keep JSON output valid (no markdown, no code blocks, no explanation).
- **Do not abbreviate or shorten URLs** — include full reference URLs as-is.

Do not:
- Omit any key or drug
- Add new information not present in the input
- Alter the field names or structure

Output Format (JSON only):
Return a valid JSON object like this:

{{
  "AMVUTTRA": {{
    "mechanism_of_action": ["RNAi therapeutic targeting TTR"],
    "indication": ["hATTR polyneuropathy and ATTR cardiomyopathy in adults"],
    "preclinical_data": [],
    "clinical_trials": [
      "FDA & ANVISA approval for ATTR-CM (March 2025)",
      "Initial NDA approved for hATTR; FDA delay due to inspection issues"
    ],
    "upcoming_milestones": [
      "EMA/PMDA decisions pending",
      "sNDA under review for label expansion"
    ],
    "references": [
      "10-Q, 2025-05-01, ITEM 1A",
      "https://www.sec.gov/.../alny-20250331.htm"
    ],
    "aliases": ["AMVUTTRA", "vutrisiran"]
  }},
}}
---
INPUT:
{json_blob}
"""


final_drug_info_schema = {
    "type": "object",
    "properties": {
        "drugs": {
            "type": "object",
            "patternProperties": {
                "^.*$": {  # each drug key
                    "type": "object",
                    "required": ["aliases"],
                    "properties": {
                        "aliases": {
                            "type": "array",
                            "items": {"type": "string"}
                        },
                        "mechanism_of_action": {"type": "array", "items": {"type": "string"}},
                        "target": {"type": "array", "items": {"type": "string"}},
                        "indication": {"type": "array", "items": {"type": "string"}},
                        "preclinical_data": {"type": "array", "items": {"type": "string"}},
                        "clinical_trials": {"type": "array", "items": {"type": "string"}},
                        "upcoming_milestones": {"type": "array", "items": {"type": "string"}},
                        "references": {"type": "array", "items": {"type": "string"}}
                    }
                }
            },
            "additionalProperties": False
        }
    },
    "required": ["drugs"]
}
