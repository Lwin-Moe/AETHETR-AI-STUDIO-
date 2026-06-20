import streamlit as st
import json
import base64

# ခွဲထုတ်ထားသော အကူဖိုင်များမှ Data သိမ်းဆည်းသည့်စနစ်များကို လှမ်းခေါ်ခြင်း
from utils.helpers import load_key, save_key

# --- 1. THEME & STYLING ---
st.set_page_config(page_title="AETHER STUDIO V52", layout="wide", page_icon="🎬")

st.markdown('''
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&family=Montserrat:wght@500;700;800;900&display=swap');
    
    /* 🔴 UI BUG FIX: Hide Streamlit Default Sidebar Navigation */
    [data-testid="stSidebarNav"] { display: none !important; }
    
    .stApp { background-color: #0b0f19 !important; background-image: radial-gradient(circle at top, #161b2e 0%, #0b0f19 60%) !important; color: #cbd5e1 !important; font-family: 'Inter', sans-serif; }
    section[data-testid="stSidebar"] { background-color: #0d111c !important; border-right: 1px solid rgba(255, 255, 255, 0.05) !important; }
    h1, h2, h3, h4 { font-family: 'Montserrat', sans-serif !important; color: #f8fafc !important; font-weight: 700 !important; }
    p, span, label, .stRadio label, .stCheckbox label, .stSelectbox label { color: #94a3b8 !important; font-size: 14px; }
    .main-title { text-align: center; font-family: 'Montserrat', sans-serif; font-size: 3.5rem !important; font-weight: 900; background: linear-gradient(135deg, #38bdf8 0%, #818cf8 50%, #c084fc 100%);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin-top: 20px; margin-bottom: 5px; letter-spacing: -1px; text-shadow: 0px 10px 30px rgba(129, 140, 248, 0.2); }
    .sub-title { text-align: center; color: #64748b; font-family: 'Inter', sans-serif; font-size: 1.1rem; font-weight: 500; margin-bottom: 40px; letter-spacing: 3px; text-transform: uppercase; }
    .stTextInput input, div[data-baseweb="select"], .stTextArea textarea { background-color: #151b2b !important; color: #f1f5f9 !important; border: 1px solid #334155 !important; border-radius: 8px !important; transition: all 0.3s ease; }
    .setting-panel { background: #111624; border: 1px solid rgba(255, 255, 255, 0.05); border-radius: 12px; padding: 24px; margin-bottom: 24px; box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2); }
    .stButton>button { background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%) !important; color: #ffffff !important; font-family: 'Montserrat', sans-serif !important; font-weight: 700 !important; font-size: 16px !important; border-radius: 8px !important; border: none !important; width: 100%; padding: 16px !important; transition: all 0.3s ease !important; box-shadow: 0 4px 15px rgba(124, 58, 237, 0.3); }
    .stButton>button:hover { transform: translateY(-3px); box-shadow: 0 8px 25px rgba(124, 58, 237, 0.5); }
    .sub-box { background-color: #1a2235; border: 1px solid rgba(129, 140, 248, 0.3); border-radius: 8px; padding: 20px; margin-top: 15px; margin-bottom: 10px; }
    </style>
''', unsafe_allow_html=True)

# State initialization (Global)
if "render_success" not in st.session_state: st.session_state.render_success = False
if "generated_script" not in st.session_state: st.session_state.generated_script = ""
if "original_transcript" not in st.session_state: st.session_state.original_transcript = ""
if "viral_title" not in st.session_state: st.session_state.viral_title = ""
if "viral_tags" not in st.session_state: st.session_state.viral_tags = ""
if "thumb_path_A" not in st.session_state: st.session_state.thumb_path_A = None
if "thumb_path_B" not in st.session_state: st.session_state.thumb_path_B = None
if "viral_score" not in st.session_state: st.session_state.viral_score = ""
if "final_video_path" not in st.session_state: st.session_state.final_video_path = ""

# --- UI INTERFACE & NAVIGATION ---
st.markdown('<div class="main-title">AETHER FILMWORKS</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">AI Studio V52 ⚡ SaaS Edition</div>', unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### 🧭 Navigation Menu")
    app_mode = st.radio("Select Studio Mode:", ["🎙️ Movie Dubbing Studio", "🎙️ Faceless Channel Studio", "🎥 Veo Video Studio", "🎵 Lyria Music Studio"])
    st.markdown("---")

    st.markdown("### 💾 Project Save & Load")
    if st.button("Save Current Project"):
        proj_data = {
            "script": st.session_state.generated_script,
            "title": st.session_state.viral_title,
            "tags": st.session_state.viral_tags
        }
        json_str = json.dumps(proj_data, ensure_ascii=False)
        b64 = base64.b64encode(json_str.encode('utf-8')).decode()
        href = f'<a href="data:application/json;base64,{b64}" download="Aether_Project.json" style="color:#38bdf8; font-weight:bold;">📥 Download Project File (.json)</a>'
        st.markdown(href, unsafe_allow_html=True)

    uploaded_proj = st.file_uploader("Upload Project", type=["json"])
    if uploaded_proj:
        try:
            data = json.load(uploaded_proj)
            st.session_state.generated_script = data.get("script", "")
            st.session_state.viral_title = data.get("title", "")
            st.session_state.viral_tags = data.get("tags", "")
            st.success("✅ Project Loaded!")
        except Exception:
            st.error("Invalid Project File.")

    st.markdown("---")
    st.markdown("### 🔑 Global API Keys")
    ai_provider = st.selectbox("Choose Main AI", ["Google Gemini (Flash)", "OpenAI (GPT-5.5 Pro)", "Groq API (Fast)"])
    
    saved_gemini = load_key("GEMINI_API_KEY")
    api_key_input = st.text_input("Main AI API Key", type="password", value=saved_gemini)
    if api_key_input and api_key_input != saved_gemini: save_key("GEMINI_API_KEY", api_key_input)
    
    # Whisper Sync အတွက် Groq က မပါမဖြစ်လိုအပ်လာပါပြီ
    saved_groq_fc = load_key("GROQ_API_KEY")
    groq_key_fc = st.text_input("Groq API Key (For Whisper Word-Sync)", type="password", value=saved_groq_fc)
    if groq_key_fc and groq_key_fc != saved_groq_fc: save_key("GROQ_API_KEY", groq_key_fc)

# =====================================================================
# 📌 DYNAMIC PAGE ROUTING
# =====================================================================
if app_mode == "🎙️ Movie Dubbing Studio":
    from pages.movie_dubbing import render_movie_dubbing_studio
    # Groq Key ကိုပါ Movie Dubbing အတွက် ပေးပို့မည်
    render_movie_dubbing_studio(api_key_input, saved_gemini, ai_provider, groq_key_fc)
    
elif app_mode == "🎙️ Faceless Channel Studio":
    from pages.faceless_channel import render_faceless_studio
    render_faceless_studio(api_key_input, saved_gemini, groq_key_fc)
    
elif app_mode == "🎥 Veo Video Studio":
    st.markdown('<div class="setting-panel"><h3>🎥 Veo 3.0 Cinematic Video Generator</h3>', unsafe_allow_html=True)
    video_prompt = st.text_area("🎬 Enter Video Prompt", placeholder="A cinematic slow-motion drone shot...")
    if st.button("🚀 Generate Veo Video"): pass
    
elif app_mode == "🎵 Lyria Music Studio":
    st.markdown('<div class="setting-panel"><h3>🎵 Lyria 3 Pro Music Generator</h3>', unsafe_allow_html=True)
    music_prompt = st.text_area("🎧 Enter Music Prompt", placeholder="Epic cinematic background music...")
    if st.button("🚀 Generate Lyria Music"): pass
