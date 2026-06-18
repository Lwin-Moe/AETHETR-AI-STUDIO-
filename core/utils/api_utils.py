import os
import base64

API_KEY_FILE = "saved_api_key.txt"
ELEVEN_KEY_FILE = "saved_eleven_key.txt"
GROQ_KEY_FILE = "saved_groq_key.txt"
OPENAI_KEY_FILE = "saved_openai_key.txt"
ELEVEN_VOICE_ID_FILE = "saved_eleven_voice_id.txt"

def load_key(file_path):
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f: 
            return f.read().strip()
    return ""

def save_key(file_path, key):
    with open(file_path, "w", encoding="utf-8") as f: 
        f.write(key)

def get_download_link(file_path, file_name, link_text):
    if not os.path.exists(file_path): 
        return ""
    with open(file_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return f'<a href="data:application/octet-stream;base64,{b64}" download="{file_name}" style="display:block; text-align:center; margin-top:10px; padding:12px 20px; background:linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%); color:white; text-decoration:none; border-radius:8px; font-weight:bold;">📥 {link_text}</a>'