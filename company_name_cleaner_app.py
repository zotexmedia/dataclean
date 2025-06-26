import re

import pandas as pd
import streamlit as st
from rapidfuzz import fuzz, process

# -----------------------------------------------------------
# Cleaning utilities
# -----------------------------------------------------------
LEGAL_SUFFIX_PATTERNS = [
    r'incorporated', r'inc\.?',
    r'llc', r'l\.l\.c\.?',
    r'company', r'corp\.?', r'corporation',
    r'limited', r'ltd\.?', r'plc',
    r'gmbh', r's\.a\.?', r'bv', r'b\.v\.?', r'ag',
    # Professional / medical markers
    r'dds', r'dmd',
    r'p\.a\.?', r'p\s*a', r'pa',
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

STOPWORDS_LOWER = {
    'of', 'and', 'the', 'for', 'in', 'on', 'at', 'with', 'to', 'from', 'by'
}

ACRONYM_EXCEPTIONS = {
    'usa', 'bsn', 'ibm', 'uams', 'uapb', 'mri', 'ct'
}


def _smart_case(word: str) -> str:
    """Return a word in appropriate case.

    * Always lowercase stop‑words (of, and, …) regardless of position.
    * Preserve two‑letter state codes (AR, TX) and whitelisted acronyms.
    * Everything else title‑cased, keeping hyphenated parts.
    """
    low = word.lower()

    # Force stop‑words to lowercase everywhere
    if low in STOPWORDS_LOWER:
        return low

    # Preserve state abbreviations
    if len(word) == 2 and low in STATE_CODES:
        return word.upper()

    # Preserve whitelisted acronyms (all‑caps tokens in the exceptions list)
    if word.isupper() and low in ACRONYM_EXCEPTIONS:
        return word

    # Otherwise Title‑case, handling hyphenated compounds
    return "-".join(part.capitalize() for part in word.split("-"))


def clean_company_name(name: str) -> str:
    if pd.isna(name):
        return ""

    name = str(name)
    name = APOSTROPHE_RE.sub("", name)
    name = NON_ALNUM_RE.sub(" ", name)
    name = MULTISPACE_RE.sub(" ", name).strip()

    # Strip legal / professional suffixes (not touching standalone 'Co' here)
    name = SUFFIX_RE.sub("", name).strip()

    # Remove trailing 'Co' / 'Co.' unless preceded by '&'
    if not re.search(r"&\s+co\.?$", name, re.IGNORECASE):
        name = re.sub(r"\s+co\.?$", "", name, flags=re.IGNORECASE)

    tokens = name.split()
    styled = [_smart_case(tok) for tok in tokens]

    # Restore '& Co' if we accidentally trimmed 'Co' after an ampersand
    if styled and styled[-1] == '&':
        styled.append('Co')

    return " " . join(styled)


# -----------------------------------------------------------
# Fuzzy deduplication helper
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
# Streamlit Interface
# -----------------------------------------------------------

st.set_page_config(page_title="CSV Company Name Cleaner", page_icon="🧹", layout="centered")

st.title("🧹 CSV Company Name Cleaner")

st.markdown(
    """
Upload a CSV, pick the column with company names, and download a cleaned version.

**Latest fix**
* Stop‑words (*of, and, the…*) now always remain lowercase—no more stray caps.
* Other rules unchanged (ampersands/hyphens kept, suffixes removed, smart acronyms, optional fuzzy dedupe).
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
Need more tweaks? Just ask and we’ll refine further.
"""
    )
