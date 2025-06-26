import re
from pathlib import Path

import pandas as pd
import streamlit as st
from rapidfuzz import fuzz, process

# -----------------------------------------------------------
# Cleaning utilities
# -----------------------------------------------------------
LEGAL_SUFFIX_PATTERNS = [
    r'incorporated',
    r'inc\.?',
    r'llc',
    r'l\.l\.c\.?',
    r'company',
    r'co\.?',
    r'corp\.?',
    r'corporation',
    r'limited',
    r'ltd\.?',
    r'plc',
    r'gmbh',
    r's\.a\.?',
    r'bv',
    r'b\.v\.?',
    r'ag',
]

SUFFIX_RE = re.compile(r"\s+(?:" + "|".join(LEGAL_SUFFIX_PATTERNS) + r")\s*$", flags=re.IGNORECASE)
# apostrophes are handled separately so they don't turn into spaces
NON_ALNUM_RE = re.compile(r"[^\w\s-]")  # keep hyphens initially, strip later
MULTISPACE_RE = re.compile(r"\s{2,}")
APOSTROPHE_RE = re.compile(r"[’']")


def clean_company_name(name: str) -> str:
    """Return a normalised company name with legal suffixes and punctuation removed.

    Steps:
    1. Remove apostrophes ("Gilmer's" -> "Gilmers")
    2. Replace ampersands with textual "and"
    3. Remove all non‑alphanumeric chars (we keep hyphens for now)
    4. Convert hyphens to space to merge words
    5. Collapse multiple spaces and strip
    6. Strip legal suffixes (Inc, LLC, etc.)
    7. Smart title‑case while preserving acronyms (ALL‑CAPS words)
    """
    if pd.isna(name):
        return ""

    name = str(name)
    # 1. Apostrophes -> remove (don't introduce space)
    name = APOSTROPHE_RE.sub("", name)
    # 2. & -> and (keeps meaning, better dedupe)
    name = name.replace("&", " and ")
    # 3. Remove punctuation except hyphen
    name = NON_ALNUM_RE.sub(" ", name)
    # 4. Hyphen -> space
    name = name.replace("-", " ")
    # 5. Collapse spaces
    name = MULTISPACE_RE.sub(" ", name).strip()
    # 6. Strip legal suffixes at end
    name = SUFFIX_RE.sub("", name).strip()
    # 7. Title‑case preserving acronyms
    tokens = [(t if t.isupper() else t.title()) for t in name.split()]
    return " ".join(tokens)


# -----------------------------------------------------------
# Fuzzy deduplication helper (RapidFuzz ≥ 3.x)
# -----------------------------------------------------------

def fuzzy_deduplicate(series: pd.Series, threshold: int = 92) -> pd.Series:
    """Map near‑duplicate names to a single canonical representative.

    Uses token‑set ratio; threshold default 92 (tunable via slider).
    """
    known: list[str] = []
    output: list[str] = []

    for name in series:
        if not name:
            output.append(name)
            continue

        match = process.extractOne(name, known, scorer=fuzz.token_set_ratio)
        if match and match[1] >= threshold:
            canonical = match[0]
        else:
            canonical = name
            known.append(name)
        output.append(canonical)

    return pd.Series(output, index=series.index)


# -----------------------------------------------------------
# Streamlit UI
# -----------------------------------------------------------
st.set_page_config(page_title="CSV Company Name Cleaner", page_icon="🧹", layout="centered")

st.title("🧹 CSV Company Name Cleaner")

st.markdown(
    """
Upload a CSV, pick the column that holds company names, and download a cleaned
version.

**Cleaning rules**
* Apostrophes removed ("Gilmer's" → "Gilmers")
* Ampersand becomes "and" (better matching)
* Legal suffixes (Inc, LLC, Corp, …) dropped
* Punctuation / weird characters stripped, hyphens → space
* Names smart‑title‑cased (acronyms preserved)
* *Optional* fuzzy deduplication (RapidFuzz)
    """
)

uploaded = st.file_uploader("Upload CSV", type=["csv"])

if uploaded:
    try:
        df = pd.read_csv(uploaded)
    except Exception as e:
        st.error(f"❌ Could not read CSV: {e}")
        st.stop()

    cols = df.columns.tolist()
    default_idx = next((i for i, c in enumerate(cols) if "company" in c.lower()), 0)
    col_choice = st.selectbox("Column with company names", cols, index=default_idx)

    fuzzy_opt = st.checkbox("Fuzzy deduplicate similar names", value=False)
    threshold = st.slider("Similarity threshold", 80, 100, 92, disabled=not fuzzy_opt)

    with st.spinner("Cleaning names…"):
        df["Cleaned Company Name"] = df[col_choice].astype(str).map(clean_company_name)
        if fuzzy_opt:
            df["Canonical Company Name"] = fuzzy_deduplicate(df["Cleaned Company Name"], threshold=threshold)

    st.success("✅ Cleaning complete!")

    st.markdown("### Preview (first 25 rows)")
    st.dataframe(df.head(25))

    csv_data = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download cleaned CSV",
        data=csv_data,
        file_name=f"cleaned_{uploaded.name}",
        mime="text/csv",
    )

    st.markdown(
        "---\nIf you spot any suffix or pattern that isn't getting cleaned, add it to
        `LEGAL_SUFFIX_PATTERNS` and redeploy—or let me know and I'll patch it!"
    )
