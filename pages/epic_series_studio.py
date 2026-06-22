import streamlit as st
import os
import time
import json
import asyncio
import subprocess
import shutil
import re
import urllib.parse
import requests
import textwrap
import wave
import ffmpeg
from google import genai
from core_engines.audio_tts import generate_tts
from utils.helpers import get_available_fonts, get_download_link, cleanup_temp_files, load_key
from core_engines.video_render import FFMPEG_BINARY


# --- CORE FUNCTIONS ---
def get_wav_duration(file_path):
    try:
        with wave.open(file_path, 'r') as wf: return wf.getnframes() / float(wf.getframerate())
    except Exception: return 0.0

def animate_image_with_fallback(img_path, out_path, duration, w=720, h=1280):
    """Luma/Kling API မရပါက FFmpeg Zoompan ဖြင့် Auto Fallback လုပ်မည့်စနစ်"""
    # မှတ်ချက်: ဤနေရာတွင် Luma API ကို လှမ်းခေါ်ရန် Code ထည့်နိုင်သည်။ (ယခုတော့ FFmpeg ဖြင့် အခမဲ့ သေချာပေါက်လုပ်မည်)
    try:
        # Panning Effects အား Random ကစားခြင်းဖြင့် ရုပ်ရှင်ဆန်စေရန်
        pan_styles = [
            f"zoompan=z='min(zoom+0.001,1.15)':d={int(duration*25)}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{h},fps=25", # Center Zoom
            f"zoompan=z='1.15':d={int(duration*25)}:x='if(eq(x,0),0,x+1)':y='ih/2-(ih/zoom/2)':s={w}x{h},fps=25", # Pan Right
            f"zoompan=z='1.15':d={int(duration*25)}:x='iw/2-(iw/zoom/2)':y='if(eq(y,0),0,y+1)':s={w}x{h},fps=25"  # Pan Down
        ]
        selected_style = random.choice(pan_styles)
        
        subprocess.run([FFMPEG_BINARY, "-y", "-loop", "1", "-framerate", "25", "-i", img_path, "-t", str(duration), "-vf", f"scale=-2:2000,{selected_style}", "-c:v", "libx264", "-preset", "superfast", out_path], capture_output=True)
        return True
    except Exception as e:
        st.error(f"Animation Fallback Error: {e}")
        return False

# --- UI & LOGIC ---
st.markdown('<div class="setting-panel"><h2>📚 Epic Series Storytelling Studio</h2>', unsafe_allow_html=True)
st.markdown("PDF စာအုပ်ကို တစ်ခါတည်းမှတ်ဉာဏ်သွင်းပြီး၊ Consistency အပြည့်အဝဖြင့် ဇာတ်လမ်းတွဲများ ဆက်တိုက်ထုတ်လုပ်ပါ။")

MEMORY_FILE = "series_memory.json"
available_fonts = get_available_fonts()

tab1, tab2 = st.tabs(["⚙️ Step 1: Memory Setup (စာအုပ်ဖတ်ခိုင်းရန်)", "🎬 Step 2: Generate Episode (ဇာတ်လမ်းတွဲ ထုတ်ရန်)"])

api_key_input = load_key("saved_api_key.txt") # Gemini Key ကို ယူပါမည်

with tab1:
    st.info("💡 ပထမဆုံးအကြိမ် တစ်ခါသာ လုပ်ရန် လိုအပ်ပါသည်။ စာအုပ်ကို ဖတ်ပြီး ဇာတ်ကောင်ရုပ်ထွက်များကို အသေမှတ်သားပါမည်။")
    series_name = st.text_input("ဇာတ်လမ်းတွဲ အမည်:", placeholder="ဥပမာ - အိုဘယ့် အနော်ရထာ")
    uploaded_pdf = st.file_uploader("PDF စာအုပ် တင်ပါ", type=["pdf"])
    
    if st.button("🧠 AI ကို ဖတ်ခိုင်းပြီး မှတ်ဉာဏ်တည်ဆောက်ပါ"):
        if not api_key_input or not uploaded_pdf or not series_name:
            st.error("API Key နှင့် PDF ကို ထည့်ပေးပါ။")
        else:
            with st.spinner("⏳ စာအုပ်တစ်အုပ်လုံးကို ဖတ်ရှုပြီး ဇာတ်ကောင်များကို မှတ်သားနေပါသည်..."):
                try:
                    with open("temp_book.pdf", "wb") as f: f.write(uploaded_pdf.read())
                    client = genai.Client(api_key=api_key_input.split(",")[0])
                    media_file = client.files.upload(file="temp_book.pdf")
                    while "PROCESSING" in str(client.files.get(name=media_file.name).state): time.sleep(2)
                    
                    setup_prompt = f"""Read this book. Extract the main characters and create a short, extremely detailed English visual prompt for each (focus on face, 11th century Burmese attire, weapons). 
                    Output EXACTLY as a valid JSON format:
                    {{
                        "series_title": "{series_name}",
                        "global_narrative_style": "Third-Person Omniscient Cinematic Tone. Tell the story like a legendary historical epic. Do NOT change narrator perspective.",
                        "characters": {{
                            "Character1_Name": "Visual description...",
                            "Character2_Name": "Visual description..."
                        }}
                    }}"""
                    res = client.models.generate_content(model="gemini-2.5-flash", contents=[media_file, setup_prompt])
                    clean_json = res.text.replace('```json', '').replace('```', '').strip()
                    with open(MEMORY_FILE, "w", encoding="utf-8") as jf: jf.write(clean_json)
                    client.files.delete(name=media_file.name)
                    st.success("✅ မှတ်ဉာဏ်တည်ဆောက်ခြင်း ပြီးစီးပါပြီ! Step 2 သို့ သွားပါ။")
                except Exception as e:
                    st.error(f"Memory Setup Error: {e}")

with tab2:
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "r", encoding="utf-8") as jf:
            memory_data = json.load(jf)
        st.success(f"📚 Active Series: {memory_data.get('series_title', 'Unknown')}")
        st.json(memory_data.get("characters", {}))
        
        col_ep1, col_ep2 = st.columns(2)
        with col_ep1:
            ep_number = st.number_input("Episode Number (အပိုင်း):", min_value=1, value=1)
            ep_focus = st.text_area("ဒီအပိုင်းမှာ ဘာအကြောင်း အဓိက ပြောမလဲ?", placeholder="ဥပမာ - စုက္ကတေးနဲ့ အနော်ရထာ မြင်းကပါချောင်းမှာ စီးချင်းထိုးသည့် အခန်း။")
        with col_ep2:
            voice_char = st.selectbox("Narrator Voice", ["Synergy Charon (Deep)", "ဇော်ဇော် (Male)", "အောင်အောင် (Deep)"])
            font_choice = st.selectbox("Subtitle Font", available_fonts)
            
        if st.button("🚀 GENERATE EPISODE NOW"):
            st.session_state.render_success = False
            cleanup_temp_files()
            run_id = str(int(time.time()))
            pbar = st.progress(0, text="🚀 ဇာတ်ညွှန်း ရေးသားနေပါသည်...")
            
            # --- 1. SCRIPT GENERATION ---
            try:
                client = genai.Client(api_key=api_key_input.split(",")[0])
                char_bible = json.dumps(memory_data.get("characters", {}))
                global_style = memory_data.get("global_narrative_style", "")
                
                # 🔴 PROMPT ENGINEERING: ဇာတ်ညွှန်းကို Block တွေအဖြစ် အတိအကျ ခွဲထုတ်ခိုင်းခြင်း
                script_prompt = f"""Write Episode {ep_number} of the series based on this plot: "{ep_focus}".
                GLOBAL STYLE: {global_style}
                CHARACTER BIBLE: {char_bible}
                
                STRICT INSTRUCTIONS:
                1. Write in engaging spoken Burmese. Start with a 3-second viral hook.
                2. You MUST break the story into sequential blocks (scenes).
                3. For EVERY block, you MUST provide 3 tags exactly in this order:
                   [SCENE: Epic 11th century graphic novel art style, <inject matching character visual from Bible here>, dramatic lighting]
                   [SFX: SWORD or HORSE or THUNDER or CROWD or NONE]
                   [NARRATION: <The Burmese spoken script for this block>]
                
                Example format:
                [SCENE: King Anawrahta holding shining spear, epic Bagan background]
                [SFX: SWORD]
                [NARRATION: အနော်ရထာမင်းကြီးသည် အရိန္ဒမာလှံကို ကိုင်ဆောင်လျက်...]
                
                Do not add any other text outside these blocks!"""
                
                res = client.models.generate_content(model="gemini-2.5-flash", contents=script_prompt)
                raw_script = res.text.strip()
            except Exception as e:
                st.error(f"Script Error: {e}"); st.stop()
                
            # --- 2. PARSE BLOCKS ---
            pbar.progress(20, text="🔍 ဇာတ်ကွက်များကို စိစစ်နေပါသည်...")
            blocks = []
            current_block = {}
            for line in raw_script.split('\n'):
                line = line.strip()
                if line.startswith('[SCENE:'):
                    if current_block: blocks.append(current_block)
                    current_block = {'scene': line.replace('[SCENE:', '').replace(']', '').strip(), 'sfx': 'NONE', 'narration': ''}
                elif line.startswith('[SFX:') and current_block:
                    current_block['sfx'] = line.replace('[SFX:', '').replace(']', '').strip()
                elif line.startswith('[NARRATION:') and current_block:
                    current_block['narration'] = line.replace('[NARRATION:', '').replace(']', '').strip()
                elif line and current_block and not line.startswith('['):
                    current_block['narration'] += " " + line
            if current_block: blocks.append(current_block)
            
            if not blocks:
                st.error("AI ဇာတ်ညွှန်း Format လွဲချော်သွားပါသည်။ ပြန်လည် Generate လုပ်ပါ။")
                st.stop()

            # --- 3. PROCESS EACH BLOCK (PERFECT SYNC ENGINE) ---
            final_clips = []
            for i, blk in enumerate(blocks):
                pbar.progress(30 + int((i/len(blocks))*50), text=f"🎬 Scene {i+1}/{len(blocks)} အား ဖန်တီးနေပါသည်...")
                
                narration = blk['narration']
                scene_prompt = blk['scene']
                sfx_tag = blk['sfx']
                
                a_out = f"temp_aud_{i}.wav"
                i_out = f"temp_img_{i}.jpg"
                v_out = f"temp_vid_{i}.mp4"
                
                # A. Generate Audio
                asyncio.run(generate_tts(narration, voice_char, a_out, engine="Google Synergy TTS (Flash 3.1 Preview)" if "Synergy" in voice_char else "Edge-TTS", gemini_key=api_key_input))
                dur = get_wav_duration(a_out)
                if dur < 1.0: dur = 3.0 # Fallback safety
                
                # B. Generate Image
                encoded_prompt = urllib.parse.quote(scene_prompt + ", masterpiece, epic 11th century graphic novel, highly detailed")
                url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=720&height=1280&nologo=true"
                try:
                    res = requests.get(url, timeout=30)
                    with open(i_out, "wb") as f: f.write(res.content)
                except Exception:
                    st.error(f"Image generation failed for scene {i}"); st.stop()
                    
                # C. Animate Image (Length = Audio Duration exactly)
                animate_image_with_fallback(i_out, "temp_anim.mp4", dur)
                
                # D. Add Subtitles (Burn into this specific clip)
                wrap_text = "\n".join(textwrap.wrap(narration, 25))
                with open("temp_sub.txt", "w", encoding="utf-8") as tf: tf.write(wrap_text)
                safe_font = os.path.abspath(font_choice).replace('\\', '/').replace(':', '\\:')
                
                vid_stream = ffmpeg.input("temp_anim.mp4").video
                vid_stream = ffmpeg.filter(vid_stream, 'drawtext', textfile='temp_sub.txt', fontfile=safe_font, fontcolor='yellow', fontsize=32, bordercolor='black', borderw=3, x='(w-text_w)/2', y='h-text_h-150', text_align='C')
                
                # E. Mix Audio & SFX
                aud_stream = ffmpeg.input(a_out).audio
                sfx_path = f"sfx/{sfx_tag.lower()}.mp3"
                if sfx_tag != "NONE" and os.path.exists(sfx_path):
                    sfx_stream = ffmpeg.input(sfx_path).audio.filter('volume', 0.8)
                    aud_stream = ffmpeg.filter([aud_stream, sfx_stream], 'amix', inputs=2, duration='first')
                
                # Render the final block clip
                ffmpeg.output(vid_stream, aud_stream, v_out, vcodec='libx264', acodec='aac', t=dur).overwrite_output().run(cmd=FFMPEG_BINARY, quiet=True)
                final_clips.append(v_out)
                
            # --- 4. MASTER CONCATENATION ---
            pbar.progress(90, text="🎞️ ဗီဒီယိုအားလုံးကို ဆက်စပ်နေပါသည်...")
            with open("concat_list.txt", "w") as f:
                for c in final_clips: f.write(f"file '{c}'\n")
            
            out_final = f"EPISODE_{ep_number}_{run_id}.mp4"
            subprocess.run([FFMPEG_BINARY, "-y", "-f", "concat", "-safe", "0", "-i", "concat_list.txt", "-c", "copy", out_final], capture_output=True)
            
            st.session_state.final_video_path = out_final
            st.session_state.render_success = True
            pbar.progress(100, text="✅ အားလုံးအောင်မြင်စွာ ပြီးစီးပါပြီ!")
            
        # Dashboard Display
        if st.session_state.get("render_success"):
            st.balloons()
            st.success(f"🎉 Episode {ep_number} အောင်မြင်စွာ ထွက်လာပါပြီ!")
            if os.path.exists(st.session_state.final_video_path):
                st.video(st.session_state.final_video_path)
                st.markdown(get_download_link(st.session_state.final_video_path, f"Epic_Episode_{ep_number}.mp4", "📥 Download Episode Video"), unsafe_allow_html=True)
    else:
        st.warning("⚠️ မှတ်ဉာဏ်ဖိုင် (Memory) မရှိသေးပါ။ Step 1 တွင် အရင်ဆုံး Setup လုပ်ပါ။")
