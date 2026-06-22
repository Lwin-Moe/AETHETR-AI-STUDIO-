import streamlit as st
import os
import time
import json
import asyncio
import subprocess
import re
import urllib.parse
import requests
import textwrap
import wave
import random
import tempfile
import ffmpeg
from google import genai
from core_engines.audio_tts import generate_tts
from utils.helpers import get_available_fonts, get_download_link, cleanup_temp_files, load_key
from core_engines.video_render import FFMPEG_BINARY

# ffmpeg-python binary path
ffmpeg.ffmpeg = FFMPEG_BINARY

# ==================== ASYNC WRAPPER ====================
def run_async(coro):
    """Safe async runner for Streamlit (avoid event loop conflict)"""
    def _run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor() as executor:
        return executor.submit(_run).result()

# ==================== CORE FUNCTIONS ====================
def get_wav_duration(file_path):
    try:
        with wave.open(file_path, 'r') as wf:
            return wf.getnframes() / float(wf.getframerate())
    except Exception:
        return 0.0

def call_luma_api(image_path, prompt, duration, api_key):
    """
    Luma Dream Machine API ကို သုံးပြီး Image မှ Video ဖန်တီးခြင်း။
    (ဤနေရာတွင် Luma API ၏ တရားဝင် endpoint ကို ထည့်သွင်းရန်လိုအပ်ပါသည်။
     အောက်ပါ ကုဒ်သည် sample skeleton သာဖြစ်ပါသည်။)
    """
    try:
        # Luma API endpoint နဲ့ header
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "image_url": "",  # File upload ပြုလုပ်ရန် လိုအပ်ပါက base64 သို့မဟုတ် signed URL သုံးပါ
            "prompt": prompt,
            "duration": min(duration, 5),  # Luma က 5 sec အထိသာ ထောက်ပံ့နိုင်ပါက
        }
        # တကယ့် implementation အတွက် multipart/form-data ဖြင့် image file ပို့ပါ
        # response = requests.post("https://api.luma.ai/v1/generate", json=payload, headers=headers)
        # ရလာတဲ့ video_url ကို download လုပ်ပြီး local path သိမ်းပါ
        # ဤနမူနာတွင် placeholder အနေဖြင့် False ပြန်ထားပါသည် (Fallback သုံးရန်)
        return False, "Luma API not fully implemented"
    except Exception as e:
        return False, str(e)

def call_kling_api(image_path, prompt, duration, api_key):
    """Kling API အတွက် နမူနာ skeleton"""
    try:
        # Kling API implementation here
        return False, "Kling API not fully implemented"
    except Exception as e:
        return False, str(e)

def animate_image_with_fallback(img_path, out_path, duration, scene_prompt, api_choice=None, api_key=None):
    """
    Luma/Kling API ဖြင့် Animation လုပ်မည်။ မအောင်မြင်ပါက FFmpeg Zoompan သုံးမည်။
    api_choice: "Luma" or "Kling"
    """
    # --- API ပိုင်း စမ်းသပ်ခြင်း ---
    if api_key and api_choice:
        success = False
        if api_choice == "Luma":
            success, msg = call_luma_api(img_path, scene_prompt, duration, api_key)
        elif api_choice == "Kling":
            success, msg = call_kling_api(img_path, scene_prompt, duration, api_key)
        if success:
            # API ကရလာတဲ့ video ကို out_path သို့ရွှေ့ / copy လုပ်ပြီး True ပြန်ပါ
            # (video path ကို msg ထဲမှာ ထည့်ပေးနိုင်သည်)
            return True
        else:
            st.warning(f"{api_choice} API failed: {msg}. Falling back to FFmpeg.")

    # --- FFmpeg Zoompan Fallback ---
    fps = 25
    total_frames = max(int(duration * fps), 1)
    pan_styles = [
        f"scale=-2:2000,zoompan=z='min(zoom+0.001,1.2)':d={total_frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=720x1280,fps={fps}",
        f"scale=-2:2000,zoompan=z='1.15':d={total_frames}:x='if(lte(on,{total_frames}),on*2,0)':y='ih/2-(ih/zoom/2)':s=720x1280,fps={fps}",
        f"scale=-2:2000,zoompan=z='1.15':d={total_frames}:x='iw/2-(iw/zoom/2)':y='if(lte(on,{total_frames}),on*2,0)':s=720x1280,fps={fps}"
    ]
    selected_style = random.choice(pan_styles)
    try:
        subprocess.run(
            [FFMPEG_BINARY, "-y", "-loop", "1", "-framerate", str(fps),
             "-i", img_path, "-t", str(duration), "-vf", selected_style,
             "-c:v", "libx264", "-preset", "superfast", out_path],
            capture_output=True, check=True
        )
        return True
    except subprocess.CalledProcessError as e:
        st.error(f"Animation Fallback Error: {e.stderr.decode()}")
        return False

# ==================== UI SETUP ====================
st.markdown('<div class="setting-panel"><h2>📚 Epic Series Storytelling Studio</h2>', unsafe_allow_html=True)
st.markdown("PDF စာအုပ်ကို တစ်ခါတည်းမှတ်ဉာဏ်သွင်းပြီး၊ ၃ မိနစ်စာ အပိုင်းများအလိုက် ဗီဒီယိုများ ထုတ်လုပ်ပါ။")

MEMORY_FILE = "series_memory.json"
available_fonts = get_available_fonts()

tab1, tab2 = st.tabs(["⚙️ Step 1: Memory Setup (စာအုပ်ဖတ်ခိုင်းရန်)", "🎬 Step 2: Generate Episode (ဇာတ်လမ်းတွဲ ထုတ်ရန်)"])

api_key_input = load_key("GEMINI_API_KEY")

with tab1:
    st.info("💡 ပထမဆုံးအကြိမ်သာ လုပ်ပါ။ စာအုပ်ကို Part အလိုက်ခွဲပြီး ဇာတ်ကောင်ရုပ်ထွက်များကို မှတ်သားပါမည်။")
    series_name = st.text_input("ဇာတ်လမ်းတွဲ အမည်:", placeholder="ဥပမာ - အိုဘယ့် အနော်ရထာ")
    uploaded_pdf = st.file_uploader("PDF စာအုပ် တင်ပါ", type=["pdf"])
    
    if st.button("🧠 AI ကို ဖတ်ခိုင်းပြီး မှတ်ဉာဏ်တည်ဆောက်ပါ"):
        if not api_key_input or not uploaded_pdf or not series_name:
            st.error("API Key နှင့် PDF ကို ထည့်ပေးပါ။")
        else:
            with st.spinner("⏳ စာအုပ်ကို အပိုင်းများခွဲပြီး ဇာတ်ကောင်များကို မှတ်သားနေပါသည်... (စာမျက်နှာ ၁၀၀ ကျော်ပါက အချိန်အနည်းငယ်ကြာနိုင်ပါသည်)"):
                tmp_path = None
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                        tmp.write(uploaded_pdf.read())
                        tmp_path = tmp.name

                    client = genai.Client(api_key=api_key_input.split(",")[0])
                    media_file = client.files.upload(file=tmp_path)
                    while "PROCESSING" in str(client.files.get(name=media_file.name).state):
                        time.sleep(2)
                    
                    # --- ပိုမိုအားကောင်းသော SETUP PROMPT ---
                    setup_prompt = f"""
                    You are an expert Burmese historical scriptwriter and visual director.
                    The uploaded PDF is a Burmese historical book about "{series_name}".
                    
                    TASK:
                    1. Extract ALL main characters with EXTREMELY detailed visual descriptions (face, age, distinctive features, 11th century Bagan era attire, weapons, accessories). Focus on UNIQUE traits so images remain consistent.
                    2. Read the entire book and divide the story into sequential parts. Each part must be approximately **3 minutes of spoken narrative** (around 400-500 Burmese words). 
                    3. For EACH PART, write a concise summary (1 sentence) and then break it into SCENE blocks. For every scene block you MUST provide:
                       - [SCENE]: A rich, cinematic, wide-angle visual prompt in English. This must include:
                            * The main character(s) from the character bible (describe their look explicitly)
                            * Detailed background (Bagan temples, palace, battlefield, river, etc.)
                            * Atmospheric lighting, time of day, weather
                            * Style: "Epic 11th century Burmese historical graphic novel, masterpiece"
                       - [SFX]: Relevant sound effect (SWORD, HORSE, THUNDER, CROWD, RIVER, NONE etc.)
                       - [NARRATION]: The Burmese narration for this block (exact text to be spoken by narrator)
                    
                    CRITICAL RULES:
                    - Scene prompt must be a WIDE SHOT (not portrait), showing the environment and characters in context.
                    - Always maintain historical accuracy: Bagan period, ancient Burmese architecture, traditional costumes.
                    - Use the character bible inside each scene prompt to ensure character consistency.
                    
                    OUTPUT FORMAT: VALID JSON ONLY. No extra text.
                    {{
                        "series_title": "{series_name}",
                        "global_narrative_style": "Third-Person Omniscient Cinematic Tone. Epic historical narration.",
                        "characters": {{
                            "Character1_Name": "Visual description...",
                            "Character2_Name": "Visual description..."
                        }},
                        "parts": [
                            {{
                                "part_number": 1,
                                "summary": "Part 1 summary in Burmese",
                                "blocks": [
                                    {{
                                        "scene": "Wide cinematic shot, King Anawrahta...",
                                        "sfx": "SWORD",
                                        "narration": "အနော်ရထာမင်းကြီးသည်..."
                                    }},
                                    ...
                                ]
                            }},
                            ...
                        ]
                    }}
                    """
                    
                    res = client.models.generate_content(model="gemini-2.5-flash", contents=[media_file, setup_prompt])
                    clean_json = res.text.replace('```json', '').replace('```', '').strip()
                    # Validate JSON
                    memory_data = json.loads(clean_json)
                    # Ensure parts exist
                    if "parts" not in memory_data or not memory_data["parts"]:
                        st.error("AI could not divide the story into parts. Please try again.")
                        st.stop()
                    
                    with open(MEMORY_FILE, "w", encoding="utf-8") as jf:
                        json.dump(memory_data, jf, ensure_ascii=False, indent=2)
                    
                    client.files.delete(name=media_file.name)
                    st.success(f"✅ မှတ်ဉာဏ်တည်ဆောက်ပြီးပါပြီ! စုစုပေါင်း အပိုင်း {len(memory_data['parts'])} ပိုင်း သိမ်းဆည်းထားပါသည်။")
                except Exception as e:
                    st.error(f"Memory Setup Error: {e}")
                finally:
                    if tmp_path and os.path.exists(tmp_path):
                        os.unlink(tmp_path)

with tab2:
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "r", encoding="utf-8") as jf:
            memory_data = json.load(jf)
        st.success(f"📚 Active Series: {memory_data.get('series_title', 'Unknown')} (Parts: {len(memory_data.get('parts', []))})")
        st.json(memory_data.get("characters", {}))
        
        col_ep1, col_ep2 = st.columns(2)
        with col_ep1:
            # Part ရွေးချယ်ရန် (Number input or select)
            parts_list = memory_data.get("parts", [])
            if parts_list:
                part_numbers = [p["part_number"] for p in parts_list]
                ep_number = st.selectbox("ထုတ်လုပ်မည့် Part (အပိုင်း)", part_numbers)
            else:
                ep_number = st.number_input("Episode Number (အပိုင်း):", min_value=1, value=1)
            # Optional: Override focus (ဇာတ်လမ်းတွဲ အကျဉ်းချုပ် ပြသပြီး ပြင်ဆင်နိုင်သည်)
            selected_part = next((p for p in parts_list if p["part_number"] == ep_number), None)
            if selected_part:
                st.info(f"📖 Part {ep_number} Summary: {selected_part.get('summary', '')}")
                ep_focus = st.text_area("အကြောင်းအရာ ထပ်ဖြည့်ရန် (Optional)", placeholder="ဤအပိုင်းတွင် အထူးထည့်သွင်းလိုသည်များ...")
            else:
                ep_focus = st.text_area("ဒီအပိုင်းမှာ ဘာအကြောင်း အဓိက ပြောမလဲ?", placeholder="ဥပမာ - စုက္ကတေးနဲ့ အနော်ရထာ မြင်းကပါချောင်းမှာ စီးချင်းထိုးသည့် အခန်း။")
        
        with col_ep2:
            voice_char = st.selectbox("Narrator Voice", ["Synergy Charon (Deep)", "ဇော်ဇော် (Male)", "အောင်အောင် (Deep)"])
            font_choice = st.selectbox("Subtitle Font", available_fonts)
            # Animation API Settings
            st.markdown("---")
            st.markdown("🎞️ **Animation API (Optional)**")
            enable_api = st.checkbox("Luma/Kling API ဖြင့် Animation လုပ်မည်", value=False)
            api_choice = None
            api_anim_key = None
            if enable_api:
                api_choice = st.selectbox("API ရွေးချယ်ပါ", ["Luma", "Kling"])
                api_anim_key = st.text_input(f"{api_choice} API Key", type="password")
            
        if st.button("🚀 GENERATE EPISODE NOW"):
            st.session_state.render_success = False
            cleanup_temp_files()
            run_id = str(int(time.time()))
            pbar = st.progress(0, text="🚀 ပြင်ဆင်နေသည်...")
            
            # --- 1. SCRIPT (Memory မှယူမည်) ---
            # Memory ထဲတွင် Part အတွက် Blocks ရှိပါက အသုံးပြုပါ၊ မရှိပါက AI ဖြင့် Generate လုပ်ပါ
            if selected_part and "blocks" in selected_part:
                blocks = selected_part["blocks"]
                st.info("✅ Pre-processed script blocks loaded from memory.")
            else:
                # Fallback: မူလ AI Script Generation (Part မရှိလျှင်)
                pbar.progress(10, text="📝 AI ဇာတ်ညွှန်း ရေးသားနေသည်...")
                try:
                    client = genai.Client(api_key=api_key_input.split(",")[0])
                    char_bible = json.dumps(memory_data.get("characters", {}))
                    global_style = memory_data.get("global_narrative_style", "")
                    
                    script_prompt = f"""Write Episode {ep_number} of the series based on this plot: "{ep_focus}".
                    GLOBAL STYLE: {global_style}
                    CHARACTER BIBLE: {char_bible}
                    ... (same as before, but improved to wide shots) ...
                    """
                    res = client.models.generate_content(model="gemini-2.5-flash", contents=script_prompt)
                    raw_script = res.text.strip()
                    
                    # Parse (regex)
                    block_pattern = re.compile(
                        r'\[SCENE:\s*(.*?)\]\s*'
                        r'\[SFX:\s*(.*?)\]\s*'
                        r'\[NARRATION:\s*(.*?)\](?=\s*\[SCENE:|\s*$)',
                        re.DOTALL
                    )
                    matches = block_pattern.findall(raw_script)
                    blocks = []
                    if matches:
                        for scene, sfx, narration in matches:
                            narration = re.sub(r'\s+', ' ', narration).strip()
                            blocks.append({'scene': scene.strip(), 'sfx': sfx.strip(), 'narration': narration})
                    else:
                        # fallback line parser
                        ...
                    if not blocks:
                        st.error("AI ဇာတ်ညွှန်း Format လွဲချော်သွားပါသည်။")
                        st.stop()
                except Exception as e:
                    st.error(f"Script Error: {e}"); st.stop()
            
            # --- 2. PROCESS EACH BLOCK ---
            final_clips = []
            temp_files = []
            for i, blk in enumerate(blocks):
                pbar.progress(30 + int((i/len(blocks))*50), text=f"🎬 Scene {i+1}/{len(blocks)}")
                narration = blk['narration']
                scene_prompt = blk['scene']
                sfx_tag = blk['sfx']
                
                a_out = f"temp_aud_{i}.wav"
                i_out = f"temp_img_{i}.jpg"
                v_out = f"temp_vid_{i}.mp4"
                anim_out = f"temp_anim_{i}.mp4"
                temp_files.extend([a_out, i_out, v_out, anim_out])
                
                # A. Audio
                run_async(generate_tts(narration, voice_char, a_out,
                                       engine="Google Synergy TTS (Flash 3.1 Preview)" if "Synergy" in voice_char else "Edge-TTS",
                                       gemini_key=api_key_input))
                dur = get_wav_duration(a_out)
                if dur < 1.0: dur = 3.0
                
                # B. Image (Improved: inject character bible and wide shot hints)
                # Character bible ကို scene prompt ထဲသို့ထည့်ထားသော်လည်း ထပ်မံအားဖြည့်ရန်
                char_bible_context = ", ".join(memory_data.get("characters", {}).values())
                full_scene_prompt = f"{scene_prompt}, {char_bible_context}, wide cinematic shot, Bagan ancient kingdom, historical accuracy, masterpiece, 11th century graphic novel style"
                encoded_prompt = urllib.parse.quote(full_scene_prompt)
                url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=720&height=1280&nologo=true"
                try:
                    resp = requests.get(url, timeout=30)
                    if resp.status_code != 200 or 'image' not in resp.headers.get('Content-Type', ''):
                        raise Exception("Invalid image response")
                    with open(i_out, "wb") as f:
                        f.write(resp.content)
                except Exception as e:
                    st.error(f"Image generation failed for scene {i+1}: {e}")
                    st.stop()
                
                # C. Animation
                anim_success = animate_image_with_fallback(
                    i_out, anim_out, dur,
                    scene_prompt=scene_prompt,  # original scene prompt for API
                    api_choice=api_choice if enable_api else None,
                    api_key=api_anim_key if enable_api else None
                )
                if not anim_success:
                    st.error(f"Animation failed for scene {i+1}")
                    st.stop()
                
                # D. Subtitles
                safe_text = narration.replace(':', '\\:').replace("'", "'\\''")
                font_path = os.path.abspath(font_choice).replace('\\', '/')
                vid_stream = ffmpeg.input(anim_out).video
                vid_stream = ffmpeg.filter(vid_stream, 'drawtext',
                                           text=safe_text,
                                           fontfile=font_path,
                                           fontcolor='yellow',
                                           fontsize=32,
                                           bordercolor='black',
                                           borderw=3,
                                           x='(w-text_w)/2',
                                           y='h-text_h-150',
                                           text_align='C')
                
                # E. Audio mix
                aud_stream = ffmpeg.input(a_out).audio
                sfx_path = f"sfx/{sfx_tag.lower()}.mp3"
                if sfx_tag != "NONE" and os.path.exists(sfx_path):
                    sfx_stream = ffmpeg.input(sfx_path).audio.filter('volume', 0.8)
                    aud_stream = ffmpeg.filter([aud_stream, sfx_stream], 'amix', inputs=2, duration='first')
                
                ffmpeg.output(vid_stream, aud_stream, v_out,
                              vcodec='libx264', acodec='aac', t=dur
                              ).overwrite_output().run(cmd=FFMPEG_BINARY, quiet=True)
                final_clips.append(v_out)
            
            # --- 3. CONCATENATE ---
            pbar.progress(90, text="🎞️ ဗီဒီယိုအားလုံးကို ဆက်စပ်နေသည်...")
            concat_file = f"concat_list_{run_id}.txt"
            with open(concat_file, "w") as f:
                for c in final_clips:
                    f.write(f"file '{os.path.abspath(c)}'\n")
            temp_files.append(concat_file)
            out_final = f"EPISODE_{ep_number}_{run_id}.mp4"
            subprocess.run([FFMPEG_BINARY, "-y", "-f", "concat", "-safe", "0",
                            "-i", concat_file, "-c", "copy", out_final],
                           capture_output=True, check=True)
            
            st.session_state.final_video_path = out_final
            st.session_state.render_success = True
            pbar.progress(100, text="✅ အားလုံးအောင်မြင်စွာ ပြီးစီးပါပြီ!")
            
            # Cleanup
            for tf in temp_files:
                if os.path.exists(tf):
                    try:
                        os.remove(tf)
                    except Exception:
                        pass
                        
        # Dashboard
        if st.session_state.get("render_success"):
            st.balloons()
            st.success(f"🎉 Episode {ep_number} အောင်မြင်စွာ ထွက်လာပါပြီ!")
            if os.path.exists(st.session_state.final_video_path):
                st.video(st.session_state.final_video_path)
                st.markdown(get_download_link(st.session_state.final_video_path, f"Epic_Episode_{ep_number}.mp4", "📥 Download Episode Video"), unsafe_allow_html=True)
    else:
        st.warning("⚠️ မှတ်ဉာဏ်ဖိုင် (Memory) မရှိသေးပါ။ Step 1 တွင် အရင်ဆုံး Setup လုပ်ပါ။")
