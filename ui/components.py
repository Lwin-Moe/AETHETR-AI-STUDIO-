import os
import shutil
import subprocess
import urllib.request
import streamlit as st

def setup_fonts_and_css():
    local_font_path = "Padauk.ttf"
    if not os.path.exists(local_font_path):
        try:
            urllib.request.urlretrieve("https://github.com/google/fonts/raw/main/ofl/padauk/Padauk-Regular.ttf", local_font_path)
        except Exception:
            pass

    _fonts_dir = os.path.expanduser("~/.fonts")
    os.makedirs(_fonts_dir, exist_ok=True)
    _sys_font = os.path.join(_fonts_dir, "Padauk.ttf")
    if not os.path.exists(_sys_font) and os.path.exists(local_font_path):
        try:
            shutil.copy(local_font_path, _sys_font)
            subprocess.run(["fc-cache", "-f", "-v"], capture_output=True)
        except Exception:
            pass

    st.markdown('''
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&family=Montserrat:wght@500;700;800;900&display=swap');
        .stApp { background-color: #0b0f19 !important; background-image: radial-gradient(circle at top, #161b2e 0%, #0b0f19 60%) !important; color: #cbd5e1 !important; font-family: 'Inter', sans-serif; }
        section[data-testid="stSidebar"] { background-color: #0d111c !important; border-right: 1px solid rgba(255, 255, 255, 0.05) !important; }
        h1, h2, h3, h4 { font-family: 'Montserrat', sans-serif !important; color: #f8fafc !important; font-weight: 700 !important; }
        p, span, label, .stRadio label, .stCheckbox label, .stSelectbox label { color: #94a3b8 !important; font-size: 14px; }
        .main-title { text-align: center; font-family: 'Montserrat', sans-serif; font-size: 3.5rem !important; font-weight: 900; background: linear-gradient(135deg, #38bdf8 0%, #818cf8 50%, #c084fc 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin-top: 20px; margin-bottom: 5px; letter-spacing: -1px; text-shadow: 0px 10px 30px rgba(129, 140, 248, 0.2); }
        .sub-title { text-align: center; color: #64748b; font-family: 'Inter', sans-serif; font-size: 1.1rem; font-weight: 500; margin-bottom: 40px; letter-spacing: 3px; text-transform: uppercase; }
        .stTextInput input, div[data-baseweb="select"], .stTextArea textarea { background-color: #151b2b !important; color: #f1f5f9 !important; border: 1px solid #334155 !important; border-radius: 8px !important; transition: all 0.3s ease; }
        .setting-panel { background: #111624; border: 1px solid rgba(255, 255, 255, 0.05); border-radius: 12px; padding: 24px; margin-bottom: 24px; box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2); }
        .stButton>button { background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%) !important; color: #ffffff !important; font-family: 'Montserrat', sans-serif !important; font-weight: 700 !important; font-size: 16px !important; border-radius: 8px !important; border: none !important; width: 100%; padding: 16px !important; transition: all 0.3s ease !important; box-shadow: 0 4px 15px rgba(124, 58, 237, 0.3); }
        .stButton>button:hover { transform: translateY(-3px); box-shadow: 0 8px 25px rgba(124, 58, 237, 0.5); }
        .sub-box { background-color: #1a2235; border: 1px solid rgba(129, 140, 248, 0.3); border-radius: 8px; padding: 20px; margin-top: 15px; margin-bottom: 10px; }
        </style>
    ''', unsafe_allow_html=True)