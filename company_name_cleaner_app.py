import re

import pandas as pd
import streamlit as st
from rapidfuzz import fuzz, process

# -----------------------------------------------------------
# Cleaning utilities
# -----------------------------------------------------------
LEGAL_SUFFIX_PATTERNS = [
    # Common corporate/legal endings
    r'incorporated', r'inc\.?',
    r'llc', r'l\.l\.c\.?',
    r'company', r'co\.?',
    r'corp\.?', r'corporation',
    r'limited', r'ltd\.?', r'plc',
    r'gmbh', r's\.a\.?', r'bv', r'b\.v\.?', r'ag',
    # Professional / medical markers
    r'dds', r'dmd',
    r'p\.c\.?', r'p\s*c', r'pc',   # professional corporation
    r'p\.a\.?', r'p\s*a', r'pa',    # professional association
    r'llp', r'l\.l\.p\.?',         # limited liability partnership
    r'm\.d\.?', r'm\s*d', r'md',
]

SUFFIX_RE = re.compile(r"\s+(?:" + "|".join(LEGAL_SUFFIX_PATTERNS) + r")\s*$", re.IGNORECASE)
NON_ALNUM_RE = re.compile(r"[^\w\s&-]")   # keep & and hyphen
MULTISPACE_RE = re.compile(r"\s{2,}")
APOSTROPHE_RE = re.compile(r"[’']")

STATE_CODES = {
    'al', 'ak', 'az', 'ar', 'ca', 'co', 'ct', 'de', 'fl', 'ga', 'hi', 'id', 'il', 'in', 'ia', 'ks', 'ky',
    'la', 'me', 'md', 'ma', 'mi', 'mn', 'ms', 'mo', 'mt', 'ne', 'nv', 'nh', 'nj', 'nm', 'ny', 'nc', 'nd',
    'oh', 'ok', 'or', 'pa', 'ri', 'sc', 'sd', 'tn', 'tx', 'ut', 'vt', 'va', 'wa', 'wv', 'wi', 'wy'
}

STOPWORDS = {
    'of', 'and', 'the', 'for', 'in', 'on', 'at', 'with', 'to', 'from', 'by'
}

ACRONYM_WHITELIST = {
    'usa', 'bsn', 'ibm', 'uams', 'uapb', 'mri', 'ct', 'ltb'  # custom acronyms stay uppercase
}


def _smart_case(word: str, first: bool) -> str:
    """Return word with correct casing using custom rules.

    * Stop‑words lowercase **unless** they are the first token (keep title case for names like "The Barcode Group").
    * Preserve two‑letter state codes and whitelisted acronyms in uppercase.
    * Otherwise Title‑case (handling hyphens).
    """
    low = word.lower()

    # Stop‑word logic
    if low in STOPWORDS:
        return word.capitalize() if first else low

    # State abbreviations
    if len(word) == 2 and low in STATE_CODES:
        return word.upper()

    # Whitelisted acronyms
    if word.isupper() and low in ACRONYM_WHITELIST:
        return word

    # Default Title‑case (handle hyphenated parts)
    return "-".join(part.capitalize() for part in word.split("-"))


def clean_company_name(name: str) -> str:
    if pd.isna(name):
        return ""

    name = str(name)
    name = APOSTROPHE_RE.sub("", name)
    name = NON_ALNUM_RE.sub(" ", name)
    name = MULTISPACE_RE.sub(" ", name).strip()

    name = SUFFIX_RE.sub("", name).strip()

    # Remove trailing 'Co' unless preceded by '&'
    if not re.search(r"&\s+co\.?$", name, re.IGNORECASE):
        name = re.sub(r"\s+co\.?$", "", name, flags=re.IGNORECASE)

    tokens = name.split()
    styled = [_smart_case(tok, i == 0) for i, tok in enumerate(tokens)]

    if styled and styled[-1] == '&':
        styled.append('Co')

    return " ".join(styled)


# -----------------------------------------------------------
# Fuzzy de‑duplication helper
# -----------------------------------------------------------

def fuzzy_deduplicate(series: pd.Series, threshold: int = 92) -> pd.Series:
    known, out = [], []
    for value in series:
        if not value:
            out.append(value)
            continue
        match = process.extractOne(value, known, scorer=fuzz.token_set_ratio)
        if match and match[1] >= threshold:
            canonical = match[0]
        else:
            canonical = value
            known.append(value)
        out.append(canonical)
    return pd.Series(out, index=series.index)


# -----------------------------------------------------------
# Streamlit Interface (unchanged)
# -----------------------------------------------------------

st.set_page_config(page_title="CSV Company Name Cleaner", page_icon="🧹", layout="centered")

st.title("🧹 CSV Company Name Cleaner")

st.markdown(
    """
Upload a CSV, pick the column with company names, and download a cleaned file.

* Hyphens and ampersands preserved (e.g., **Jan‑Pro**, **H&H**, **Eldredge & Clark**)
* Legal/prof suffixes removed (Inc, LLC, LLP, PC, DDS, …)
* Stop‑words lowercase inside the name but capitalised if first (The Barcode Group)
* State codes and whitelisted acronyms stay uppercase (LTB, USA…)
* **Optional fuzzy de‑duplication** to group near‑identical names into a *Canonical Company Name* column
"""
)

uploaded = st.file_uploader("Upload CSV", type=["csv"])

if uploaded is not None:
    try:
        df = pd.read_csv(uploaded)
    except Exception as e:
        st.error(f"❌ Could not read CSV: {e}")
        st.stop()

    cols = df.columns.tolist()
    default_idx = next((i for i, c in enumerate(cols) if "company" in c.lower()), 0)
    col = st.selectbox("Column with company names", cols, index=default_idx)

    use_dedupe = st.checkbox("Apply fuzzy de‑duplication", value=False)
    threshold = st.slider("Similarity threshold", 80, 100, 92, disabled=not use_dedupe)

    with st.spinner("Cleaning names…"):
        df["Cleaned Company Name"] = df[col].astype(str).map(clean_company_name)
        if use_dedupe:
            df["Canonical Company Name"] = fuzzy_deduplicate(df["Cleaned Company Name"], threshold)

    st.success("✅ Cleaning complete!")

    st.markdown("### Preview (first 25 rows)")
    st.dataframe(df.head(25))

    csv_bytes = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download cleaned CSV",
        data=csv_bytes,
        file_name=f"cleaned_{uploaded.name}",
        mime="text/csv",
    )

    st.markdown("---\nNeed more tweaks? Just ask and we’ll refine further.")
