"""Truebind entrypoint: multi-page Streamlit app.

  - Upload & Process  -- today's upload -> map -> validate -> download flow
  - Leakage & Duplicates -- Truebind 2.1
  - Compliance & Audit -- Truebind 2.2

Run: streamlit run app.py
"""

from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="Truebind", layout="wide", page_icon="📋")

pages = [
    st.Page("upload_and_process.py", title="Upload & Process", icon="📋", default=True),
    st.Page("leakage_dashboard.py", title="Leakage & Duplicates", icon="💰"),
    st.Page("compliance_audit.py", title="Compliance & Audit", icon="🛡️"),
]

st.navigation(pages).run()
