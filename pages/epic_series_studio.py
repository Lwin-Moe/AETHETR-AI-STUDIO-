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
import json5                     # JSON5 (strict JSON မဟုတ်လည်း parse လုပ်နိုင်ရန်)
from google import genai
from google.genai import types
from core_engines.audio_tts import generate_tts
from utils.helpers import get_available_fonts, get_download_link, cleanup_temp_files, load_key
from core_engines.video_render import FFMPEG_BINARY

# ffmpeg-python binary path
ffmpeg.ffmpeg = FFMPEG_BINARY

# ==================== ASYNC WRAPPER (Streamlit event loop safe) ====================
def run_async(coro):
    """asycio.run အစား သုံးပါ။"""
    def _run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor() as executor:
        return executor.submit(_run).result()

# ==================== GEMINI KEY ROTATION HELPER ====================
def gemini_generate_with_keys(api_keys, model, contents, max_retries_per_key=2):
    """
    Comma ဖြုတ်ထားသော Gemini API Keys များကို အစဉ်တိုင်းစမ်းပါ။
    503/429 ကဲ့သို့ transient error များတွင် နောက် key သို့ ပြောင်းပြီး ထပ်ကြိုးစားပါသည်။
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
                    if "503" in err or "UNAVAILABLE" in err or "429" in err or "RESOURCE_EXHAUSTED" in err:
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

# --- CORE FUNCTIONS (မူလအတိုင်း + ထပ်ဖြည့်မှုများ) ---
def get_wav_duration(file_path):
    try:
        with wave.open(file_path, 'r') as wf:
            return wf.getnframes() / float(wf.getframerate())
    except Exception:
        return 0.0

def call_replicate_svd(image_path, out_path, api_token):
    """Stable Video Diffusion via Replicate API"""
    try:
        import replicate
        client = replicate.Client(api_token=api_token)
        with open(image_path, "rb") as f:
            output = client.run(
                "stability-ai/stable-video-diffusion:3f0457e4619daac51203dedb472816fd4af51f3149fa7a9e0b5ffcf1b8172438",
                input={
                    "input_image": f,
                    "sizing_strategy": "maintain_aspect_ratio",
                    "frames_per_second": 6,
                    "video_length": "25_frames_with_svd_xt"
                }
            )
        if isinstance(output, str):
            video_resp = requests.get(output)
            with open(out_path, "wb") as vf:
                vf.write(video_resp.content)
        else:
            with open(out_path, "wb") as vf:
                vf.write(output.read())
        return True
    except Exception as e:
        st.warning(f"Replicate error: {e}")
        return False

def animate_image_with_fallback(img_path, out_path, duration, w=720, h=1280, replicate_key=None):
    """
    Replicate API ရှိလျှင် ၎င်းကို ဦးစားပေးသုံး၊ မရပါက FFmpeg Zoompan ဖြင့် fallback လုပ်မည်။
    """
    # Replicate စမ်းမည်
    if replicate_key:
        success = call_replicate_svd(img_path, out_path, replicate_key)
        if success:
            # ရလာတဲ့ video ရဲ့ကြာချိန် စစ်၊ လိုအပ်ရင် loop ပတ်
            try:
                probe = ffmpeg.probe(out_path)
                v_dur = float(probe['format']['duration'])
            except:
                v_dur = 0
            if v_dur < duration:
                looped = out_path + "_looped.mp4"
                subprocess.run([FFMPEG_BINARY, "-y", "-stream_loop", "-1", "-i", out_path,
                                "-t", str(duration), "-c", "copy", looped],
                               capture_output=True, check=True)
                os.replace(looped, out_path)
            return True

    # Fallback FFmpeg Zoompan (မူရင်း)
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

# --- UI & LOGIC (မူရင်းကို ထိန်းသိမ်းထားသည်) ---
st.markdown('<div class="setting-panel"><h2>📚 Epic Series Storytelling Studio</h2>', unsafe_allow_html=True)
st.markdown("PDF စာအုပ်ကို တစ်ခါတည်းမှတ်ဉာဏ်သွင်းပြီး၊ Consistency အပြည့်အဝဖြင့် ဇာတ်လမ်းတွဲများ ဆက်တိုက်ထုတ်လုပ်ပါ။")

MEMORY_FILE = "series_memory.json"
available_fonts = get_available_fonts()

tab1, tab2 = st.tabs(["⚙️ Step 1: Memory Setup (စာအုပ်ဖတ်ခိုင်းရန်)", "🎬 Step 2: Generate Episode (ဇာတ်လမ်းတွဲ ထုတ်ရန်)"])

# API Key များကို comma ဖြုတ်၍ list အဖြစ်သိမ်းမည်
raw_key_input = load_key("GEMINI_API_KEY")
gemini_keys = [k.strip() for k in raw_key_input.split(",") if k.strip()] if raw_key_input else []

with tab1:
    st.info("💡 ပထမဆုံးအကြိမ် တစ်ခါသာ လုပ်ရန် လိုအပ်ပါသည်။ စာအုပ်ကို ဖတ်ပြီး ဇာတ်ကောင်ရုပ်ထွက်များကို အသေမှတ်သားပါမည်။")
    series_name = st.text_input("ဇာတ်လမ်းတွဲ အမည်:", placeholder="ဥပမာ - အိုဘယ့် အနော်ရထာ")
    uploaded_pdf = st.file_uploader("PDF စာအုပ် တင်ပါ", type=["pdf"])

    if st.button("🧠 AI ကို ဖတ်ခိုင်းပြီး မှတ်ဉာဏ်တည်ဆောက်ပါ"):
        if not gemini_keys or not uploaded_pdf or not series_name:
            st.error("API Key နှင့် PDF ကို ထည့်ပေးပါ။")
        else:
            # PyMuPDF ရှိမရှိစစ်
            try:
                import fitz
            except ImportError:
                st.error("PyMuPDF လိုအပ်ပါသည်။ pip install pymupdf")
                st.stop()

            status = st.empty()
            status.write("⏳ PDF ကို ဖတ်နေပါသည်...")
            memory_data = {
                "series_title": series_name,
                "global_narrative_style": "Third-Person Omniscient Cinematic Tone. Epic historical narration.",
                "characters": {},
                "parts": []
            }

            with fitz.open(stream=uploaded_pdf.read(), filetype="pdf") as doc:
                total_pages = doc.page_count
                # ---- Stage 1: Characters (chunk) ----
                status.write(f"👥 ဇာတ်ကောင်များကို ဖတ်နေပါသည်... (စာမျက်နှာ ၁-{total_pages})")
                chunk_size = 15
                for start in range(0, total_pages, chunk_size):
                    end = min(start+chunk_size, total_pages)
                    chunk_text = ""
                    for i in range(start, end):
                        chunk_text += doc[i].get_text()
                    prompt = f"""Extract main characters from this Burmese historical text.
For each character provide a detailed English visual description (face, age, 11th century Bagan attire, weapons).
Output ONLY valid JSON: {{"characters": {{"CharacterName": "description"}}}}.
Text: {chunk_text[:25000]}"""
                    try:
                        res = gemini_generate_with_keys(gemini_keys, "gemini-2.5-flash", prompt)
                        clean = res.text.replace('```json','').replace('```','').strip()
                        chunk_chars = json5.loads(clean).get("characters", {})
                        memory_data["characters"].update(chunk_chars)
                    except Exception as e:
                        st.warning(f"Character chunk error (pages {start}-{end}): {e}")

                status.write(f"✅ ဇာတ်ကောင် {len(memory_data['characters'])} ခု ဖတ်ပြီးပါပြီ။")

                # ---- Stage 2: Parts ----
                status.write("📖 ဇာတ်လမ်းကို ၃ မိနစ်စာ အပိုင်းများ ခွဲနေပါသည်...")
                # အရှည်ကြီးဖြစ်နိုင်သဖြင့် ပထမ 120 စာမျက်နှာသာယူပါမည်
                full_text = ""
                for i in range(min(total_pages, 120)):
                    full_text += doc[i].get_text()
                char_bible = json.dumps(memory_data["characters"], ensure_ascii=False)
                part_prompt = f"""You are an expert Burmese historical scriptwriter.
Based on the following Burmese historical text, divide the entire story into sequential parts.
Each part must be around 3 minutes of spoken narration (400-500 words).
For EVERY part, provide:
- part_number
- summary (1 Burmese sentence)
- blocks (array of scenes). Each block must have:
    [SCENE]: Wide cinematic shot in English, containing character visual from {char_bible}, Bagan period background, atmospheric lighting, epic graphic novel style.
    [SFX]: relevant sound effect (SWORD, HORSE, CROWD, etc.)
    [NARRATION]: Exact Burmese narration for this block.
Output ONLY valid JSON: {{"parts": [{{"part_number":1, "summary":"...", "blocks":[...]}}]}}.
Text: {full_text[:80000]}"""
                try:
                    res = gemini_generate_with_keys(gemini_keys, "gemini-2.5-flash", part_prompt)
                    clean = res.text.replace('```json','').replace('```','').strip()
                    parts_data = json5.loads(clean)
                    memory_data["parts"] = parts_data.get("parts", [])
                except Exception as e:
                    st.error(f"Part division error: {e}")
                    st.stop()

            # Save memory
            with open(MEMORY_FILE, "w", encoding="utf-8") as f:
                json.dump(memory_data, f, ensure_ascii=False, indent=2)
            status.success(f"✅ မှတ်ဉာဏ်တည်ဆောက်ပြီးပါပြီ! အပိုင်း {len(memory_data['parts'])} ပိုင်း အဆင်သင့်ဖြစ်ပါပြီ။")

with tab2:
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "r", encoding="utf-8") as jf:
            memory_data = json.load(jf)
        st.success(f"📚 Active Series: {memory_data.get('series_title', 'Unknown')}")
        st.json(memory_data.get("characters", {}))

        col_ep1, col_ep2 = st.columns(2)
        with col_ep1:
            # Part ရွေးချယ်ရန်
            parts_list = memory_data.get("parts", [])
            if parts_list:
                part_numbers = [p["part_number"] for p in parts_list]
                ep_number = st.selectbox("ထုတ်လုပ်မည့် Part (အပိုင်း)", part_numbers)
            else:
                ep_number = st.number_input("Episode Number (အပိုင်း):", min_value=1, value=1)
            selected_part = next((p for p in parts_list if p["part_number"] == ep_number), None)
            if selected_part:
                st.info(f"📖 Part {ep_number} Summary: {selected_part.get('summary', '')}")
                ep_focus = st.text_area("အထူးထည့်သွင်းလိုသည့် အကြောင်းအရာ (Optional)", placeholder="ဤအပိုင်းတွင် ထပ်ထည့်ချင်သည်များ...")
            else:
                ep_focus = st.text_area("ဒီအပိုင်းမှာ ဘာအကြောင်း အဓိက ပြောမလဲ?", placeholder="ဥပမာ - စုက္ကတေးနဲ့ အနော်ရထာ မြင်းကပါချောင်းမှာ စီးချင်းထိုးသည့် အခန်း။")

        with col_ep2:
            voice_char = st.selectbox("Narrator Voice", ["Synergy Charon (Deep)", "ဇော်ဇော် (Male)", "အောင်အောင် (Deep)"])
            font_choice = st.selectbox("Subtitle Font", available_fonts)
            st.markdown("---")
            st.markdown("🎞️ **Animation API (Replicate)**")
            use_replicate = st.checkbox("Replicate API ဖြင့် Animation လုပ်မည်", value=False)
            replicate_key = None
            if use_replicate:
                replicate_key = st.text_input("Replicate API Key", type="password")

        if st.button("🚀 GENERATE EPISODE NOW"):
            st.session_state.render_success = False
            cleanup_temp_files()
            run_id = str(int(time.time()))
            pbar = st.progress(0, text="🚀 ဇာတ်ညွှန်း ရေးသားနေပါသည်...")

            # Script blocks (memory မှ ယူမည်)
            if selected_part and "blocks" in selected_part:
                blocks = selected_part["blocks"]
                st.info("✅ Pre-processed script blocks loaded from memory.")
            else:
                st.error("Memory ထဲတွင် ဤအပိုင်းအတွက် Script မရှိပါ။ Step 1 ကို ပြန်လုပ်ပါ။")
                st.stop()

            # --- PROCESS EACH BLOCK ---
            final_clips = []
            for i, blk in enumerate(blocks):
                pbar.progress(30 + int((i/len(blocks))*50), text=f"🎬 Scene {i+1}/{len(blocks)} အား ဖန်တီးနေပါသည်...")
                narration = blk['narration']
                scene_prompt = blk['scene']
                sfx_tag = blk['sfx']

                a_out = f"temp_aud_{i}.wav"
                i_out = f"temp_img_{i}.jpg"
                v_out = f"temp_vid_{i}.mp4"
                anim_out = f"temp_anim_{i}.mp4"

                # A. Audio
                run_async(generate_tts(narration, voice_char, a_out,
                                       engine="Google Synergy TTS (Flash 3.1 Preview)" if "Synergy" in voice_char else "Edge-TTS",
                                       gemini_key=gemini_keys[0] if gemini_keys else None))
                dur = get_wav_duration(a_out)
                if dur < 1.0: dur = 3.0

                # B. Image (Wide shot, historical accuracy, character consistency)
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
                    replicate_key=replicate_key if use_replicate else None
                )
                if not anim_success:
                    st.error(f"Animation failed for scene {i+1}")
                    st.stop()

                # D. Subtitles
                wrap_text = "\n".join(textwrap.wrap(narration, 25))
                with open("temp_sub.txt", "w", encoding="utf-8") as tf:
                    tf.write(wrap_text)
                safe_font = os.path.abspath(font_choice).replace('\\', '/').replace(':', '\\:')
                vid_stream = ffmpeg.input(anim_out).video
                vid_stream = ffmpeg.filter(vid_stream, 'drawtext', textfile='temp_sub.txt',
                                           fontfile=safe_font, fontcolor='yellow', fontsize=32,
                                           bordercolor='black', borderw=3,
                                           x='(w-text_w)/2', y='h-text_h-150', text_align='C')

                # E. Mix Audio & SFX
                aud_stream = ffmpeg.input(a_out).audio
                sfx_path = f"sfx/{sfx_tag.lower()}.mp3"
                if sfx_tag != "NONE" and os.path.exists(sfx_path):
                    sfx_stream = ffmpeg.input(sfx_path).audio.filter('volume', 0.8)
                    aud_stream = ffmpeg.filter([aud_stream, sfx_stream], 'amix', inputs=2, duration='first')

                ffmpeg.output(vid_stream, aud_stream, v_out,
                              vcodec='libx264', acodec='aac', t=dur
                              ).overwrite_output().run(cmd=FFMPEG_BINARY, quiet=True)
                final_clips.append(v_out)

            # --- MASTER CONCATENATION ---
            pbar.progress(90, text="🎞️ ဗီဒီယိုအားလုံးကို ဆက်စပ်နေပါသည်...")
            with open("concat_list.txt", "w") as f:
                for c in final_clips:
                    f.write(f"file '{os.path.abspath(c)}'\n")
            out_final = f"EPISODE_{ep_number}_{run_id}.mp4"
            subprocess.run([FFMPEG_BINARY, "-y", "-f", "concat", "-safe", "0",
                            "-i", "concat_list.txt", "-c", "copy", out_final],
                           capture_output=True, check=True)

            st.session_state.final_video_path = out_final
            st.session_state.render_success = True
            pbar.progress(100, text="✅ အားလုံးအောင်မြင်စွာ ပြီးစီးပါပြီ!")

        # Dashboard Display (မူရင်းအတိုင်း)
        if st.session_state.get("render_success"):
            st.balloons()
            st.success(f"🎉 Episode {ep_number} အောင်မြင်စွာ ထွက်လာပါပြီ!")
            if os.path.exists(st.session_state.final_video_path):
                st.video(st.session_state.final_video_path)
                st.markdown(get_download_link(st.session_state.final_video_path, f"Epic_Episode_{ep_number}.mp4", "📥 Download Episode Video"), unsafe_allow_html=True)
    else:
        st.warning("⚠️ မှတ်ဉာဏ်ဖိုင် (Memory) မရှိသေးပါ။ Step 1 တွင် အရင်ဆုံး Setup လုပ်ပါ။")
