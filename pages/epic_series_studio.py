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
import random  # မူရင်းကုဒ်တွင် ပျောက်နေသည့် random module
import tempfile
import ffmpeg
import json5   # AI မှထွက်သော JSON (control character များပါလျှင်) အတွက်
from google import genai
from core_engines.audio_tts import generate_tts
from utils.helpers import get_available_fonts, get_download_link, cleanup_temp_files, load_key
from core_engines.video_render import FFMPEG_BINARY

ffmpeg.ffmpeg = FFMPEG_BINARY

# ==================== KEY ROTATION HELPER ====================
def gemini_generate_with_keys(api_keys, model, contents, max_retries_per_key=2):
    """
    Comma ခြားထားသော Gemini API Keys များကို အစဉ်တိုင်းစမ်းပြီး 
    အောင်မြင်သော Key ဖြင့် Generate လုပ်ပါမည်။
    """
    for key in api_keys:
        try:
            client = genai.Client(api_key=key.strip())
            for attempt in range(max_retries_per_key):
                try:
                    res = client.models.generate_content(model=model, contents=contents)
                    return res
                except Exception as e:
                    err = str(e)
                    if any(code in err for code in ["503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED"]):
                        wait = 2 ** attempt
                        st.warning(f"Key {key[:10]}... – {wait}s စောင့်ပါ...")
                        time.sleep(wait)
                        continue
                    else:
                        raise e
            st.warning(f"Key {key[:10]}... ဖြင့် မအောင်မြင်ပါ။")
        except Exception as e:
            st.warning(f"Key {key[:10]}... error: {e}")
            continue
    raise Exception("Gemini API ခေါ်ဆို၍မရပါ – သော့အားလုံး ပျက်ကုန်ပါပြီ။")

def step1_memory_setup(pdf_bytes, api_keys, series_name):
    """
    Step 1 အတွက် Key rotation ပါဝင်သော Memory Setup လုပ်ငန်းစဉ်။
    Key တစ်ခုချင်းစီအတွက် file upload + generate ကို လုပ်ဆောင်ပါမည်။
    """
    last_error = None
    for key in api_keys:
        tmp_path = None
        try:
            # temp file ဖန်တီးပါ
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(pdf_bytes)
                tmp_path = tmp.name

            client = genai.Client(api_key=key.strip())
            # File upload
            media_file = client.files.upload(file=tmp_path)
            while "PROCESSING" in str(client.files.get(name=media_file.name).state):
                time.sleep(2)

            # Generate content
            setup_prompt = f"""Read this book. Extract the main characters and create a short, extremely detailed English visual prompt for each.
Each visual prompt MUST describe the character's **full body pose, traditional 11th century Bagan attire, weapons, and the typical background environment (Bagan temples, palace, battlefield, etc.)**.
This will be used to generate consistent character images in wide cinematic shots.
Output EXACTLY as a valid JSON format:
{{
    "series_title": "{series_name}",
    "global_narrative_style": "Third-Person Omniscient Cinematic Tone. Tell the story like a legendary historical epic. Do NOT change narrator perspective.",
    "characters": {{
        "Character1_Name": "Visual description with wide background...",
        "Character2_Name": "Visual description with wide background..."
    }}
}}"""
            # ဤနေရာတွင် generate လုပ်ရန် key rotation helper ကိုပင် သုံးနိုင်သော်လည်း
            # media file သည် ထို key ဖြင့်သာ access လုပ်နိုင်သောကြောင့် ထို key နှင့်ပဲ generate လုပ်ပါမည်။
            # သို့သော် ယာယီပြဿနာ (503) အတွက် retry လုပ်ရန် gemini_generate_with_keys ၏ logic ကို manual ထည့်ပါမည်။
            for attempt in range(3):
                try:
                    res = client.models.generate_content(model="gemini-2.5-flash", contents=[media_file, setup_prompt])
                    break
                except Exception as e:
                    err = str(e)
                    if any(c in err for c in ["503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED"]):
                        wait = 2 ** attempt
                        st.warning(f"Key {key[:10]}... – {wait}s စောင့်ပါ...")
                        time.sleep(wait)
                        continue
                    else:
                        raise e
            else:
                raise Exception("Generate failed after retries")

            clean_json = res.text.replace('```json', '').replace('```', '').strip()
            memory_data = json5.loads(clean_json)
            # အောင်မြင်ပါက file delete လုပ်ပြီး ပြန်ပေးမည်
            client.files.delete(name=media_file.name)
            return memory_data
        except Exception as e:
            last_error = e
            # cleanup
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)
            st.warning(f"Key {key[:10]}... ဖြင့် မအောင်မြင်ပါ။ နောက် key ဖြင့် ထပ်ကြိုးစားပါမည်...")
            continue
    raise Exception(f"Memory Setup အားလုံးမအောင်မြင်ပါ။ နောက်ဆုံးအမှား: {last_error}")

# --- CORE FUNCTIONS (မူရင်းအတိုင်း + ပုံ prompt အားကောင်းခြင်း) ---
def get_wav_duration(file_path):
    try:
        with wave.open(file_path, 'r') as wf: return wf.getnframes() / float(wf.getframerate())
    except Exception: return 0.0

def animate_image_with_fallback(img_path, out_path, duration, w=720, h=1280):
    """FFmpeg Zoompan ဖြင့် Auto Fallback"""
    try:
        fps = 25
        total_frames = int(duration * fps)
        pan_styles = [
            f"scale=-2:2000,zoompan=z='min(zoom+0.001,1.2)':d={total_frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{h},fps={fps}",
            f"scale=-2:2000,zoompan=z='1.15':d={total_frames}:x='if(lte(on,{total_frames}),on*2,0)':y='ih/2-(ih/zoom/2)':s={w}x{h},fps={fps}",
            f"scale=-2:2000,zoompan=z='1.15':d={total_frames}:x='iw/2-(iw/zoom/2)':y='if(lte(on,{total_frames}),on*2,0)':s={w}x{h},fps={fps}"
        ]
        selected_style = random.choice(pan_styles)
        subprocess.run([FFMPEG_BINARY, "-y", "-loop", "1", "-framerate", str(fps),
                        "-i", img_path, "-t", str(duration), "-vf", selected_style,
                        "-c:v", "libx264", "-preset", "superfast", out_path],
                       capture_output=True, check=True)
        return True
    except Exception as e:
        st.error(f"Animation Fallback Error: {e}")
        return False

# --- UI & LOGIC (မူရင်းအတိုင်း) ---
st.markdown('<div class="setting-panel"><h2>📚 Epic Series Storytelling Studio</h2>', unsafe_allow_html=True)
st.markdown("PDF စာအုပ်ကို တစ်ခါတည်းမှတ်ဉာဏ်သွင်းပြီး၊ Consistency အပြည့်အဝဖြင့် ဇာတ်လမ်းတွဲများ ဆက်တိုက်ထုတ်လုပ်ပါ။")

MEMORY_FILE = "series_memory.json"
available_fonts = get_available_fonts()

tab1, tab2 = st.tabs(["⚙️ Step 1: Memory Setup (စာအုပ်ဖတ်ခိုင်းရန်)", "🎬 Step 2: Generate Episode (ဇာတ်လမ်းတွဲ ထုတ်ရန်)"])

api_key_input = load_key("GEMINI_API_KEY")
# Comma ခြားထားသော Key များကို list အဖြစ် ပြင်ဆင်ပါ
gemini_keys = [k.strip() for k in api_key_input.split(",") if k.strip()] if api_key_input else []

with tab1:
    st.info("💡 ပထမဆုံးအကြိမ် တစ်ခါသာ လုပ်ရန် လိုအပ်ပါသည်။")
    series_name = st.text_input("ဇာတ်လမ်းတွဲ အမည်:", placeholder="ဥပမာ - အိုဘယ့် အနော်ရထာ")
    uploaded_pdf = st.file_uploader("PDF စာအုပ် တင်ပါ", type=["pdf"])
    
    if st.button("🧠 AI ကို ဖတ်ခိုင်းပြီး မှတ်ဉာဏ်တည်ဆောက်ပါ"):
        if not gemini_keys or not uploaded_pdf or not series_name:
            st.error("API Key နှင့် PDF ကို ထည့်ပေးပါ။")
        else:
            with st.spinner("⏳ စာအုပ်တစ်အုပ်လုံးကို ဖတ်ရှုပြီး ဇာတ်ကောင်များကို မှတ်သားနေပါသည်... (Key တစ်ခုမရပါက နောက် Key ဖြင့် ဆက်ကြိုးစားပါမည်)"):
                try:
                    memory_data = step1_memory_setup(uploaded_pdf.read(), gemini_keys, series_name)
                    with open(MEMORY_FILE, "w", encoding="utf-8") as jf:
                        json.dump(memory_data, jf, ensure_ascii=False, indent=2)
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
            
            # --- 1. SCRIPT GENERATION (Key Rotation) ---
            try:
                char_bible = json.dumps(memory_data.get("characters", {}), ensure_ascii=False)
                global_style = memory_data.get("global_narrative_style", "")
                
                script_prompt = f"""Write Episode {ep_number} of the series based on this plot: "{ep_focus}".
GLOBAL STYLE: {global_style}
CHARACTER BIBLE: {char_bible}
                
STRICT INSTRUCTIONS:
1. Write in engaging spoken Burmese. Start with a 3-second viral hook.
2. You MUST break the story into sequential blocks (scenes).
3. For EVERY block, you MUST provide 3 tags exactly in this order:
   [SCENE: Wide cinematic shot, include the exact visual description of characters from the Character Bible, plus detailed background (Bagan temples, battlefield, etc.), dramatic lighting, epic 11th century graphic novel style]
   [SFX: SWORD or HORSE or THUNDER or CROWD or NONE]
   [NARRATION: <The Burmese spoken script for this block>]

Example format:
[SCENE: Wide shot, King Anawrahta in golden armor riding a white horse, Bagan temples in background, dramatic sunset lighting]
[SFX: HORSE]
[NARRATION: အနော်ရထာမင်းကြီးသည် စစ်သည်တော်များနှင့်...]

Do not add any other text outside these blocks!"""
                
                res = gemini_generate_with_keys(gemini_keys, "gemini-2.5-flash", script_prompt)
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

            # --- 3. PROCESS EACH BLOCK ---
            final_clips = []
            for i, blk in enumerate(blocks):
                pbar.progress(30 + int((i/len(blocks))*50), text=f"🎬 Scene {i+1}/{len(blocks)} အား ဖန်တီးနေပါသည်...")
                
                narration = blk['narration']
                scene_prompt = blk['scene']
                sfx_tag = blk['sfx']
                
                a_out = f"temp_aud_{i}.wav"
                i_out = f"temp_img_{i}.jpg"
                v_out = f"temp_vid_{i}.mp4"
                
                # A. Generate Audio (မူရင်းအတိုင်း)
                asyncio.run(generate_tts(
                    narration, voice_char, a_out,
                    engine="Google Synergy TTS (Flash 3.1 Preview)" if "Synergy" in voice_char else "Edge-TTS",
                    gemini_key=api_key_input.split(",")[0] if api_key_input else None
                ))
                dur = get_wav_duration(a_out)
                if dur < 1.0: dur = 3.0
                
                # B. Generate Image (✅ IMPROVED: Wide shot + Historical accuracy + Character consistency)
                # Character Bible မှ Visual Descriptions အားလုံးကို prompt ထဲသို့ထည့်ပါ
                char_descriptions = ", ".join(memory_data.get("characters", {}).values())
                full_scene_prompt = f"{scene_prompt}, {char_descriptions}, wide cinematic shot, Bagan ancient kingdom, 11th century Burmese historical accuracy, epic graphic novel style, masterpiece"
                # Prompt အရှည်ကန့်သတ်ရန် (option)
                if len(full_scene_prompt) > 1000:
                    full_scene_prompt = full_scene_prompt[:1000]
                encoded_prompt = urllib.parse.quote(full_scene_prompt)
                url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=720&height=1280&nologo=true"
                try:
                    res = requests.get(url, timeout=30)
                    # Status check ထည့်ပါ (ပုံမဟုတ်သည့် response များကို ကာကွယ်ရန်)
                    if res.status_code == 200 and 'image' in res.headers.get('Content-Type', ''):
                        with open(i_out, "wb") as f: f.write(res.content)
                    else:
                        # Fallback: ရိုးရှင်းသော prompt ဖြင့် ထပ်ကြိုးစားပါ
                        st.warning(f"Image API returned status {res.status_code}, retrying with simple prompt...")
                        simple_prompt = "epic 11th century Bagan historical scene, wide cinematic shot, masterpiece"
                        encoded_prompt = urllib.parse.quote(simple_prompt)
                        url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=720&height=1280&nologo=true"
                        res = requests.get(url, timeout=30)
                        if res.status_code == 200 and 'image' in res.headers.get('Content-Type', ''):
                            with open(i_out, "wb") as f: f.write(res.content)
                        else:
                            raise Exception("Image API failed")
                except Exception as e:
                    st.error(f"Image generation failed for scene {i}: {e}"); st.stop()
                    
                # C. Animate Image
                if not animate_image_with_fallback(i_out, "temp_anim.mp4", dur):
                    st.error(f"Animation failed for scene {i}")
                    st.stop()
                
                # D. Add Subtitles
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
