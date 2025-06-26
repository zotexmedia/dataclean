import re

import pandas as pd
import streamlit as st
from rapidfuzz import fuzz, process

# -----------------------------------------------------------
# Cleaning utilities
# -----------------------------------------------------------
# Regex‑ready suffixes that should be cut from the end of names
LEGAL_SUFFIX_PATTERNS = [
    r'incorporated', r'inc\.?',
    r'llc', r'l\.l\.c\.?',
    r'company', r'co\.?', r'corp\.?', r'corporation',
    r'limited', r'ltd\.?', r'plc',
    r'gmbh', r's\.a\.?', r'bv', r'b\.v\.?', r'ag',
    # Professional / medical markers
    r'dds', r'dmd',
    r'p\.a\.?', r'p\s*a', r'pa',
    r'm\.d\.?', r'm\s*d', r'md',
]

SUFFIX_RE = re.compile(r"\s+(?:" + "|".join(LEGAL_SUFFIX_PATTERNS) + r")\s*$", re.IGNORECASE)
# Keep ampersand (&) so tokens like "H&H" survive. Hyphen kept initially, stripped later.
NON_ALNUM_RE = re.compile(r"[^\w\s&-]")
MULTISPACE_RE = re.compile(r"\s{2,}")
APOSTROPHE_RE = re.compile(r"[’']")

STATE_CODES = {
    'al', 'ak', 'az', 'ar', 'ca', 'co', 'ct', 'de', 'fl', 'ga', 'hi', 'id', 'il', 'in', 'ia', 'ks', 'ky',
    'la', 'me', 'md', 'ma', 'mi', 'mn', 'ms', 'mo', 'mt', 'ne', 'nv', 'nh', 'nj', 'nm', 'ny', 'nc', 'nd',
    'oh', 'ok', 'or', 'pa', 'ri', 'sc', 'sd', 'tn', 'tx', 'ut', 'vt', 'va', 'wa', 'wv', 'wi', 'wy'
}


def _smart_case(word: str) -> str:
    """Return a word in a visually sensible case."""
    if word.isupper():
        return word
    if len(word) == 2 and word.lower() in STATE_CODES:
        return word.upper()
    if len(word) <= 3 and word.isalpha():
        return word.upper()
    return word.title()


def clean_company_name(name: str) -> str:
    """Clean and normalise a single company name string."""
    if pd.isna(name):
        return ""

    name = str(name)
    name = APOSTROPHE_RE.sub("", name)                      # remove apostrophes

    # Replace *spaced* ampersand with "and" ("A & B" → "A and B").
    name = re.sub(r"\s&\s", " and ", name)

    name = NON_ALNUM_RE.sub(" ", name)                     # drop punctuation except & and ‑
    name = name.replace("-", " ")                         # hyphen → space
    name = MULTISPACE_RE.sub(" ", name).strip()            # collapse whitespace
    name = SUFFIX_RE.sub("", name).strip()                 # strip legal / prof suffixes

    tokens = [_smart_case(tok) for tok in name.split()]
    return " ".join(tokens)


# -----------------------------------------------------------
# Fuzzy deduplication helper
# -----------------------------------------------------------

def fuzzy_deduplicate(series: pd.Series, threshold: int = 92) -> pd.Series:
    known, out = [], []
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
Upload a CSV, pick the column with company names, and download a cleaned version.

**Key rules**
* Apostrophes removed (*Danny's → Dannys*)
* Plain **&** kept inside tokens (so *H&H* stays *H&H*). Only " & " with spaces becomes **and**
* Legal/prof suffixes (Inc, LLC, DDS, MD, P A …) stripped
* Punctuation removed, hyphens → space
* Smart casing keeps acronyms / state codes upper‑case
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

    cols = df.columns.tolist()
    default_idx = next((i for i, c in enumerate(cols) if "company" in c.lower()), 0)
    col = st.selectbox("Column with company names", cols, index=default_idx)

    use_fuzzy = st.checkbox("Fuzzy deduplicate similar names", value=False)
    thresh = st.slider("Similarity threshold", 80, 100, 92, disabled=not use_fuzzy)

    with st.spinner("Cleaning names…"):
        df["Cleaned Company Name"] = df[col].astype(str).map(clean_company_name)
        if use_fuzzy:
            df["Canonical Company Name"] = fuzzy_deduplicate(df["Cleaned Company Name"], threshold=thresh)

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

    st.markdown(
        """
---
Need another edge‑case handled? Add it to `LEGAL_SUFFIX_PATTERNS`, adapt the ampersand
rule, or ping me and I’ll patch it!
"""
    )
