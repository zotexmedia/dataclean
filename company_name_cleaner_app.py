import re
from pathlib import Path

import pandas as pd
import streamlit as st
from rapidfuzz import fuzz, process

# -----------------------------
# Utility ‑ Cleaning Functions
# -----------------------------
SUFFIXES = {
    "inc", "inc.", "llc", "l.l.c.", "co", "co.", "corp", "corporation", "limited",
    "ltd", "ltd.", "plc", "gmbh", "pte", "pty", "sa", "s.a.", "bv", "b.v.", "ag",
}

SPECIAL_CHARS_PATTERN = re.compile(r"[^\w\s]")
MULTISPACE_PATTERN = re.compile(r"\s{2,}")


def clean_company_name(name: str) -> str:
    """Basic deterministic cleaning for a single company name."""
    if pd.isna(name):
        return ""

    # Normalize whitespace, strip special chars, lowercase
    name = SPECIAL_CHARS_PATTERN.sub(" ", name.lower())
    name = MULTISPACE_PATTERN.sub(" ", name).strip()

    # Remove common legal suffixes
    words = [w for w in name.split() if w not in SUFFIXES]

    # Re‑title‑case but keep uppercase words (e.g., IBM)
    cleaned = " ".join(word.upper() if word.isupper() else word.title() for word in words)
    return cleaned


# -----------------------------
# Fuzzy Deduplication Helpers
# -----------------------------

def fuzzy_deduplicate(names: pd.Series, threshold: int = 90) -> pd.Series:
    """Group names that are similar above the threshold and assign the canonical form."""
    canonical_map = {}
    cleaned_list = names.tolist()

    for idx, original in enumerate(cleaned_list):
        if idx in canonical_map:  # already assigned
            continue

        # Find similar names
        matches = process.extractBests(original, cleaned_list, scorer=fuzz.token_set_ratio, score_cutoff=threshold)
        for match_name, _score, match_idx in matches:
            canonical_map[match_idx] = original  # Assign canonical representative

    # Build new series with canonical names
    canonical_series = pd.Series([canonical_map.get(i, name) for i, name in enumerate(cleaned_list)])
    return canonical_series


# -----------------------------
# Streamlit Interface
# -----------------------------
st.set_page_config(page_title="CSV Company Name Cleaner", page_icon="🧹", layout="centered")
st.title("🧹 CSV Company Name Cleaner")
st.markdown(
    """
This tool cleans and standardises *Company Name* fields in your CSV files.
- **Legal suffix removal** (Inc, LLC, Corp, …)
- **Special‑character stripping**
- **Whitespace / casing fixes**
- **Optional fuzzy deduplication** using RapidFuzz (token‑set‑ratio)
    """
)

uploaded = st.file_uploader("Upload CSV", type=["csv"])

if uploaded is not None:
    try:
        df = pd.read_csv(uploaded)
    except Exception:
        st.error("❌ Could not read the CSV. Please ensure it's a valid file.")
        st.stop()

    # Let user select the column containing company names
    cols = df.columns.tolist()
    default_col = next((c for c in cols if "company" in c.lower()), cols[0])
    name_col = st.selectbox("Select the column with company names", cols, index=cols.index(default_col))

    st.markdown("### Cleaning parameters")
    do_fuzzy = st.checkbox("Apply fuzzy deduplication", value=False)
    threshold = st.slider("Similarity threshold (higher = stricter)", 70, 100, 90, disabled=not do_fuzzy)

    # Perform cleaning
    with st.spinner("Cleaning names ..."):
        df["Cleaned Company Name"] = df[name_col].astype(str).apply(clean_company_name)
        if do_fuzzy:
            df["Canonical Company Name"] = fuzzy_deduplicate(df["Cleaned Company Name"], threshold=threshold)

    st.success("✅ Cleaning complete!")

    # Show preview
    st.markdown("### Preview (first 25 rows)")
    st.dataframe(df.head(25))

    # Download button
    out_file = Path("cleaned_" + uploaded.name)
    df.to_csv(out_file, index=False)
    st.download_button(
        label="Download cleaned CSV",
        data=out_file.read_bytes(),
        file_name=out_file.name,
        mime="text/csv",
    )

    st.markdown("---")
    st.markdown(
        "#### Tips:\n- If you enable fuzzy deduplication, similar names (≥ threshold) map to the first appearance.\n- You can re‑upload the cleaned file for additional passes if needed."
    )
