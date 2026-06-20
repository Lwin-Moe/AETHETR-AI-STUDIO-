import os
import base64
import urllib.request
from dotenv import load_dotenv, set_key

# --- SECURITY UPGRADE: Environment Variables (.env) ---
ENV_FILE = ".env"
load_dotenv(ENV_FILE)

def download_default_font():
    """Default Font ဖြစ်သော Padauk.ttf မရှိပါက ဒေါင်းလုဒ်ဆွဲပေးမည်"""
    local_font_path = "Padauk.ttf"
    if not os.path.exists(local_font_path):
        try:
            urllib.request.urlretrieve("https://github.com/google/fonts/raw/main/ofl/padauk/Padauk-Regular.ttf", local_font_path)
        except Exception:
            pass

def get_available_fonts():
    """font folder ထဲရှိ .ttf ဖိုင်များကို ရှာဖွေပေးမည်"""
    download_default_font()
    font_list = ["Padauk.ttf"]
    if os.path.exists("font"):
        for f in os.listdir("font"):
            if f.endswith(".ttf") or f.endswith(".otf"):
                font_list.append(os.path.join("font", f))
    return list(set(font_list))

def load_key(key_name):
    """.env မှ Key ကို လုံခြုံစွာ ခေါ်ယူမည်"""
    return os.getenv(key_name, "")

def save_key(key_name, key_value):
    """.env ထဲသို့ လုံခြုံစွာ သိမ်းဆည်းမည်"""
    if not os.path.exists(ENV_FILE):
        open(ENV_FILE, 'w').close()
    set_key(ENV_FILE, key_name, key_value)
    os.environ[key_name] = key_value

def get_download_link(file_path, file_name, link_text):
    if not os.path.exists(file_path):
        return ""
    with open(file_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return f'<a href="data:application/octet-stream;base64,{b64}" download="{file_name}" style="display:block; text-align:center; margin-top:10px; padding:12px 20px; background:linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%); color:white; text-decoration:none; border-radius:8px; font-weight:bold;"> 📥  {link_text}</a>'

def cleanup_temp_files():
    """Rendering ပြီးတိုင်း မလိုအပ်သော ဖိုင်အကြွင်းအကျန်များကို ဖျက်ပစ်မည်"""
    for f in os.listdir("."):
        if f.startswith(("fc_clip_", "fc_img_", "raw_fc_clip_", "temp_", "subtitles.", "thumb_", "FACELESS_FINAL_", "AETHER_RECAP_FINAL_", "fc_audio.wav", "fc_video_loop.mp4", "hook_text.txt", "thumb_pro_text.txt", "thumb_text.txt", "audio_concat.txt")):
            try:
                os.remove(f)
            except Exception:
                pass
