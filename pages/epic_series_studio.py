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
import random  
import tempfile  
import ffmpeg
from google import genai
from core_engines.audio_tts import generate_tts
from utils.helpers import get_available_fonts, get_download_link, cleanup_temp_files, load_key
from core_engines.video_render import FFMPEG_BINARY

# ffmpeg-python ၏ default binary ကို သတ်မှတ်ထားသော path သို့ပြောင်းပါ
ffmpeg.ffmpeg = FFMPEG_BINARY

# --- ASYNCIO အတွက် Safe Wrapper (Streamlit event loop နှင့် conflict မဖြစ်စေရန်) ---
def run_async(coro):
    """သီးသန့် thread တွင် event loop အသစ်ဖြင့် async function ကို run ပါ"""
    def _run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(_run)
        return future.result()

# --- CORE FUNCTIONS ---
def get_wav_duration(file_path):
    try:
        with wave.open(file_path, 'r') as wf:
            return wf.getnframes() / float(wf.getframerate())
    except Exception:
        return 0.0

def animate_image_with_fallback(img_path, out_path, duration, w=720, h=1280):
    """FFmpeg Zoompan ဖြင့် Animation ဖန်တီးပါ (Luma/Kling မပါလျှင်)"""
    fps = 25
    total_frames = int(duration * fps)
    if total_frames < 1:
        total_frames = 1
    
    pan_styles = [
        f"scale=-2:2000,zoompan=z='min(zoom+0.001,1.2)':d={total_frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{h},fps={fps}",
        f"scale=-2:2000,zoompan=z='1.15':d={total_frames}:x='if(lte(on,{total_frames}),on*2,0)':y='ih/2-(ih/zoom/2)':s={w}x{h},fps={fps}",
        f"scale=-2:2000,zoompan=z='1.15':d={total_frames}:x='iw/2-(iw/zoom/2)':y='if(lte(on,{total_frames}),on*2,0)':s={w}x{h},fps={fps}"
    ]
    selected_style = random.choice(pan_styles)
    
    try:
        subprocess.run(
            [FFMPEG_BINARY, "-y", "-loop", "1", "-framerate", str(fps),
             "-i", img_path, "-t", str(duration),
             "-vf", selected_style,
             "-c:v", "libx264", "-preset", "superfast", out_path],
            capture_output=True, check=True
        )
        return True
    except subprocess.CalledProcessError as e:
        st.error(f"Animation Fallback Error: {e.stderr.decode()}")
        return False

# --- UI & LOGIC ---
st.markdown('<div class="setting-panel"><h2>📚 Epic Series Storytelling Studio</h2>', unsafe_allow_html=True)
st.markdown("PDF စာအုပ်ကို တစ်ခါတည်းမှတ်ဉာဏ်သွင်းပြီး၊ Consistency အပြည့်အဝဖြင့် ဇာတ်လမ်းတွဲများ ဆက်တိုက်ထုတ်လုပ်ပါ။")

MEMORY_FILE = "series_memory.json"
available_fonts = get_available_fonts()

# 🔴 ဇာတ်ညွှန်း Review လုပ်ရန် State သတ်မှတ်ခြင်း
if "script_draft" not in st.session_state:
    st.session_state.script_draft = ""

tab1, tab2 = st.tabs(["⚙️ Step 1: Memory Setup (စာအုပ်ဖတ်ခိုင်းရန်)", "🎬 Step 2: Generate Episode (ဇာတ်လမ်းတွဲ ထုတ်ရန်)"])

api_key_input = load_key("GEMINI_API_KEY")

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
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                        tmp.write(uploaded_pdf.read())
                        tmp_path = tmp.name

                    keys = [k.strip() for k in api_key_input.split(",") if k.strip()]
                    setup_success = False
                    last_error = None
                    
                    for key in keys:
                        for attempt in range(3): 
                            try:
                                client = genai.Client(api_key=key)
                                media_file = client.files.upload(file=tmp_path)
                                while "PROCESSING" in str(client.files.get(name=media_file.name).state):
                                    time.sleep(2)
                                
                                setup_prompt = f"""Read this book. Extract the main characters and create a short, extremely detailed English visual prompt for each. 
                                CRITICAL VISUAL RULES: The setting is strictly 11th century Ancient Myanmar (Burma) / Southeast Asia. 
                                PROHIBITED: NO Chinese, NO Japanese, NO Hanfu, NO Samurai, NO East Asian tropes, NO queues (braids).
                                ATTIRE: Characters must wear traditional Myanmar 'paso' (sarong), 'eingyi', and headbands. Warriors have tattoos on their thighs.
                                
                                Output EXACTLY as a valid JSON format:
                                {{
                                    "series_title": "{series_name}",
                                    "global_narrative_style": "Third-Person Omniscient Cinematic Tone. Tell the story like a legendary historical epic.",
                                    "global_art_style": "High-quality 2D digital art, masterpiece webtoon style. Strictly Ancient Myanmar/Bagan aesthetic. (Note: Mood shifts dynamically from gritty/dark in early era to golden/majestic in later era)",
                                    "characters": {{
                                        "Character1_Name": "Visual description including Southeast Asian facial features and Burmese attire...",
                                        "Character2_Name": "Visual description..."
                                    }}
                                }}"""
                                res = client.models.generate_content(model="gemini-2.5-flash", contents=[media_file, setup_prompt])
                                
                                raw_text = res.text
                                json_match = re.search(r'\{[\s\S]*\}', raw_text)
                                if json_match:
                                    clean_json = json_match.group(0)
                                else:
                                    clean_json = raw_text.replace('```json', '').replace('```', '').strip()
                                    
                                with open(MEMORY_FILE, "w", encoding="utf-8") as jf:
                                    jf.write(clean_json)
                                client.files.delete(name=media_file.name)
                                
                                setup_success = True
                                break 
                            except Exception as e:
                                last_error = e
                                if "503" in str(e) or "429" in str(e):
                                    time.sleep(5 * (attempt + 1)) 
                                    continue
                                else:
                                    break 
                        if setup_success:
                            break
                            
                    os.unlink(tmp_path)
                    
                    if setup_success:
                        st.success("✅ မှတ်ဉာဏ်တည်ဆောက်ခြင်း ပြီးစီးပါပြီ! Step 2 သို့ သွားပါ။")
                    else:
                        st.error(f"Memory Setup Error: All API keys failed. Last error: {last_error}")
                        
                except Exception as e:
                    st.error(f"Memory Setup Error: {e}")
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)

with tab2:
    # 🔴 Check and create SFX folder if it doesn't exist
    if not os.path.exists("sfx"):
        os.makedirs("sfx")
        st.info("💡 'sfx' ဆိုတဲ့ ဖိုင်တွဲအသစ် တည်ဆောက်ထားပါတယ်။ အက်ရှင်အသံတွေမြည်ချင်ရင် အဲ့ဒီဖိုင်တွဲထဲကို sword.mp3, horse.mp3, thunder.mp3, crowd.mp3 အသံဖိုင်လေးတွေ ရှာထည့်ပေးထားပါ။")

    memory_data = None
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as jf:
                memory_data = json.load(jf)
        except json.JSONDecodeError:
            st.error("⚠️ မှတ်ဉာဏ်ဖိုင်ဟောင်း (Memory) ပျက်စီးနေပါသည်။ ကျေးဇူးပြု၍ Step 1 တွင် 'AI ကို ဖတ်ခိုင်းပြီး မှတ်ဉာဏ်တည်ဆောက်ပါ' ခလုတ်ကို တစ်ခေါက်ပြန်နှိပ်ပေးပါ။")
            try:
                os.remove(MEMORY_FILE)
            except:
                pass

    if memory_data:
        st.success(f"📚 Active Series: {memory_data.get('series_title', 'Unknown')}")
        
        col_ep1, col_ep2 = st.columns(2)
        with col_ep1:
            ep_number = st.number_input("Episode Number (အပိုင်း):", min_value=1, value=1)
            ep_focus = st.text_area("ဒီအပိုင်းမှာ ဘာအကြောင်း အဓိက ပြောမလဲ?", placeholder="ဥပမာ - ကွမ်းဆော်ကြောင်းဖြူမင်းကြီးကို ကျည်စိုးနှင့် စုက္ကတေးတို့က လှည့်စားပြီး နန်းချကာ ရဟန်းဝတ်ခိုင်းလိုက်သည့် အဖြစ်အပျက်။ အရည်းကြီးတို့၏ လွှမ်းမိုးမှု။")
        with col_ep2:
            voice_char = st.selectbox("Narrator Voice", ["Synergy Charon (Deep)", "ဇော်ဇော် (Male)", "အောင်အောင် (Deep)"])
            font_choice = st.selectbox("Subtitle Font", available_fonts)
            
        if st.button("📝 အဆင့် (၁) - ဇာတ်ညွှန်း အကြမ်းရေးဆွဲရန်"):
            st.session_state.render_success = False
            status_text = st.empty()
            
            keys = [k.strip() for k in api_key_input.split(",") if k.strip()]
            raw_script = None
            last_error = None
            script_success = False
            
            for key in keys:
                for attempt in range(3): 
                    try:
                        status_text.markdown(f"**🚀 ဇာတ်ညွှန်း ရေးသားနေပါသည်... (Attempt {attempt+1})**")
                        client = genai.Client(api_key=key)
                        char_bible = json.dumps(memory_data.get("characters", {}))
                        global_style = memory_data.get("global_narrative_style", "")
                        global_art_style = memory_data.get("global_art_style", "High-quality 2D digital art, masterpiece webtoon style")
                        
                        # 🔴 PROMPT UPDATE: Cinematic Camera Angles နှင့် ရှုခင်းကျယ်များ ထည့်သွင်းစေရန် အမိန့်အသစ်များ
                        script_prompt = f"""Write Episode {ep_number} of the series based on this plot: "{ep_focus}".
                        GLOBAL STYLE: {global_style}
                        GLOBAL ART STYLE: {global_art_style}
                        CHARACTER BIBLE: {char_bible}
                        
                        CRITICAL WORLD-BUILDING & TIMELINE AWARENESS:
                        1. Adapt the Vibe: The visual tone MUST match the timeline of the provided plot.
                           - EARLY ERA (Pre-reforms): Use "dark cinematic lighting, gritty, rustic, gloomy". DO NOT mention golden pagodas.
                           - GOLDEN ERA (Shin Arahan/Later): Use "warm golden lighting, majestic, glorious". Include "golden pagodas, thriving empire".
                        2. Cultural Accuracy: ALL scenes MUST be explicitly tagged with "Ancient Myanmar aesthetic, Southeast Asian, traditional Burmese attire". Absolutely NO Chinese or East Asian clothing/tropes.
                        
                        3. CINEMATIC COMPOSITION (CRITICAL RULE): 
                           You MUST vary the camera angles to match the story. DO NOT just generate close-ups of characters for every scene.
                           - For scenes in palaces, massive army marches, or traveling to landscapes (like Mount Popa), start the tag with "Wide-angle establishing shot, massive scale, panoramic view".
                           - For action, fights, or crowds, use "Long shot, dynamic action".
                           - ONLY use character descriptions for dialogue or emotional close-up moments. Describe the grand environment vividly.

                        STRICT INSTRUCTIONS:
                        1. Write in engaging spoken Burmese. Start with a 3-second viral hook.
                        2. You MUST break the story into sequential blocks (scenes).
                        3. For EVERY block, you MUST provide 3 tags exactly in this order:
                           [SCENE: <Shot Type (e.g., Wide-angle/Medium/Close-up)>, <Vivid Environment/Action Description>, <Dynamic Art Style Tags Based on Era>, STRICTLY Ancient Myanmar/Bagan aesthetic, NO Chinese/East Asian tropes]
                           [SFX: SWORD or HORSE or THUNDER or CROWD or NONE]
                           [NARRATION: <The Burmese spoken script for this block>]
                        
                        Do not add any other text outside these blocks!"""
                        
                        res = client.models.generate_content(model="gemini-2.5-flash", contents=script_prompt)
                        st.session_state.script_draft = res.text.strip()
                        script_success = True
                        status_text.success("✅ ဇာတ်ညွှန်းရေးဆွဲပြီးပါပြီ။ အောက်တွင် စစ်ဆေးပြင်ဆင်ပါ။")
                        break  
                    except Exception as e:
                        last_error = e
                        if "503" in str(e) or "429" in str(e):
                            wait_time = 5 * (attempt + 1)
                            status_text.warning(f"⚠️ Server ကြပ်နေပါသည်။ စက္ကန့် {wait_time} ခေတ္တစောင့်ဆိုင်းပြီး ပြန်လည်ကြိုးစားပါမည်...")
                            time.sleep(wait_time)
                            continue
                        else:
                            break 
                if script_success:
                    break
                    
            if not script_success:
                st.error(f"Script Error: All API keys failed. Last error: {last_error}")

        if st.session_state.script_draft:
            st.markdown("---")
            st.markdown("### ✍️ ဇာတ်ညွှန်းကို စစ်ဆေး/ပြင်ဆင်ပါ (Script Review)")
            st.caption("မှတ်ချက် - AI ရေးထားသော ဇာတ်ညွှန်းများကို လိုအပ်သလို ပြင်ဆင်နိုင်ပါသည်။ `[SCENE]`, `[SFX]`, `[NARRATION]` tag များကို မဖျက်မိစေရန် သတိပြုပါ။")
            
            edited_script = st.text_area("Final Script Code", value=st.session_state.script_draft, height=400)
            
            if st.button("🎬 အဆင့် (၂) - ဇာတ်ညွှန်းအတိုင်း ဗီဒီယို ဖန်တီးရန် (RENDER NOW)"):
                st.session_state.render_success = False
                cleanup_temp_files()
                run_id = str(int(time.time()))
                
                status_text_render = st.empty()
                pbar = st.progress(0)
                keys = [k.strip() for k in api_key_input.split(",") if k.strip()]
                
                status_text_render.markdown("**🔍 ဇာတ်ကွက်များကို စိစစ်နေပါသည်...**")
                pbar.progress(10)
                block_pattern = re.compile(
                    r'\[SCENE:\s*(.*?)\]\s*'
                    r'\[SFX:\s*(.*?)\]\s*'
                    r'\[NARRATION:\s*(.*?)\](?=\s*\[SCENE:|\s*$)',
                    re.DOTALL
                )
                matches = block_pattern.findall(edited_script)
                blocks = []
                if matches:
                    for scene, sfx, narration in matches:
                        narration = re.sub(r'\s+', ' ', narration).strip()
                        blocks.append({
                            'scene': scene.strip(),
                            'sfx': sfx.strip(),
                            'narration': narration
                        })
                else:
                    current_block = {}
                    for line in edited_script.split('\n'):
                        line = line.strip()
                        if line.startswith('[SCENE:'):
                            if current_block:
                                blocks.append(current_block)
                            current_block = {'scene': line.replace('[SCENE:', '').replace(']', '').strip(), 'sfx': 'NONE', 'narration': ''}
                        elif line.startswith('[SFX:') and current_block:
                            current_block['sfx'] = line.replace('[SFX:', '').replace(']', '').strip()
                        elif line.startswith('[NARRATION:') and current_block:
                            current_block['narration'] = line.replace('[NARRATION:', '').replace(']', '').strip()
                        elif line and current_block and not line.startswith('['):
                            current_block['narration'] += " " + line
                    if current_block:
                        blocks.append(current_block)
                
                if not blocks:
                    st.error("ဇာတ်ညွှန်း Format လွဲချော်သွားပါသည်။ [SCENE], [SFX], [NARRATION] tag များ မှန်ကန်စွာ ပါဝင်ခြင်း ရှိမရှိ စစ်ဆေးပါ။")
                    st.stop()

                final_clips = []
                temp_files = []
                
                for i, blk in enumerate(blocks):
                    status_text_render.markdown(f"**🎬 Scene {i+1}/{len(blocks)} အား ဖန်တီးနေပါသည်...**")
                    pbar.progress(20 + int((i/len(blocks))*60))
                    
                    narration = blk['narration']
                    scene_prompt = blk['scene']
                    sfx_tag = blk['sfx']
                    
                    a_out = f"temp_aud_{i}.wav"
                    i_out = f"temp_img_{i}.jpg"
                    v_out = f"temp_vid_{i}.mp4"
                    anim_out = f"temp_anim_{i}.mp4"
                    temp_files.extend([a_out, i_out, v_out, anim_out])
                    
                    tts_success = False
                    last_tts_error = None
                    
                    for key in keys:
                        for attempt in range(3):
                            try:
                                run_async(generate_tts(narration, voice_char, a_out,
                                                       engine="Google Synergy TTS (Flash 3.1 Preview)" if "Synergy" in voice_char else "Edge-TTS",
                                                       gemini_key=key))
                                tts_success = True
                                break 
                            except Exception as e:
                                last_tts_error = e
                                error_str = str(e)
                                if "429" in error_str or "503" in error_str:
                                    wait_time = 5 * (attempt + 1)
                                    status_text_render.warning(f"⚠️ TTS API Limit (Scene {i+1}). စက္ကန့် {wait_time} စောင့်ပြီး နောက် Key ဖြင့် စမ်းသပ်နေပါသည်...")
                                    time.sleep(wait_time)
                                    continue
                                else:
                                    break 
                        if tts_success:
                            break 
                            
                    if not tts_success:
                        st.error(f"TTS Error (Scene {i+1}): All API keys failed or quota exceeded. Last error: {last_tts_error}")
                        st.stop()
                    
                    dur = get_wav_duration(a_out)
                    if dur < 1.0:
                        dur = 3.0  
                    
                    seed = random.randint(1, 1000000) 
                    style_suffix = ", masterpiece, 2D digital art, webtoon style, STRICTLY ancient Burmese aesthetic, Southeast Asian, traditional Myanmar clothing, NO Chinese, NO Japanese, trending on artstation"
                    encoded_prompt = urllib.parse.quote(scene_prompt + style_suffix)
                    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=720&height=1280&nologo=true&seed={seed}"
                    
                    max_retries = 3
                    image_success = False
                    
                    for attempt in range(max_retries):
                        try:
                            resp = requests.get(url, timeout=60)
                            if resp.status_code == 200 and 'image' in resp.headers.get('Content-Type', ''):
                                with open(i_out, "wb") as f:
                                    f.write(resp.content)
                                image_success = True
                                break  
                            else:
                                status_text_render.warning(f"⚠️ Scene {i+1} Image Server Busy. Retrying ({attempt+1}/{max_retries})...")
                                time.sleep(3)
                        except requests.exceptions.Timeout:
                            status_text_render.warning(f"⚠️ Scene {i+1} Image Timeout. Retrying ({attempt+1}/{max_retries})...")
                            time.sleep(3)
                        except Exception as e:
                            status_text_render.warning(f"⚠️ Scene {i+1} Image Error: {e}. Retrying ({attempt+1}/{max_retries})...")
                            time.sleep(3)
                    
                    if not image_success:
                        st.error(f"Image generation failed for scene {i+1} after {max_retries} attempts. Server is likely overloaded.")
                        st.stop()
                        
                    if not animate_image_with_fallback(i_out, anim_out, dur):
                        st.error(f"Animation failed for scene {i+1}")
                        st.stop()
                    
                    wrap_text = "\n".join(textwrap.wrap(narration, 25))
                    safe_text = wrap_text.replace(':', '\\:').replace("'", "'\\''")
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
                    
                    # 🔴 SFX MIXING UPDATE (ဖိုင်မရှိပါက သတိပေးမည့်စနစ်)
                    aud_stream = ffmpeg.input(a_out).audio
                    if sfx_tag != "NONE":
                        sfx_path = f"sfx/{sfx_tag.lower()}.mp3"
                        if os.path.exists(sfx_path):
                            sfx_stream = ffmpeg.input(sfx_path).audio.filter('volume', 0.8)
                            aud_stream = ffmpeg.filter([aud_stream, sfx_stream], 'amix', inputs=2, duration='first')
                        else:
                            st.toast(f"⚠️ Sound Effect ဖိုင် မရှိပါ: {sfx_path} ကို 'sfx' ဖိုင်တွဲထဲတွင် ရှာမတွေ့ပါ။")
                    
                    try:
                        ffmpeg.output(vid_stream, aud_stream, v_out,
                                      vcodec='libx264', acodec='aac', t=dur
                                      ).overwrite_output().run(cmd=FFMPEG_BINARY, quiet=True)
                    except ffmpeg.Error as e:
                        st.error(f"FFmpeg render error for scene {i+1}: {e.stderr.decode()}")
                        st.stop()
                        
                    final_clips.append(v_out)
                    
                status_text_render.markdown("**🎞️ ဗီဒီယိုအားလုံးကို ဆက်စပ်နေပါသည်...**")
                pbar.progress(90)
                concat_file = f"concat_list_{run_id}.txt"
                with open(concat_file, "w") as f:
                    for c in final_clips:
                        f.write(f"file '{os.path.abspath(c)}'\n")
                temp_files.append(concat_file)
                
                out_final = f"EPISODE_{ep_number}_{run_id}.mp4"
                try:
                    subprocess.run([FFMPEG_BINARY, "-y", "-f", "concat", "-safe", "0",
                                    "-i", concat_file, "-c", "copy", out_final],
                                   capture_output=True, check=True)
                except subprocess.CalledProcessError as e:
                    st.error(f"Final concatenation failed: {e.stderr.decode()}")
                    st.stop()
                
                st.session_state.final_video_path = out_final
                st.session_state.render_success = True
                status_text_render.markdown("**✅ အားလုံးအောင်မြင်စွာ ပြီးစီးပါပြီ!**")
                pbar.progress(100)
                
                for tf in temp_files:
                    if os.path.exists(tf):
                        try:
                            os.remove(tf)
                        except Exception:
                            pass
                            
            if st.session_state.get("render_success"):
                st.balloons()
                st.success(f"🎉 Episode {ep_number} အောင်မြင်စွာ ထွက်လာပါပြီ!")
                if os.path.exists(st.session_state.final_video_path):
                    st.video(st.session_state.final_video_path)
                    st.markdown(get_download_link(st.session_state.final_video_path, f"Epic_Episode_{ep_number}.mp4", "📥 Download Episode Video"), unsafe_allow_html=True)
    else:
        st.warning("⚠️ မှတ်ဉာဏ်ဖိုင် (Memory) မရှိသေးပါ။ Step 1 တွင် အရင်ဆုံး Setup လုပ်ပါ။")
