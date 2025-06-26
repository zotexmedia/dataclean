import re

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

SUFFIX_RE = re.compile(r"\s+(?:" + "|".join(LEGAL_SUFFIX_PATTERNS) + r")\s*$", re.IGNORECASE)
NON_ALNUM_RE = re.compile(r"[^\w\s-]")
MULTISPACE_RE = re.compile(r"\s{2,}")
APOSTROPHE_RE = re.compile(r"[’']")


def clean_company_name(name: str) -> str:
    """Clean and standardise a single company name."""
    if pd.isna(name):
        return ""

    name = str(name)
    name = APOSTROPHE_RE.sub("", name)           # Gilmer's → Gilmers
    name = name.replace("&", " and ")            # & → and
    name = NON_ALNUM_RE.sub(" ", name)            # drop punctuation (keep hyphen for now)
    name = name.replace("-", " ")                # hyphen → space
    name = MULTISPACE_RE.sub(" ", name).strip()   # collapse spaces
    name = SUFFIX_RE.sub("", name).strip()        # strip legal suffixes

    # Title‑case while preserving acronyms (ALL‑CAPS words)
    tokens = [t if t.isupper() else t.title() for t in name.split()]
    return " ".join(tokens)


# -----------------------------------------------------------
# Fuzzy deduplication helper
# -----------------------------------------------------------

def fuzzy_deduplicate(series: pd.Series, threshold: int = 92) -> pd.Series:
    """Group near‑duplicate names using RapidFuzz token‑set ratio."""
    known: list[str] = []
    out: list[str] = []

    for n in series:
        if not n:
            out.append(n)
            continue
        match = process.extractOne(n, known, scorer=fuzz.token_set_ratio)
        if match and match[1] >= threshold:
            canonical = match[0]
        else:
            canonical = n
            known.append(n)
        out.append(canonical)

    return pd.Series(out, index=series.index)


# -----------------------------------------------------------
# Streamlit Interface
# -----------------------------------------------------------

st.set_page_config(page_title="CSV Company Name Cleaner", page_icon="🧹", layout="centered")

st.title("🧹 CSV Company Name Cleaner")

st.markdown(
    """
Upload a CSV, choose the column containing company names, and download a cleaned file.

**Cleaning rules**
* Apostrophes removed (*Gilmer's → Gilmers*)
* Ampersand becomes **and**
* Legal suffixes (Inc, LLC, Corp, …) dropped
* Punctuation stripped, hyphens → space
* Smart title‑casing (acronyms preserved)
* Optional fuzzy de‑duplication (RapidFuzz)
"""
)

uploaded = st.file_uploader("Upload CSV", type=["csv"])

if uploaded is not None:
    try:
        df = pd.read_csv(uploaded)
    except Exception as e:
        st.error(f"❌ Could not read CSV: {e}")
        st.stop()

    columns = df.columns.tolist()
    default_idx = next((i for i, c in enumerate(columns) if "company" in c.lower()), 0)
    col = st.selectbox("Column with company names", columns, index=default_idx)

    use_fuzzy = st.checkbox("Fuzzy deduplicate similar names", value=False)
    thresh = st.slider("Similarity threshold", 80, 100, 92, disabled=not use_fuzzy)

    with st.spinner("Cleaning names…"):
        df["Cleaned Company Name"] = df[col].astype(str).map(clean_company_name)
        if use_fuzzy:
            df["Canonical Company Name"] = fuzzy_deduplicate(df["Cleaned Company Name"], threshold=thresh)

    st.success("✅ Cleaning complete!")

    st.markdown("### Preview (first 25 rows)")
    st.dataframe(df.head(25))

    csv_bytes = df.to_csv(index=False).encode("utf‑8")
    st.download_button(
        label="Download cleaned CSV",
        data=csv_bytes,
        file_name=f"cleaned_{uploaded.name}",
        mime="text/csv",
    )

    st.markdown(
        """
---
If you spot a suffix or pattern that isn't handled, just add it to
`LEGAL_SUFFIX_PATTERNS` and redeploy — or ping me and I'll patch it!
"""
    )
