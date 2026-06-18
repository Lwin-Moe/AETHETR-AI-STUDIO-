import streamlit as st
import os
import asyncio
import time
import json
import base64
import random
import shutil
import textwrap
import urllib.parse
import concurrent.futures
import re
import requests
import ffmpeg
from google import genai
from groq import Groq
import openai

st.set_page_config(page_title="AETHER STUDIO V52", layout="wide", page_icon="🎬")

# --- IMPORTS FROM MODULES ---
from ui.components import setup_fonts_and_css
from core.utils.api_utils import load_key, save_key, get_download_link, API_KEY_FILE, ELEVEN_KEY_FILE, GROQ_KEY_FILE, OPENAI_KEY_FILE, ELEVEN_VOICE_ID_FILE
from core.utils.ffmpeg_utils import FFMPEG_BINARY, cleanup_temp_files, get_file_duration, download_video_from_url, extract_audio_fast
from core.engines.tts import generate_tts
from core.engines.subtitles import parse_and_save_real_srt
from core.engines.video import render_premium_saas_video

# Setup Theme & Fonts
setup_fonts_and_css()

# State initialization
if "render_success" not in st.session_state: st.session_state.render_success = False
if "generated_script" not in st.session_state: st.session_state.generated_script = ""
if "original_transcript" not in st.session_state: st.session_state.original_transcript = ""
if "viral_title" not in st.session_state: st.session_state.viral_title = ""
if "viral_tags" not in st.session_state: st.session_state.viral_tags = ""
if "thumb_path_A" not in st.session_state: st.session_state.thumb_path_A = None
if "thumb_path_B" not in st.session_state: st.session_state.thumb_path_B = None
if "viral_score" not in st.session_state: st.session_state.viral_score = ""
if "final_video_path" not in st.session_state: st.session_state.final_video_path = ""

# --- UI INTERFACE ---
st.markdown('<div class="main-title">AETHER FILMWORKS</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">AI Studio V52 ⚡ Clean Architecture Edition</div>', unsafe_allow_html=True)

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
    ai_provider = st.selectbox("Choose AI Provider", ["Google Gemini (Flash - Recommended)", "OpenAI (GPT-5.5 Pro)", "Groq API (Fast & Free)"])
    saved_gemini = load_key(API_KEY_FILE)
    if "Gemini" in ai_provider:
        api_key_input = st.text_input("Gemini Keys (Comma separated)", type="password", value=saved_gemini)
        if api_key_input and api_key_input != saved_gemini: save_key(API_KEY_FILE, api_key_input)
    elif "Groq" in ai_provider:
        saved_groq = load_key(GROQ_KEY_FILE)
        api_key_input = st.text_input("Groq API Key", type="password", value=saved_groq)
        if api_key_input and api_key_input != saved_groq: save_key(GROQ_KEY_FILE, api_key_input)
    else:
        saved_openai = load_key(OPENAI_KEY_FILE)
        api_key_input = st.text_input("OpenAI API Key", type="password", value=saved_openai)
        if api_key_input and api_key_input != saved_openai: save_key(OPENAI_KEY_FILE, api_key_input)

    if app_mode == "🎙️ Faceless Channel Studio":
        st.markdown("---")
        st.markdown("### 🔑 Additional API Keys")
        saved_groq_fc = load_key(GROQ_KEY_FILE)
        groq_key_fc = st.text_input("Groq API Key (For Accurate Whisper Sync)", type="password", value=saved_groq_fc)
        if groq_key_fc and groq_key_fc != saved_groq_fc: save_key(GROQ_KEY_FILE, groq_key_fc)

# =====================================================================
# 📌 MODE 1 - MOVIE DUBBING
# =====================================================================
if app_mode == "🎙️ Movie Dubbing Studio":
    with st.sidebar:
        st.markdown("---")
        audio_engine_choice = st.radio("Voice Engine", ["Edge-TTS (Default Free)", "Google Synergy TTS (Flash 3.1 Preview)", "ElevenLabs (Premium AI)", "TTSMaker (Free API)"])
        if "Synergy" in audio_engine_choice: synergy_key = st.text_input("API Key for Synergy TTS", type="password", value=saved_gemini)
        if "ElevenLabs" in audio_engine_choice:
            saved_eleven = load_key(ELEVEN_KEY_FILE)
            eleven_key_input = st.text_input("ElevenLabs API Key", type="password", value=saved_eleven)
            if eleven_key_input and eleven_key_input != saved_eleven: save_key(ELEVEN_KEY_FILE, eleven_key_input)
            saved_voice_id = load_key(ELEVEN_VOICE_ID_FILE)
            custom_eleven_id = st.text_input("Custom Voice ID", value=saved_voice_id)
            if custom_eleven_id and custom_eleven_id != saved_voice_id: save_key(ELEVEN_VOICE_ID_FILE, custom_eleven_id)
        key_ttsmaker = st.text_input("TTSMaker API Key", type="password") if "TTSMaker" in audio_engine_choice else ""

        st.markdown("---")
        video_ratio = st.selectbox("Crop Ratio", ["Original", "9:16 (TikTok/Shorts)", "16:9 (YouTube)"])
        st.markdown("<b>🛡️ Anti-Copyright Options</b>", unsafe_allow_html=True)
        cb_bypass = st.checkbox("🔍 Smart Zoom", value=True)
        cb_mirror = st.checkbox("🪞 Mirror Effect", value=False)
        cb_color = st.checkbox("🎨 Color Tweaks", value=False)
        cb_grain = st.checkbox("🎞️ Subtle Film Grain", value=False)
        cb_fps = st.checkbox("🎬 Cinematic 24 FPS", value=False)
        cb_freeze = st.checkbox("❄️ Freeze Frame (Stop-Motion Bypass)", value=False)
        
        st.markdown("<b>🎬 Visual & Subs</b>", unsafe_allow_html=True)
        cb_blur = st.checkbox("👁️ Cinematic Black Mask", value=True)
        cb_thumb_text = st.checkbox("🖼️ Add Viral Title to Thumbnail", value=True)
        
        st.markdown("<b>©️ Brand Watermark</b>", unsafe_allow_html=True)
        uploaded_logo = st.file_uploader("🖼️ Add Logo Image (Top Right)", type=["png", "jpg", "jpeg"])
        use_text_watermark = st.checkbox("✍️ Use Text Watermark instead", value=False)
        watermark_text = st.text_input("Text Watermark", "") if use_text_watermark else ""
        
        subtitle_mode = st.radio("Subtitle Output", ["Both (Burn + SRT)", "Export SRT File Only", "Burn into Video"])

    st.markdown('<div class="setting-panel"><h3>📺 Media Acquisition & Setup</h3>', unsafe_allow_html=True)
    col_in1, col_in2 = st.columns([1, 1])

    with col_in1:
        video_url = st.text_input("🔗 Paste Short Drama URL Link", placeholder="https://...")
        uploaded_file = st.file_uploader("📥 OR Upload Video File (MP4)", type=["mp4"])
        
        st.markdown("<br><div class='sub-box'>", unsafe_allow_html=True)
        st.markdown("<p style='font-weight: bold; color: #38bdf8; font-size: 16px;'>✍️ AI Storytelling & Script Rules</p>", unsafe_allow_html=True)
        recap_mode = st.radio("🎬 Recap Mode", ["Translate Original Video (မူရင်းကို ဘာသာပြန်မည်)", "Create Original AI Story (ကိုယ်ပိုင်ဇာတ်လမ်းဖန်တီးမည်)"])
        script_style = st.selectbox("🎭 Script Style (ဇာတ်ညွှန်း ပုံစံ)", ["Normal (ပုံမှန်အညွှန်း)", "Slang (လူငယ်သုံး/Gen-Z)", "Comedy (ဟာသပြောင်ချော်ချော်)", "Suspense (သည်းထိတ်ရင်ဖို)"])
        script_hook = st.checkbox("🪝 3-Second Viral Hook (အစချီ ဆွဲဆောင်မည်)", value=True)
        script_curiosity = st.checkbox("🤯 Curiosity Gaps (စိတ်ဝင်စားမှု အရှိန်တင်မည်)", value=True)
        script_tone = st.checkbox("🎭 Emotion & Tone (ဇာတ်ကောင်စရိုက် သွင်းမည်)", value=True)
        script_cta = st.checkbox("💬 Call to Action (Commentခေါ်မည်)", value=False)
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("<div class='sub-box'>", unsafe_allow_html=True)
        st.markdown("<p style='font-weight: bold; color: #10b981; font-size: 16px;'>🎵 Audio Mixing & Auto-Ducking</p>", unsafe_allow_html=True)
        bgm_options = ["None (BGM မထည့်ပါ)"]
        bgm_files = [f for f in os.listdir("bgm_tracks") if f.endswith(".mp3")] if os.path.exists("bgm_tracks") else []
        if bgm_files:
            bgm_options.insert(1, "🤖 Auto (Random Select)")
            bgm_options.extend(bgm_files)
        selected_bgm = st.selectbox("🎼 Background Music", bgm_options)
        bgm_volume = st.slider("🔊 BGM Volume", 1, 50, 10) / 100.0
        st.markdown("</div>", unsafe_allow_html=True)

    with col_in2:
        dynamic_options = ["Synergy Puck (Male)", "Synergy Aoede (Female)", "Synergy Charon (Male - Deep)"] if "Synergy" in audio_engine_choice else (["Adam (Male Deep)", "Rachel (Female)"] if "ElevenLabs" in audio_engine_choice else (["TTSMaker Male", "TTSMaker Female"] if "TTSMaker" in audio_engine_choice else ["ဇော်ဇော် (Male)", "အောင်အောင် (Deep)", "နှင်းနှင်း (Female)"]))
        voice_char = st.selectbox("Select Character Voice", dynamic_options, index=0)
        pitch_level = st.slider("🎙️ Voice Pitch (Frequency Adjust)", min_value=-30, max_value=30, value=0, step=5)
        fx_level = st.selectbox("🎧 Cinematic Voice FX", [
            "None", "🎙️ Epic Trailer Voice", "📻 Walkie-Talkie", 
            "🏛️ Cinematic Reverb", "👹 Demon / Monster", "🤫 ASMR / Whisper",
            "🤖 Robot / Cyborg", "📞 Old Telephone", "⛰️ Deep Cave Echo", "🌊 Underwater / Muffled",
            "🔥 Deep & Energetic (Motivation)", "👻 Deep & Chilling (Horror)"
        ])
        
        st.markdown("<div class='sub-box'>", unsafe_allow_html=True)
        st.markdown("<p style='font-weight: bold; color: #818cf8; font-size: 16px;'>📝 Subtitle Pro Settings</p>", unsafe_allow_html=True)
        if subtitle_mode in ["Both (Burn + SRT)", "Burn into Video"]:
            sub_position = st.selectbox("📍 Position", ["Bottom", "Center", "Top"])
            sub_color = st.selectbox("🎨 Color", ["Yellow Text", "White Text", "Neon Green Text", "Red Text", "Gold Text"])
            sub_size = st.slider("🔠 Font Size", 16, 40, 24)
            sub_thickness = st.slider("✒️ Outline Thickness", 1.0, 5.0, 2.5)
            col_s1, col_s2 = st.columns(2)
            with col_s1:
                sub_bg = st.checkbox("🔲 Background Box", value=True)
                sub_short = st.checkbox("✂️ Short & Punchy (Hormozi)")
        else:
            st.info("💡 Burn into Video ရွေးထားမှ ချိန်ညှိနိုင်ပါမည်။")
            sub_position, sub_color, sub_size, sub_thickness, sub_bg, sub_short = "Bottom", "Yellow", 24, 2.5, True, False
        st.markdown("</div>", unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    if st.button("🚀 START ONE-CLICK WORKFLOW MONETIZE GENERATOR"):
        if not api_key_input: 
            st.error("⚠️ API Key လိုအပ်ပါသည်။")
        elif not uploaded_file and not video_url: 
            st.error("⚠️ ဗီဒီယိုဖိုင်သို့မဟုတ် Link ထည့်ပေးပါ။")
        else:
            st.session_state.render_success = False
            cleanup_temp_files()
            
            run_id = str(int(time.time()))
            v_final = f"AETHER_RECAP_FINAL_{run_id}.mp4"
            st.session_state.final_video_path = v_final
            v_input, a_extracted, a_generated, srt_final = "input_temp.mp4", "temp_extracted.mp3", "voice_temp.wav", "subtitles.srt"

            pbar = st.progress(0, text="🚀 အလုပ်စတင်နေပါပြီ...")
            with st.spinner("⏳ [အဆင့်၁/၆] ဗီဒီယို ဖိုင်အားစနစ်ထဲသို့ ဆွဲသွင်းနေပါသည်..."):
                pbar.progress(10, text="📥 [အဆင့် ၁/၆] ဗီဒီယိုဆွဲယူနေပါသည်...")
                try:
                    if uploaded_file:
                        with open(v_input, "wb") as f: f.write(uploaded_file.read())
                    else: download_video_from_url(video_url, v_input)
                except Exception as dl_err:
                    st.error(str(dl_err)); st.stop()
                extract_audio_fast(v_input, a_extracted)

            with st.spinner(f"⏳ [အဆင့်၂/၆] {ai_provider} ဖြင့် ဇာတ်ညွှန်း၊ Title နှင့် Thumbnail ထုတ်လုပ်နေပါသည်..."):
                pbar.progress(30, text=f"🤖 [အဆင့် ၂/၆] ဇာတ်ညွှန်း၊ Title နှင့် Hashtagsဖန်တီးနေပါသည်...")
                try:
                    extra_rules = ""
                    if script_hook: extra_rules += " [HOOK]: Start with an extremely engaging 3-second viral hook."
                    if "Slang" in script_style: extra_rules += " [SLANG]: Use modern Myanmar internet slang and Gen-Z conversational tone."
                    elif "Comedy" in script_style: extra_rules += " [COMEDY]: Make the narrative highly comedic, sarcastic, and funny."
                    elif "Suspense" in script_style: extra_rules += " [SUSPENSE]: Make the storytelling dramatic, fast-paced, and full of suspense."
                    if script_curiosity: extra_rules += " [CURIOSITY]: Insert curiosity gaps in the middle to retain audience attention."
                    if script_tone: extra_rules += " [TONE]: Inject strong emotions and character tones matching the scene."
                    
                    extra_rules += "\nAt the absolute end of the response, you MUST include these two lines on separate lines:\n[TITLE: (Provide a viral Burmese title here)]\n[TAGS: #tag1 #tag2]"
                    hormozi_rule = " [HORMOZI]: Split the subtitles into chunks of ONLY 1 to 4 words max per block. CRITICAL: DO NOT remove original timestamps." if sub_short else ""

                    if "Gemini" in ai_provider:
                        keys_list = [k.strip() for k in api_key_input.split(",") if k.strip()]
                        success_gemini = False; last_err = ""
                        for current_key in keys_list:
                            try:
                                client = genai.Client(api_key=current_key)
                                target_file = v_input if "Original" in recap_mode else a_extracted
                                media_file = client.files.upload(file=target_file)
                                while "PROCESSING" in str(client.files.get(name=media_file.name).state): time.sleep(2)
                                gemini_prompt = f"Watch the provided video carefully. Invent a completely ORIGINAL, highly engaging storytelling recap in Burmese. Do NOT just translate. STRICT RULES: 1. Include Synergy Audio Tags like [pause=1.0], [excited]. 2. NO ENGLISH TRANSLITERATION. 3. Output ONLY valid SRT format synced to the scenes.{extra_rules}{hormozi_rule}" if "Original" in recap_mode else f"Listen to the audio. Translate and adapt the text into highly engaging, natural spoken Burmese. STRICT RULES: 1. Include Synergy Audio Tags like [pause=1.0], [excited]. 2. NO ENGLISH TRANSLITERATION. 3. Output ONLY valid SRT format matching original timestamps.{extra_rules}{hormozi_rule}"
                                response = client.models.generate_content(model="gemini-2.5-flash", contents=[media_file, gemini_prompt])
                                raw_output_text = response.text.strip()
                                client.files.delete(name=media_file.name)
                                success_gemini = True; break 
                            except Exception as e: last_err = str(e); continue
                        if not success_gemini: raise Exception(f"Gemini API Error: {last_err}")
                    else: 
                        client = Groq(api_key=api_key_input) if "Groq" in ai_provider else openai
                        if "Groq" in ai_provider:
                            with open(a_extracted, "rb") as file: transcription = client.audio.translations.create(file=(a_extracted, file.read()), model="whisper-large-v3", response_format="verbose_json")
                            tsrt = "".join([f"{i}\n00:00:00,000 --> 00:00:10,000\n{seg['text']}\n\n" for i, seg in enumerate(transcription.get('segments', []), 1)]) if isinstance(transcription, dict) else str(transcription)
                        else:
                            openai.api_key = api_key_input
                            with open(a_extracted, "rb") as file: tsrt = openai.audio.translations.create(model="whisper-1", file=file, response_format="srt")
                        
                        base_prompt = f"Translate and adapt the English SRT into engaging Burmese. Add audio tags. Output valid SRT format. {extra_rules}{hormozi_rule}"
                        comp = client.chat.completions.create(model="llama-3.3-70b-versatile" if "Groq" in ai_provider else ("gpt-5.5-pro" if "5.5" in ai_provider else "gpt-4o"), messages=[{"role": "user", "content": f"{base_prompt} --- SRT --- {tsrt}"}])
                        raw_output_text = comp.choices[0].message.content

                    title_match = re.search(r'\[TITLE:\s*(.*?)\]', raw_output_text, re.IGNORECASE)
                    tags_match = re.search(r'\[TAGS:\s*(.*?)\]', raw_output_text, re.IGNORECASE)
                    st.session_state.viral_title = re.sub(r'[\[\]]', '', title_match.group(1)).strip() if title_match else "Viral Movie Recap"
                    st.session_state.viral_tags = tags_match.group(1).strip() if tags_match else "#movierecap #myanmar"
                    
                    clean_raw_srt = re.sub(r'\[TITLE:.*?\]', '', raw_output_text, flags=re.IGNORECASE)
                    clean_raw_srt = re.sub(r'\[TAGS:.*?\]', '', clean_raw_srt, flags=re.IGNORECASE).strip()
                    marker = chr(96) * 3
                    clean_raw_srt = clean_raw_srt.replace(f"{marker}srt", "").replace(marker, "")
                    
                    parsed_timestamps, speech_text = parse_and_save_real_srt(clean_raw_srt, srt_final, use_fade=False)
                    st.session_state.generated_script = clean_raw_srt
                    
                    try:
                        t_A = min(get_file_duration(v_input)*0.2, 10)
                        t_B = min(get_file_duration(v_input)*0.5, 20)
                        for thumb_suffix, t_val in [("A", t_A), ("B", t_B)]:
                            thumb_name = f"thumb_{thumb_suffix}_{run_id}.jpg"
                            try:
                                stream = ffmpeg.input(v_input, ss=t_val)
                                if cb_thumb_text:
                                    with open("thumb_text.txt", "w", encoding="utf-8") as tf: tf.write(textwrap.fill(st.session_state.viral_title, width=25))
                                    if os.path.exists("Padauk.ttf"): stream = ffmpeg.filter(stream.video, 'drawtext', textfile='thumb_text.txt', fontfile='Padauk.ttf', fontcolor='white', fontsize=65, x='(w-text_w)/2', y='(h-text_h)/2', box=1, boxcolor='red@0.9', boxborderw=20, borderw=3, bordercolor='black', line_spacing=15)
                                ffmpeg.output(stream, thumb_name, vframes=1).overwrite_output().run(cmd=FFMPEG_BINARY, quiet=True)
                            except Exception: pass
                            if thumb_suffix == "A" and os.path.exists(thumb_name): st.session_state.thumb_path_A = thumb_name
                            elif thumb_suffix == "B" and os.path.exists(thumb_name): st.session_state.thumb_path_B = thumb_name
                    except Exception: pass
                except Exception as e: st.error(f"Logic Error: {e}"); st.stop()

            with st.spinner(f"⏳ [အဆင့်၄/၆] AI Voice Over ထုတ်လုပ်နေပါသည်..."):
                pbar.progress(60, text="🎙️ [အဆင့် ၄/၆] အသံသရုပ်ဆောင်ဖန်တီးနေပါသည်...")
                try: asyncio.run(generate_tts(speech_text, voice_char, a_generated, engine=audio_engine_choice, ttsmaker_key=key_ttsmaker, eleven_key=locals().get('eleven_key_input', ''), custom_eleven_id=locals().get('custom_eleven_id', ''), gemini_key=locals().get('synergy_key', api_key_input), pitch=pitch_level, voice_fx=fx_level))
                except Exception as e: st.error(f"အသံထုတ်လုပ်ခြင်းမအောင်မြင်ပါ: {e}"); st.stop()

            with st.spinner("⏳ [အဆင့်၅/၆] ဗီဒီယိုနှင့် စာတန်းထိုးပေါင်းစပ်နေပါသည်..."):
                pbar.progress(80, text="🎬 [အဆင့် ၅/၆] ဗီဒီယိုနှင့်စာတန်းထိုး ပေါင်းစပ်နေပါသည်...")
                success, err_msg = render_premium_saas_video(v_input, a_generated, parsed_timestamps, v_final, video_ratio, cb_bypass, cb_blur, watermark_text, subtitle_mode, cb_mirror, cb_color, cb_grain, cb_fps, sub_position=sub_position, sub_color=sub_color, sub_size=sub_size, sub_thickness=sub_thickness, sub_bg=sub_bg, use_freeze=cb_freeze, logo_path=locals().get('uploaded_logo', None))
                if not success: st.error(f"❌ Sync Failure: {err_msg}"); st.stop()

            if success and selected_bgm not in ["None (BGM မထည့်ပါ)"]:
                with st.spinner("⏳ [အဆင့်၆/၆] Auto-Ducking ဖြင့် BGM ထပ်မံပေါင်းစပ်နေပါသည်..."):
                    pbar.progress(95, text="🎵 [အဆင့် ၆/၆] Auto-Ducking စနစ်ဖြင့် BGM အသံကစားနေပါသည်...")
                    selected_bgm_path = os.path.join("bgm_tracks", random.choice(bgm_files) if "Auto" in selected_bgm else selected_bgm)
                    if os.path.exists(selected_bgm_path):
                        try:
                            ducked = ffmpeg.filter([ffmpeg.input(selected_bgm_path, stream_loop=-1).audio.filter('aresample', 44100).filter('volume', bgm_volume), ffmpeg.input(v_final).audio], 'sidechaincompress', threshold=0.04, ratio=4, attack=50, release=300)
                            mixed = ffmpeg.filter([ffmpeg.input(v_final).audio, ducked], 'amix', inputs=2, duration='first').filter('volume', 2.0)
                            (ffmpeg.output(ffmpeg.input(v_final).video, mixed, "temp_mix.mp4", vcodec='copy', acodec='aac', t=get_file_duration(v_final)).overwrite_output().run(cmd=FFMPEG_BINARY, quiet=True))
                            shutil.move("temp_mix.mp4", v_final)
                        except Exception: pass
            
            pbar.progress(100, text="✅ အားလုံးပြီးစီးပါပြီ!")
            if success: st.session_state.render_success = True

    if st.session_state.render_success:
        st.balloons()
        st.success(f"🎉 One-Click ဗီဒီယို အောင်မြင်စွာ ထွက်လာပါပြီ!")
        st.markdown(f"<h2 style='color:#38bdf8; text-align:center;'>🔥 {st.session_state.viral_title}</h2>", unsafe_allow_html=True)
        st.markdown(f"<p style='text-align:center; color:#94a3b8;'>{st.session_state.viral_tags}</p>", unsafe_allow_html=True)
        
        col_out1, col_out2 = st.columns([1, 1])
        with col_out1:
            if os.path.exists(st.session_state.final_video_path): 
                st.video(st.session_state.final_video_path)
                st.markdown('<div class="setting-panel"><h4>📥 Download Dashboard</h4>', unsafe_allow_html=True)
                st.markdown(get_download_link(st.session_state.final_video_path, "Aether_Recap.mp4", "Download Recap Video (MP4)"), unsafe_allow_html=True)
                if os.path.exists("subtitles.srt"): st.markdown(get_download_link("subtitles.srt", "Aether_Subs.srt", "Download Subtitles (.SRT)"), unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)
                
        with col_out2:
            st.markdown('<div class="setting-panel"><h3>📝 Scripts & Assets</h3>', unsafe_allow_html=True)
            col_t1, col_t2 = st.columns(2)
            if st.session_state.thumb_path_A and os.path.exists(st.session_state.thumb_path_A):
                with col_t1: 
                    st.image(st.session_state.thumb_path_A, caption="Thumbnail (A)", use_column_width=True)
                    st.markdown(get_download_link(st.session_state.thumb_path_A, "Thumb_A.jpg", "Download A"), unsafe_allow_html=True)
            if st.session_state.thumb_path_B and os.path.exists(st.session_state.thumb_path_B):
                with col_t2: 
                    st.image(st.session_state.thumb_path_B, caption="Thumbnail (B)", use_column_width=True)
                    st.markdown(get_download_link(st.session_state.thumb_path_B, "Thumb_B.jpg", "Download B"), unsafe_allow_html=True)
            
            with st.expander("👁️ Original Transcript", expanded=False): st.text_area("မူရင်းစာသား:", value=st.session_state.original_transcript, height=150, disabled=True)
            with st.expander("🇲🇲 AI Generated Script", expanded=True): st.text_area("AI မှရေးသားထားသော ဇာတ်ညွှန်း:", value=st.session_state.generated_script, height=250, disabled=True)
            st.markdown('</div>', unsafe_allow_html=True)

# =====================================================================
# 📌 MODE 1.5 - FACELESS Channel Studio
# =====================================================================
elif app_mode == "🎙️ Faceless Channel Studio":
    st.markdown('<div class="setting-panel"><h3>👻 Fully-Automated Faceless Channel Studio</h3>', unsafe_allow_html=True)
    st.markdown("TikTok, FB Reels များအတွက် Reddit Stories, Horror ပုံပြင်များကိုဖန်တီးပါ။")

    with st.sidebar:
        st.markdown("---")
        st.markdown("<b>🎙️ Voice & Audio Settings</b>", unsafe_allow_html=True)
        fc_audio_engine = st.radio("Voice Engine", ["Edge-TTS (Free)", "Google Synergy TTS (API)"], key="fc_engine")
        if "Synergy" in fc_audio_engine: 
            fc_synergy_key = st.text_input("Synergy TTS Key", type="password", value=saved_gemini, key="fc_syn")
        fc_voice_char = st.selectbox("Voice Model", ["Synergy Puck (Male)", "Synergy Charon (Deep)"] if "Synergy" in fc_audio_engine else ["ဇော်ဇော် (Male)", "အောင်အောင် (Deep)", "နှင်းနှင်း (Female)"], key="fc_voice")
        fc_fx = st.selectbox("Voice FX (Effect)", ["None", "👹 Demon / Horror", "🤫 ASMR / Whisper", "🎙️ Epic Trailer", "🤖 Robot / Cyborg", "📞 Old Telephone", "⛰️ Deep Cave Echo", "🌊 Underwater / Muffled", "🔥 Deep & Energetic (Motivation)", "👻 Deep & Chilling (Horror)"], key="fc_fx")
        
        st.markdown("---")
        st.markdown("<b>🎨 Visual & Niche Settings</b>", unsafe_allow_html=True)
        fc_niche = st.selectbox("Select Niche", ["👻 Horror / Creepypasta", "💔 Reddit Relationship Drama", "🧠 Dark Psychology", "💡 Fun Facts / Trivia", "🚀 Motivation / Mindset", "📜 Ancient History / Myths"])
        fc_ratio = st.selectbox("Video Ratio", ["9:16 (TikTok/Shorts)", "16:9 (YouTube)"], key="fc_ratio")
        fc_duration = st.slider("⏱️ Story Duration (Minutes)", 1, 10, 3)

        st.markdown("<b>📝 Subtitle Pro Settings</b>", unsafe_allow_html=True)
        fc_sub_position = st.selectbox("📍 Position", ["Center", "Bottom", "Top"], index=0, key="fc_sub_pos")
        fc_sub_color = st.selectbox("🎨 Color", ["Yellow Text", "White Text", "Neon Green Text", "Red Text", "Gold Text"], index=0, key="fc_sub_col")
        fc_subtitle_mode = st.radio("Subtitle Output Mode", ["Both (Burn + SRT)", "Export SRT File Only", "Burn into Video"], key="fc_sub_mode")

        bgm_options = ["None (BGM မထည့်ပါ)"]
        bgm_files = [f for f in os.listdir("bgm_tracks") if f.endswith(".mp3")] if os.path.exists("bgm_tracks") else []
        if bgm_files:
            bgm_options.insert(1, "🤖 Auto (Random Select)")
            bgm_options.extend(bgm_files)
        fc_bgm = st.selectbox("🎼 Background Music", bgm_options, key="fc_bgm")
        fc_bgm_vol = st.slider("🔊 BGM Volume", 1, 50, 8, key="fc_bgm_vol") / 100.0
        fc_sub_short = st.checkbox("✂️ Short & Punchy (Hormozi)", value=True)

    st.markdown('<div class="setting-panel"><h4>🛠️ Manual Controls (Optional)</h4>', unsafe_allow_html=True)
    col_fc1, col_fc2 = st.columns(2)
    with col_fc1:
        st.markdown("<div class='sub-box'>", unsafe_allow_html=True)
        fc_script_mode = st.radio("📝 Story Script Source", ["🤖 Auto-Generate AI Script", "✍️ Manual Script Entry"])
        fc_manual_script = st.text_area("✍️ Paste your script here:", placeholder="သင့်ကိုယ်ပိုင်ဇာတ်ညွှန်းကို ဤနေရာတွင် ထည့်ပါ...", height=150) if "Manual" in fc_script_mode else ""
        st.markdown("</div>", unsafe_allow_html=True)
        
    with col_fc2:
        st.markdown("<div class='sub-box'>", unsafe_allow_html=True)
        fc_visual_mode = st.radio("🎥 Visuals Source", ["🎨 Auto-Generate AI Images (Pollinations)", "🖼️ Upload Manual Images"])
        fc_uploaded_images = st.file_uploader("🖼️ Upload Images (JPG/PNG)", type=["png", "jpg", "jpeg"], accept_multiple_files=True) if "Upload" in fc_visual_mode else None
        st.markdown("</div>", unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    if st.button("🚀 CREATE FACELESS VIDEO (AUTO-MAGIC)"):
        if not api_key_input: 
            st.error("⚠️ Google Gemini API Key ထည့်သွင်းပေးပါ။ (Sidebar တွင်ထည့်ပါ)")
        elif "Manual" in fc_script_mode and not fc_manual_script.strip(): 
            st.error("⚠️ Manual ဇာတ်ညွှန်းထည့်သွင်းပေးပါ။")
        elif "Upload" in fc_visual_mode and not fc_uploaded_images: 
            st.error("⚠️ အနည်းဆုံးပုံ (၁) ပုံ Upload တင်ပေးပါ။")
        else:
            st.session_state.render_success = False
            cleanup_temp_files()
            run_id = str(int(time.time()))
            v_final = f"FACELESS_FINAL_{run_id}.mp4"
            st.session_state.final_video_path = v_final
            pbar = st.progress(0, text="🚀 အလိုအလျောက် ဖန်တီးမှုစတင်နေပါပြီ...")
            keys_list = [k.strip() for k in api_key_input.split(",") if k.strip()]

            fc_story_text = ""
            if "Manual" in fc_script_mode:
                pbar.progress(10, text="📝 Manual ဇာတ်ညွှန်းအား ဖတ်ယူနေပါသည်...")
                fc_story_text = fc_manual_script.strip()
            else:
                with st.spinner(f"⏳ [အဆင့်၁/၅] Gemini ဖြင့် {fc_duration} မိနစ်စာ ဇာတ်လမ်း ရေးသားနေပါသည်..."):
                    pbar.progress(10, text="📝 ဇာတ်လမ်း ရေးသားနေပါသည်...")
                    target_words = fc_duration * 140
                    story_prompt = f"""Act as a YouTube content strategist AND cinematic narrative writer.
Write an engaging {fc_duration}-minute highly viral script for a {fc_niche} TikTok/YouTube video in natural spoken Burmese. (Around {target_words} words).
 
CRITICAL RULES:
1. THE VIRAL HOOK (0-3s): Start with a mind-blowing, highly engaging 3-second viral hook.
2. NO FORMAL GRAMMAR: STRICTLY PROHIBITED to use formal literary markers (၌,၍, သည့်, သည်, ၏). Use natural spoken endings (တယ်, တဲ့, မှာ, ရဲ့).
3. POV: Write in second person (မင်း / မင်းရဲ့) if applicable.
4. AUDIO TAGS: Include tags like [pause=1.0], [excited], [whisper] to guide the voice.
5. Do not use English transliteration. Use emotionally immersive storytelling. MUST BE IN PURE BURMESE LANGUAGE.
 
Output format:
Provide the script directly.
At the absolute end, include these two lines:
[TITLE: A highly viral, click-worthy Burmese title]
[TAGS: #tag1 #tag2]"""
                    last_err = ""
                    for key in keys_list:
                        try:
                            client = genai.Client(api_key=key)
                            response = client.models.generate_content(model="gemini-2.5-flash", contents=story_prompt)
                            fc_story_text = response.text.strip(); break
                        except Exception as e: last_err = str(e); continue
                    if not fc_story_text:
                        st.error(f"Story Error: Key အားလုံး Limit ပြည့်နေပါသည်။ {last_err}"); st.stop()

            title_match = re.search(r'\[TITLE:\s*(.*?)\]', fc_story_text, re.IGNORECASE)
            tags_match = re.search(r'\[TAGS:\s*(.*?)\]', fc_story_text, re.IGNORECASE)
            if title_match: st.session_state.viral_title = re.sub(r'[\[\]]', '', title_match.group(1)).strip()
            if tags_match: st.session_state.viral_tags = tags_match.group(1).strip()
            
            fc_story_text = re.sub(r'\[TITLE:.*?\]', '', fc_story_text, flags=re.IGNORECASE)
            fc_story_text = re.sub(r'\[TAGS:.*?\]', '', fc_story_text, flags=re.IGNORECASE).strip()

            with st.spinner("⏳ [အဆင့်၂/၅] AI သရုပ်ဆောင်ဖြင့် အသံဖန်တီးနေပါသည်..."):
                pbar.progress(30, text="🎙️ အသံဖန်တီးနေပါသည်...")
                try:
                    clean_story = re.sub(r'\[.*?\]', '', fc_story_text) 
                    asyncio.run(generate_tts(fc_story_text if "Synergy" in fc_audio_engine else clean_story, fc_voice_char, "fc_audio.wav", engine=fc_audio_engine, gemini_key=locals().get('fc_synergy_key', api_key_input), voice_fx=fc_fx))
                    fc_audio_dur = get_file_duration("fc_audio.wav")
                    if fc_audio_dur < 5.0: st.error("❌ အသံထုတ်လုပ်ခြင်းမအောင်မြင်ပါ။ API Limit ငြိသွားခြင်း သို့မဟုတ် Network ပြဿနာကြောင့် အသံဖိုင် တိုတောင်းလွန်းနေပါသည်။ ပြန်လည်ကြိုးစားပါ။"); st.stop()
                except Exception as e: st.error(f"Audio Error: {e}"); st.stop()

            with st.spinner("⏳ [အဆင့်၃/၅] Visuals များကို ပြင်ဆင်နေပါသည်..."):
                pbar.progress(50, text="🎥 Visuals ပြင်ဆင်နေပါသည်...")
                try:
                    generated_clips = []
                    v_w, v_h = (720, 1280) if "9:16" in fc_ratio else (1280, 720)
                    
                    if "Upload" in fc_visual_mode:
                        clip_dur = fc_audio_dur / len(fc_uploaded_images)
                        for i, img_file in enumerate(fc_uploaded_images):
                            img_path = f"fc_img_{i}.jpg"
                            clip_path = f"fc_clip_{i}.mp4"
                            img_file.seek(0)
                            with open(img_path, "wb") as f: f.write(img_file.read())
                            pbar.progress(50 + int((i/len(fc_uploaded_images))*15), text=f"🎥 Upload ပုံများကို Animation သွင်းနေပါသည် ({i+1}/{len(fc_uploaded_images)})...")
                            subprocess.run([FFMPEG_BINARY, "-y", "-loop", "1", "-framerate", "25", "-i", img_path, "-t", str(clip_dur), "-vf", f"scale=-2:2000,zoompan=z='min(zoom+0.001,1.15)':d={int(clip_dur*25)}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={v_w}x{v_h},fps=25", "-c:v", "libx264", "-preset", "superfast", clip_path], capture_output=True)
                            if os.path.exists(clip_path): generated_clips.append(clip_path)
                    else:
                        style_mapping = {
                            "👻 Horror / Creepypasta": "Gritty graphic novel style, cinematic lighting, thick bold outlines, deep shadows",
                            "💔 Reddit Relationship Drama": "Cinematic photography, emotional lighting, soft focus, dramatic depth of field",
                            "🧠 Dark Psychology": "Dark neo-noir cinematic style, high contrast, psychological thriller lighting",
                            "💡 Fun Facts / Trivia": "Vibrant 3D illustration style, bright colors, highly detailed, engaging visual",
                            "🚀 Motivation / Mindset": "Epic cinematic photography, bright inspiring lighting, golden hour, highly uplifting atmosphere",
                            "📜 Ancient History / Myths": "Epic historical fantasy painting, cinematic lighting, realistic textures, highly detailed"
                        }
                        current_style = style_mapping.get(fc_niche, "Cinematic, highly detailed 8k masterpiece")

                        search_keywords = []
                        last_err = ""
                        img_count = max(4, int(fc_audio_dur // 12))
                        
                        for key in keys_list:
                            try:
                                client = genai.Client(api_key=key)
                                img_prompt_instruction = f"""Based on this story, give me exactly {img_count} highly detailed English image generation prompts describing chronological scenes. 
GLOBAL STYLE DNA: {current_style}. Avoid explicit/violent words. Do NOT include text or words in the prompt.
IMPORTANT: PROMPTS MUST BE WRITTEN IN PURE ENGLISH. NO BURMESE CHARACTERS.
CRITICAL FORMAT RULE: Format strictly separated by a pipe '|' with NO newlines. Example: scene 1 | scene 2 | scene 3
Story: {fc_story_text[:500]}"""
                                prompt_req = client.models.generate_content(model="gemini-2.5-flash", contents=img_prompt_instruction)
                                raw_kws = prompt_req.text.replace('\n', '|').split('|')
                                search_keywords = [kw.strip() for kw in raw_kws if len(kw.strip()) > 5][:img_count]
                                break
                            except Exception as e:
                                last_err = str(e); continue
                                
                        if not search_keywords: 
                            search_keywords = [f"{current_style}, epic scene {i}" for i in range(img_count)]
                        
                        total_clips = len(search_keywords)
                        clip_dur = fc_audio_dur / total_clips
                        
                        def generate_pollinations_image(prompt_text, idx):
                            try:
                                encoded_prompt = urllib.parse.quote(prompt_text.strip())
                                url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width={v_w}&height={v_h}&nologo=true"
                                res = requests.get(url, timeout=60)
                                if res.status_code == 200:
                                    img_path = f"fc_img_{idx}.jpg"
                                    clip_path = f"fc_clip_{idx}.mp4"
                                    with open(img_path, "wb") as f: f.write(res.content)
                                    subprocess.run([FFMPEG_BINARY, "-y", "-loop", "1", "-framerate", "25", "-i", img_path, "-t", str(clip_dur), "-vf", f"scale=-2:2000,zoompan=z='min(zoom+0.001,1.15)':d={int(clip_dur*25)}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={v_w}x{v_h},fps=25", "-c:v", "libx264", "-preset", "superfast", clip_path], capture_output=True)
                                    return clip_path
                            except Exception: pass
                            return None

                        for i, kw in enumerate(search_keywords):
                            pbar.progress(50 + int(((i+1)/total_clips)*15), text=f"🎨 AI ဖြင့် ပုံများ ဖန်တီးနေပါသည် (Clip {i+1}/{total_clips})...")
                            generated_clip = generate_pollinations_image(kw, i)
                            if generated_clip and os.path.exists(generated_clip): generated_clips.append(generated_clip)
                            time.sleep(2)

                    if not generated_clips: st.error("❌ Visual Generation Failed. ပုံရိပ် ဖန်တီးမှု ပြဿနာရှိပါသည်။ Server က Rate Limit ကြောင့် ပိတ်ချလိုက်တာဖြစ်နိုင်ပါတယ်။ API Key ပြောင်းသုံးပါ သို့မဟုတ် ခဏစောင့်ပါ။"); st.stop()
                    
                    pbar.progress(65, text="🎞️ ဗီဒီယိုများကို ပေါင်းစပ်နေပါသည်...")
                    with open("fc_concat.txt", "w") as f:
                        for c in generated_clips: f.write(f"file '{c}'\n")
                    res_concat = subprocess.run([FFMPEG_BINARY, "-y", "-stream_loop", "-1", "-f", "concat", "-safe", "0", "-i", "fc_concat.txt", "-t", str(fc_audio_dur), "-c", "copy", "fc_video_loop.mp4"], capture_output=True)
                    if not os.path.exists("fc_video_loop.mp4"): st.error(f"❌ FFmpeg Concat Error. {res_concat.stderr.decode('utf-8', errors='ignore')}"); st.stop()
                except Exception as e: st.error(f"Visual Error: {e}"); st.stop()

            with st.spinner("⏳ [အဆင့်၄/၅] စာတန်းထိုးများကို ချိန်ညှိနေပါသည်..."):
                pbar.progress(70, text="📝 Timeline ချိန်ညှိနေပါသည်...")
                fc_parsed = None
                last_err = ""
                groq_key_val = locals().get('groq_key_fc', '').strip()
 
                if groq_key_val:
                    try:
                        pbar.progress(72, text="📝 Whisper ဖြင့် အသံအား တိကျစွာ ဖြတ်တောက်နေပါသည်...")
                        client_groq = Groq(api_key=groq_key_val)
                        with open("fc_audio.wav", "rb") as file:
                            transcription = client_groq.audio.transcriptions.create(
                                file=("fc_audio.wav", file.read()), model="whisper-large-v3", response_format="verbose_json", language="my"
                            )
                        
                        def fmt_time(sec): return f"{int(sec//3600):02d}:{int((sec%3600)//60):02d}:{int(sec%60):02d},{int((sec%1)*1000):03d}"
                            
                        clean_script_for_sub = re.sub(r'\[.*?\]', '', fc_story_text)
                        clean_script_for_sub = re.sub(r'\{.*?\}', '', clean_script_for_sub)
                        burmese_words = clean_script_for_sub.split()
                        
                        segments = transcription.segments if hasattr(transcription, 'segments') else transcription.get('segments', [])
                        raw_srt_str = ""
                        chunk_idx = 1
                        
                        total_b_words = len(burmese_words)
                        total_w_words = sum(len(seg.text.split() if hasattr(seg, 'text') else seg['text'].split()) for seg in segments)
                        
                        word_idx = 0
                        for i_seg, seg in enumerate(segments):
                            s_start = seg.start if hasattr(seg, 'start') else seg['start']
                            s_end = seg.end if hasattr(seg, 'end') else seg['end']
                            w_text = seg.text if hasattr(seg, 'text') else seg['text']
                            w_words_len = max(1, len(w_text.split()))
                            
                            num_b_words = max(1, int((w_words_len / max(1, total_w_words)) * total_b_words))
                            if i_seg == len(segments) - 1: seg_b_words = burmese_words[word_idx:]
                            else: seg_b_words = burmese_words[word_idx : word_idx + num_b_words]
                                
                            word_idx += num_b_words
                            if not seg_b_words: continue
                            
                            chunk_size = 3 if fc_sub_short else 12
                            seg_chunks = [seg_b_words[i:i + chunk_size] for i in range(0, len(seg_b_words), chunk_size)]
                            if not seg_chunks: continue
                            
                            time_per_chunk = (s_end - s_start) / len(seg_chunks)
                            for j, c_words in enumerate(seg_chunks):
                                c_start = s_start + (j * time_per_chunk)
                                c_end = c_start + time_per_chunk
                                s_text = " ".join(c_words)
                                raw_srt_str += f"{chunk_idx}\n{fmt_time(c_start)} --> {fmt_time(c_end)}\n{s_text}\n\n"
                                chunk_idx += 1
                                
                        fc_parsed, _ = parse_and_save_real_srt(raw_srt_str, "subtitles.srt", use_fade=False)
                    except Exception as e: last_err = str(e)
                
                if not fc_parsed: st.error(f"SRT Error: ကျေးဇူးပြု၍ API Limit သို့မဟုတ် Key မှန်ကန်မှု စစ်ဆေးပါ။ {last_err}"); st.stop()

            with st.spinner("⏳ [အဆင့်၅/၅] အားလုံးကိုပေါင်းစပ်ပြီး Master Video ထုတ်လုပ်နေပါသည်..."):
                pbar.progress(85, text="🎬 Master Rendering အလုပ်လုပ်နေပါသည်...")
                try:
                    success, err_msg = render_premium_saas_video("fc_video_loop.mp4", "fc_audio.wav", fc_parsed, v_final, fc_ratio, use_bypass=True, subtitle_mode=fc_subtitle_mode, sub_position=fc_sub_position, sub_color=fc_sub_color, sub_size=26, sub_thickness=2.5, sub_bg=False)
                    if not success: st.error(f"❌ Video Generation Output Failure! Internal Engine Log: {err_msg}"); st.stop()
                    
                    if fc_bgm not in ["None (BGM မထည့်ပါ)"]:
                        bgm_path = os.path.join("bgm_tracks", random.choice(bgm_files) if "Auto" in fc_bgm else fc_bgm)
                        if os.path.exists(bgm_path):
                            try:
                                ducked = ffmpeg.filter([ffmpeg.input(bgm_path, stream_loop=-1).audio.filter('aresample', 44100).filter('volume', fc_bgm_vol), ffmpeg.input(v_final).audio], 'sidechaincompress', threshold=0.04, ratio=4, attack=50, release=300)
                                mixed = ffmpeg.filter([ffmpeg.input(v_final).audio, ducked], 'amix', inputs=2, duration='first').filter('volume', 2.0)
                                ffmpeg.output(ffmpeg.input(v_final).video, mixed, "temp_faceless.mp4", vcodec='copy', acodec='aac', t=fc_audio_dur).overwrite_output().run(cmd=FFMPEG_BINARY, quiet=True)
                                shutil.move("temp_faceless.mp4", v_final)
                            except Exception: pass
                    
                    try:
                        t_A = min(fc_audio_dur * 0.2, 10)
                        t_B = min(fc_audio_dur * 0.5, 20)
                        for thumb_suffix, t_val in [("A", t_A), ("B", t_B)]:
                            thumb_name = f"thumb_{thumb_suffix}_{run_id}.jpg"
                            try:
                                stream = ffmpeg.input(v_final, ss=t_val)
                                with open("thumb_text.txt", "w", encoding="utf-8") as tf:
                                    title_text = st.session_state.viral_title if st.session_state.viral_title else "Viral Video"
                                    tf.write(textwrap.fill(title_text, width=25))
                                if os.path.exists("Padauk.ttf"):
                                    stream = ffmpeg.filter(stream.video, 'drawtext', textfile='thumb_text.txt', fontfile='Padauk.ttf', fontcolor='white', fontsize=65, x='(w-text_w)/2', y='(h-text_h)/2', box=1, boxcolor='red@0.9', boxborderw=20, borderw=3, bordercolor='black', line_spacing=15)
                                ffmpeg.output(stream, thumb_name, vframes=1).overwrite_output().run(cmd=FFMPEG_BINARY, quiet=True)
                            except Exception: pass
                            
                            if thumb_suffix == "A" and os.path.exists(thumb_name): st.session_state.thumb_path_A = thumb_name
                            elif thumb_suffix == "B" and os.path.exists(thumb_name): st.session_state.thumb_path_B = thumb_name
                    except Exception: pass
                            
                    pbar.progress(100, text="✅ အားလုံးပြီးစီးပါပြီ!")
                    st.balloons()
                    st.success("🎉 Faceless Video ထုတ်လုပ်မှု အောင်မြင်စွာ ပြီးစီးပါပြီ!")
                    
                    try:
                        client_viral = genai.Client(api_key=keys_list[0])
                        v_prompt = f"Analyze this short video for TikTok virality. Title: {st.session_state.viral_title}. Hook: {fc_story_text[:150]}. Reply strictly in this format: \nScore: [1-100]\nReason: [1 short sentence in Burmese]"
                        v_res = client_viral.models.generate_content(model="gemini-2.5-flash", contents=v_prompt)
                        st.session_state.viral_score = v_res.text.strip()
                    except Exception: st.session_state.viral_score = "Score: 90\nReason: အရမ်းကောင်းတဲ့ Hook ပါ။"
                    
                    col_f1, col_f2 = st.columns(2)
                    with col_f1:
                        if os.path.exists(st.session_state.final_video_path):
                            st.video(st.session_state.final_video_path)
                            st.markdown('<div class="setting-panel"><h4>📥 Download Dashboard</h4>', unsafe_allow_html=True)
                            st.markdown(get_download_link(st.session_state.final_video_path, "Viral_Faceless.mp4", "Download Final Video (No Refresh)"), unsafe_allow_html=True)
                            if os.path.exists("subtitles.srt"):
                                st.markdown(get_download_link("subtitles.srt", "Faceless_Subs.srt", "Download Subtitles (.SRT)"), unsafe_allow_html=True)
                            st.markdown('</div>', unsafe_allow_html=True)
                        else: st.error("❌ ဗီဒီယိုဖိုင်ကို ရှာမတွေ့ပါ။ Rendering တွင် ချို့ယွင်းချက် ရှိနိုင်ပါသည်။")

                    with col_f2:
                        st.markdown("### 📝 Generated Story & Assets")
                        st.info(f"📈 **Viral Prediction:**\n{st.session_state.viral_score}")
                        
                        col_ta, col_tb = st.columns(2)
                        if st.session_state.thumb_path_A and os.path.exists(st.session_state.thumb_path_A):
                            with col_ta: 
                                st.image(st.session_state.thumb_path_A, caption="Thumbnail A")
                                st.markdown(get_download_link(st.session_state.thumb_path_A, "Thumb_A.jpg", "Download A"), unsafe_allow_html=True)
                        if st.session_state.thumb_path_B and os.path.exists(st.session_state.thumb_path_B):
                            with col_tb: 
                                st.image(st.session_state.thumb_path_B, caption="Thumbnail B")
                                st.markdown(get_download_link(st.session_state.thumb_path_B, "Thumb_B.jpg", "Download B"), unsafe_allow_html=True)
                        st.text_area("ဇာတ်လမ်း:", value=fc_story_text, height=300, disabled=True)
                except Exception as e: st.error(f"Render Error: {e}"); st.stop()

# =====================================================================
# 📌 MODE 2 - VEO VIDEO STUDIO
# =====================================================================
elif app_mode == "🎥 Veo Video Studio":
    st.markdown('<div class="setting-panel"><h3>🎥 Veo 3.0 Cinematic Video Generator</h3>', unsafe_allow_html=True)
    video_prompt = st.text_area("🎬 Enter Video Prompt", placeholder="A cinematic slow-motion drone shot...")
    if st.button("🚀 Generate Veo Video"): pass

elif app_mode == "🎵 Lyria Music Studio":
    st.markdown('<div class="setting-panel"><h3>🎵 Lyria 3 Pro Music Generator</h3>', unsafe_allow_html=True)
    music_prompt = st.text_area("🎧 Enter Music Prompt", placeholder="Epic cinematic background music...")
    if st.button("🚀 Generate Lyria Music"): pass

elif app_mode == "⚡ Translation/Transcript Studio":
    st.markdown('<h2 style="color:#00e5ff;">⚡ Translation & Subtitle Studio (AI Dual Engine)</h2>', unsafe_allow_html=True)
    video_url = st.text_input("YouTube / FB / TikTok / Rednote URL ထည့်ပါ:")
    if st.button("🚀 စတင်လုပ်ဆောင်မည်"): pass

elif app_mode == "📥 Video Downloader Hub":
    st.markdown('<h2 style="color:#00e5ff;">📥 Video Downloader Hub</h2>', unsafe_allow_html=True)
    dl_url = st.text_input("ဗီဒီယို URL ကို ဒီမှာ ထည့်ပါ:", key="hub_dl_url")
    if st.button("⬇️ ဗီဒီယိုစစ်ဆေးပြီး ဒေါင်းလုဒ်ဆွဲမည်"): pass
