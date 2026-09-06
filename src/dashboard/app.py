import streamlit as st

from utils.db import get_companies

st.set_page_config(
    page_title="Nifty 100 Analytics",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("Nifty 100 Financial Intelligence Platform")
st.caption("Use the sidebar to navigate the 8 analytics screens.")

companies = get_companies()
c1, c2, c3 = st.columns(3)
c1.metric("Companies", len(companies))
c2.metric("Broad Sectors", companies["broad_sector"].nunique())
c3.metric("Sub-Sectors", companies["sub_sector"].nunique())