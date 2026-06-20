import streamlit as st
import os
import time
import asyncio
import subprocess
import shutil
import re
import random
import textwrap
import ffmpeg
from google import genai
from groq import Groq
import openai

from utils.helpers import get_available_fonts, get_download_link, cleanup_temp_files, load_key
from core_engines.audio_tts import generate_tts
from core_engines.subtitle_sync import parse_and_save_real_srt
from core_engines.video_render import render_premium_saas_video, generate_professional_thumbnail, get_file_duration, download_video_from_url, extract_audio_fast, FFMPEG_BINARY, VideoConfig

def tuples_to_srt(parsed_data):
    """Whisper မှထွက်လာသော ဒေတာများကို Editor တွင်ပြင်နိုင်ရန် SRT String သို့ပြောင်းပေးသည့်စနစ်"""
    srt_str = ""
    for i, (start_raw, end_raw, text) in enumerate(parsed_data, 1):
        start = float(start_raw)
        end = float(end_raw)
        
        # 🔴 SILENCE CLIP ENGINE: စကားမပြောတော့ဘဲ ငြိမ်နေချိန်တွင် စာတန်းထိုးပျောက်သွားစေရန် စာဖတ်နှုန်းဖြင့် ထိန်းချုပ်ခြင်း
        natural_dur = max(1.5, min(3.5, len(text) * 0.12))
        end = min(start + natural_dur, end)
        
        def format_srt_time(seconds):
            sec = float(seconds)
            h = int(sec // 3600); m = int((sec % 3600) // 60); s = int(sec % 60); ms = int((sec % 1) * 1000)
            return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
            
        srt_str += f"{i}\n{format_srt_time(start)} --> {format_srt_time(end)}\n{str(text).strip()}\n\n"
    return srt_str.strip()

def render_movie_dubbing_studio(api_key_input, saved_gemini, ai_provider, groq_key_fc=None):
    st.markdown('<div class="setting-panel"><h3>🎙️ Movie Dubbing & Recap Studio</h3>', unsafe_allow_html=True)
    st.markdown("နိုင်ငံခြား ဇာတ်လမ်းတိုများကို မြန်မာလို အလိုအလျောက် ဘာသာပြန်ပြီး အသံထည့်ပါ။ (2-Step Interactive Workflow)")

    available_fonts = get_available_fonts()
    
    if "md_step1_done" not in st.session_state: st.session_state.md_step1_done = False
    if "md_generated_srt" not in st.session_state: st.session_state.md_generated_srt = ""
    if "md_generated_script" not in st.session_state: st.session_state.md_generated_script = ""
    if "md_original_transcript" not in st.session_state: st.session_state.md_original_transcript = ""
    if "md_viral_title" not in st.session_state: st.session_state.md_viral_title = ""
    if "md_viral_tags" not in st.session_state: st.session_state.md_viral_tags = ""
    if "md_run_id" not in st.session_state: st.session_state.md_run_id = str(int(time.time()))
    if "md_preview_frame" not in st.session_state: st.session_state.md_preview_frame = "md_preview.jpg"
    if "md_audio_dur" not in st.session_state: st.session_state.md_audio_dur = 0.0

    with st.sidebar:
        st.markdown("---")
        audio_engine_choice = st.radio("Voice Engine (Dubbing)", ["Edge-TTS (Default Free)", "Google Synergy TTS (Flash 3.1 Preview)", "ElevenLabs (Premium AI)", "TTSMaker (Free API)"])
        synergy_key = ""
        eleven_key_input, custom_eleven_id, key_ttsmaker = "", "", ""
        if "Synergy" in audio_engine_choice: synergy_key = st.text_input("API Key for Synergy TTS", type="password", value=saved_gemini)
        if "ElevenLabs" in audio_engine_choice:
            eleven_key_input = st.text_input("ElevenLabs API Key", type="password")
            custom_eleven_id = st.text_input("Custom Voice ID")
        if "TTSMaker" in audio_engine_choice: key_ttsmaker = st.text_input("TTSMaker API Key", type="password")
            
        st.markdown("---")
        video_ratio = st.selectbox("Crop Ratio", ["Original", "9:16 (TikTok/Shorts)", "16:9 (YouTube)"])
        
        st.markdown("<b>🛡️ Anti-Copyright Options</b>", unsafe_allow_html=True)
        cb_bypass = st.checkbox("🔍 Smart Zoom", value=True)
        cb_mirror = st.checkbox("🪞 Mirror Effect", value=False)
        cb_color = st.checkbox("🎨 Color Tweaks", value=False)
        cb_grain = st.checkbox("🎞️ Subtle Film Grain", value=False)
        cb_fps = st.checkbox("🎬 Cinematic 24 FPS", value=False)
        cb_freeze = st.checkbox("❄️ Freeze Frame (Bypass)", value=False)

        st.markdown("<b>🎬 Visual & Subs</b>", unsafe_allow_html=True)
        md_blur = st.checkbox("⬛ Localized Subtitle Blur (မူရင်းစာတန်းကို ကွက်ပြီးဝါးမည်)", value=True)
        cb_thumb_text = st.checkbox("🖼️ Add Viral Title to Thumbnail", value=True)
        md_thumb_style = st.selectbox("🖼️ Thumbnail Style", ["🔥 Viral TikTok Style", "🎬 Cinematic Movie Poster", "👻 Horror / Mystery", "💎 Premium / Luxury", "⚡ Clean / Minimal"])

        st.markdown("<b>©️ Brand Watermark</b>", unsafe_allow_html=True)
        uploaded_logo = st.file_uploader("🖼️ Add Logo Image", type=["png", "jpg", "jpeg"])
        use_text_watermark = st.checkbox("✍️ Use Text Watermark instead", value=False)
        watermark_text = st.text_input("Text Watermark", "") if use_text_watermark else ""

        subtitle_mode = st.radio("Subtitle Output", ["Both (Burn + SRT)", "Export SRT File Only", "Burn into Video", "No Subtitle"])

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
        if bgm_files: bgm_options.insert(1, "🤖 Auto (Random Select)"); bgm_options.extend(bgm_files)
        selected_bgm = st.selectbox("🎼 Background Music", bgm_options)
        bgm_volume = st.slider("🔊 BGM Volume", 1, 50, 10) / 100.0
        st.markdown("</div>", unsafe_allow_html=True)

    with col_in2:
        dynamic_options = ["Synergy Puck (Male)", "Synergy Aoede (Female)", "Synergy Charon (Deep)"] if "Synergy" in audio_engine_choice else (["Adam (Deep)", "Rachel (Female)"] if "ElevenLabs" in audio_engine_choice else (["TTSMaker Male", "TTSMaker Female"] if "TTSMaker" in audio_engine_choice else ["ဇော်ဇော် (Male)", "အောင်အောင် (Deep)", "နှင်းနှင်း (Female)"]))
        voice_char = st.selectbox("Select Character Voice", dynamic_options, index=0)
        pitch_level = st.slider("🎙️ Voice Pitch", min_value=-30, max_value=30, value=0, step=5)
        fx_level = st.selectbox("🎧 Cinematic Voice FX", ["None", "🎙️ Epic Trailer Voice", "📻 Walkie-Talkie", "🏛️ Cinematic Reverb", "👹 Demon / Monster", "🤫 ASMR / Whisper", "🤖 Robot / Cyborg", "📞 Old Telephone", "⛰️ Deep Cave Echo", "🌊 Underwater / Muffled", "🔥 Motivation", "👻 Horror", "🌀 Spatial 3D Audio", "🎭 Multi-Persona"])

        st.markdown("<div class='sub-box'>", unsafe_allow_html=True)
        st.markdown("<p style='font-weight: bold; color: #818cf8; font-size: 16px;'>📝 Subtitle Pro Settings</p>", unsafe_allow_html=True)
        selected_font = st.selectbox("🔤 Font Style", available_fonts, index=0)
        sub_position = st.selectbox("📍 Position", ["Bottom", "Center", "Top"])
        sub_color = st.selectbox("🎨 Color", ["Yellow Text", "White Text", "Neon Green Text", "Red Text", "Gold Text"])
        sub_size = st.slider("🔠 Font Size", 16, 50, 28)
        sub_thickness = st.slider("✒️ Outline Thickness", 1.0, 5.0, 2.5)
        sub_short = st.checkbox("✂️ Short & Punchy (Hormozi)", value=False)
        st.markdown("</div>", unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # ==========================================
    # 🚀 STEP 1: GENERATE DUBBING & ASSETS
    # ==========================================
    if st.button("🚀 STEP 1: Generate AI Dubbing & Assets"):
        if not api_key_input: st.error("⚠️ API Key လိုအပ်ပါသည်။"); return
        if not uploaded_file and not video_url: st.error("⚠️ ဗီဒီယိုထည့်ပေးပါ။"); return

        st.session_state.render_success = False
        st.session_state.md_step1_done = False
        cleanup_temp_files()
        st.session_state.md_run_id = str(int(time.time()))
        
        pbar = st.progress(0, text="🚀 အလုပ်စတင်နေပါပြီ...")
        v_input, a_extracted, a_generated = "md_input.mp4", "md_extracted.mp3", "md_audio.wav"
        
        with st.spinner("⏳ [၁/၄] ဗီဒီယို ဖိုင်အားစနစ်ထဲသို့ ဆွဲသွင်းနေပါသည်..."):
            pbar.progress(10, text="📥 ဗီဒီယိုဆွဲယူနေပါသည်...")
            try:
                if uploaded_file:
                    with open(v_input, "wb") as f: f.write(uploaded_file.read())
                else: download_video_from_url(video_url, v_input)
                extract_audio_fast(v_input, a_extracted)
                ffmpeg.input(v_input, ss=min(get_file_duration(v_input)/2, 5)).output(st.session_state.md_preview_frame, vframes=1).overwrite_output().run(cmd=FFMPEG_BINARY, quiet=True)
            except Exception as dl_err: st.error(str(dl_err)); st.stop()

        with st.spinner(f"⏳ [၂/၄] {ai_provider} ဖြင့် ဇာတ်ညွှန်းထုတ်လုပ်နေပါသည်..."):
            pbar.progress(30, text="🤖 ဇာတ်ညွှန်းနှင့် Title ဖန်တီးနေပါသည်...")
            try:
                extra_rules = ""
                if script_hook: extra_rules += " [HOOK]: Start with an extremely engaging 3-second viral hook."
                if "Slang" in script_style: extra_rules += " [SLANG]: Use modern Myanmar internet slang and Gen-Z conversational tone."
                elif "Comedy" in script_style: extra_rules += " [COMEDY]: Make the narrative highly comedic, sarcastic, and funny."
                elif "Suspense" in script_style: extra_rules += " [SUSPENSE]: Make the storytelling dramatic, fast-paced, and full of suspense."
                if script_curiosity: extra_rules += " [CURIOSITY]: Insert curiosity gaps in the middle to retain audience attention."
                if script_tone: extra_rules += " [TONE]: Inject strong emotions and character tones matching the scene."
                if script_cta: extra_rules += " [CTA]: End the script with a strong Call to Action asking a question."
                extra_rules += "\nAt the absolute end of the response, you MUST include these two lines on separate lines:\n[TITLE: (Provide a viral Burmese title here)]\n[TAGS: #tag1 #tag2]"
                
                raw_output_text = ""
                if "Gemini" in ai_provider:
                    keys_list = [k.strip() for k in api_key_input.split(",") if k.strip()]
                    success_gemini = False; last_err = ""
                    for current_key in keys_list:
                        try:
                            client = genai.Client(api_key=current_key)
                            target_file = v_input if "Original" in recap_mode else a_extracted
                            media_file = client.files.upload(file=target_file)
                            while "PROCESSING" in str(client.files.get(name=media_file.name).state): time.sleep(2)
                            gemini_prompt = f"Watch the video carefully. Invent a completely ORIGINAL, highly engaging storytelling recap in Burmese. Do NOT just translate. STRICT RULES: 1. Include Synergy Audio Tags like [pause=1.0]. 2. NO ENGLISH TRANSLITERATION. 3. Output pure text narrative. {extra_rules}" if "Original" in recap_mode else f"Listen to the audio. Translate and adapt the text into highly engaging, natural spoken Burmese. STRICT RULES: 1. Include Synergy Audio Tags like [pause=1.0]. 2. NO ENGLISH TRANSLITERATION. 3. Output pure text narrative. {extra_rules}"
                            res = client.models.generate_content(model="gemini-2.5-flash", contents=[media_file, gemini_prompt])
                            raw_output_text = res.text.strip()
                            client.files.delete(name=media_file.name)
                            success_gemini = True; break
                        except Exception as e: last_err = str(e); continue
                    if not success_gemini: raise Exception(f"Gemini Error: {last_err}")
                else:
                    # 🔴 FIX: Properly initialize OpenAI client to avoid TypeError (unbound method)
                    client_llm = Groq(api_key=api_key_input) if "Groq" in ai_provider else openai.OpenAI(api_key=api_key_input)
                    if "Groq" in ai_provider:
                        with open(a_extracted, "rb") as file: transcription = client_llm.audio.translations.create(file=(a_extracted, file.read()), model="whisper-large-v3", response_format="verbose_json")
                        segments = transcription.segments if hasattr(transcription, 'segments') else transcription.get('segments', [])
                        tsrt = "".join([f"{i}\n00:00:00,000 --> 00:00:10,000\n{s['text']}\n\n" for i, s in enumerate(segments, 1)])
                    else:
                        with open(a_extracted, "rb") as file: ts_res = client_llm.audio.translations.create(model="whisper-1", file=file, response_format="srt")
                        tsrt = str(ts_res)
                        st.session_state.md_original_transcript = tsrt
                    
                    base_prompt = f"Translate and adapt the English text into engaging Burmese. Add audio tags. Output pure text narrative. {extra_rules}"
                    comp = client_llm.chat.completions.create(model="llama-3.3-70b-versatile" if "Groq" in ai_provider else "gpt-4o", messages=[{"role": "user", "content": f"{base_prompt} --- TEXT --- {tsrt}"}])
                    raw_output_text = comp.choices[0].message.content

                title_match = re.search(r'\[TITLE:\s*(.*?)\]', raw_output_text, re.IGNORECASE)
                tags_match = re.search(r'\[TAGS:\s*(.*?)\]', raw_output_text, re.IGNORECASE)
                st.session_state.md_viral_title = re.sub(r'[\[\]]', '', title_match.group(1)).strip() if title_match else "Viral Movie Recap"
                st.session_state.md_viral_tags = tags_match.group(1).strip() if tags_match else "#movierecap #myanmar"
                clean_raw_text = re.sub(r'\[TITLE:.*?\]', '', raw_output_text, flags=re.IGNORECASE)
                st.session_state.md_generated_script = re.sub(r'\[TAGS:.*?\]', '', clean_raw_text, flags=re.IGNORECASE).strip()
            except Exception as e: st.error(f"Logic Error: {e}"); st.stop()

        with st.spinner("⏳ [၃/၄] AI Voice Over ထုတ်လုပ်နေပါသည်... (ဇာတ်လမ်းရှည်ပါက ၂-၃ မိနစ်ခန့် ကြာနိုင်ပါသည်)"):
            pbar.progress(50, text="🎙️ အသံသရုပ်ဆောင်ဖန်တီးနေပါသည် (အချိန်အနည်းငယ် ယူပါမည်)...")
            try: 
                asyncio.run(generate_tts(st.session_state.md_generated_script, voice_char, a_generated, engine=audio_engine_choice, ttsmaker_key=key_ttsmaker, eleven_key=eleven_key_input, custom_eleven_id=custom_eleven_id, gemini_key=synergy_key if synergy_key else api_key_input, pitch=pitch_level, voice_fx=fx_level))
                st.session_state.md_audio_dur = get_file_duration(a_generated)
            except Exception as e: st.error(f"TTS Error: {e}"); st.stop()

        if subtitle_mode != "No Subtitle":
            with st.spinner("⏳ [၄/၄] Whisper ဖြင့် အသံနှင့် စာတန်းကို ချိန်ညှိနေပါသည်... (Audio Compressing...)"):
                pbar.progress(70, text="📝 Whisper Sync ပြုလုပ်နေပါသည်...")
                
                sync_audio_path = "md_sync_compressed.mp3"
                subprocess.run([FFMPEG_BINARY, "-y", "-i", a_generated, "-c:a", "libmp3lame", "-ab", "32k", "-ar", "16000", "-ac", "1", sync_audio_path], capture_output=True)
                
                if not os.path.exists(sync_audio_path) or os.path.getsize(sync_audio_path) < 100:
                    sync_audio_path = a_generated

                whisper_key = (groq_key_fc or load_key("GROQ_API_KEY") or load_key("saved_groq_key.txt") or api_key_input).strip()
                
                try:
                    raw_srt = ""
                    if whisper_key.startswith("gsk_"):
                        client_audio = Groq(api_key=whisper_key)
                        with open(sync_audio_path, "rb") as f:
                            transcription = client_audio.audio.transcriptions.create(
                                file=(sync_audio_path, f.read()),
                                model="whisper-large-v3",
                                response_format="verbose_json"
                            )
                        segments = transcription.segments if hasattr(transcription, 'segments') else transcription.get('segments', [])
                    else:
                        # 🔴 FIX: Properly initialize OpenAI client to avoid TypeError (unbound method)
                        client_openai = openai.OpenAI(api_key=whisper_key)
                        with open(sync_audio_path, "rb") as f:
                            transcription = client_openai.audio.transcriptions.create(
                                model="whisper-1", 
                                file=f, 
                                response_format="verbose_json"
                            )
                        segments = transcription.segments if hasattr(transcription, 'segments') else transcription.get('segments', [])

                    for i, segment in enumerate(segments, 1):
                        start_raw = segment['start'] if isinstance(segment, dict) else segment.start
                        end_raw = segment['end'] if isinstance(segment, dict) else segment.end
                        text_raw = segment['text'] if isinstance(segment, dict) else segment.text
                        
                        start = float(start_raw)
                        end = float(end_raw)
                        text = str(text_raw).strip()
                        
                        natural_dur = max(1.5, min(3.5, len(text) * 0.12))
                        end = min(start + natural_dur, end)
                        
                        def format_srt_time(seconds):
                            sec = float(seconds)
                            h = int(sec // 3600); m = int((sec % 3600) // 60); s = int(sec % 60); ms = int((sec % 1) * 1000)
                            return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
                        
                        raw_srt += f"{i}\n{format_srt_time(start)} --> {format_srt_time(end)}\n{text}\n\n"
                        
                    st.session_state.md_generated_srt = raw_srt.strip()
                except Exception as e:
                    st.error(f"❌ Whisper API Error: {e}")
                    st.stop()
        else: pbar.progress(75, text="⏩ Subtitle ပိတ်ထားသဖြင့် ကျော်ဖြတ်နေပါသည်...")

        st.session_state.md_step1_done = True
        pbar.progress(100, text="✅ အဆင့် (၁) ပြီးစီးပါပြီ!")

    # ==========================================
    # 🎬 STEP 2: REVIEW & FINAL RENDER
    # ==========================================
    if st.session_state.md_step1_done:
        st.markdown("<hr><h3 style='color: #38bdf8;'>🛠️ Step 2: Review & Final Render</h3>", unsafe_allow_html=True)
        
        col_r1, col_r2 = st.columns(2)
        with col_r1:
            st.markdown("**📝 Interactive SRT Editor**")
            if subtitle_mode != "No Subtitle":
                edited_srt = st.text_area("စာတန်းထိုးများကို စိတ်ကြိုက် ပြင်ဆင်နိုင်ပါသည်:", value=st.session_state.md_generated_srt, height=450)
            else:
                edited_srt = ""
                st.info("💡 Subtitles ပိတ်ထားပါသည်။")
                
        with col_r2:
            st.markdown("**👁️ 4-Axis Subtitle Blur Engine**")
            blur_x, blur_y, blur_w, blur_h = 0, 0, 0, 0
            if md_blur and os.path.exists(st.session_state.md_preview_frame):
                from PIL import Image, ImageFilter, ImageOps
                try:
                    img_raw = Image.open(st.session_state.md_preview_frame).convert("RGB")
                    if video_ratio == "Original":
                        v_w, v_h = img_raw.size
                        img_preview = img_raw
                    else:
                        v_w, v_h = (720, 1280) if "9:16" in video_ratio else (1280, 720)
                        img_preview = ImageOps.fit(img_raw, (int(v_w), int(v_h)))
                    
                    v_w = int(max(20, v_w))
                    v_h = int(max(20, v_h))
                    
                    blur_x = st.slider("↔️ Blur X (ဘယ်/ညာ)", 0, v_w, 0)
                    blur_y = st.slider("↕️ Blur Y (အထက်/အောက်)", 0, v_h, int(v_h * 0.75))
                    blur_w = st.slider("📐 Blur Width (အကျယ်)", 10, v_w, v_w)
                    blur_h = st.slider("📏 Blur Height (အမြင့်)", 10, v_h, int(v_h * 0.15))
                    
                    box_x1 = max(0, min(blur_x, v_w - 1))
                    box_y1 = max(0, min(blur_y, v_h - 1))
                    box_x2 = max(box_x1 + 1, min(blur_x + blur_w, v_w))
                    box_y2 = max(box_y1 + 1, min(blur_y + blur_h, v_h))
                    
                    cropped_part = img_preview.crop((box_x1, box_y1, box_x2, box_y2))
                    img_preview.paste(cropped_part.filter(ImageFilter.GaussianBlur(radius=22)), (box_x1, box_y1))
                    st.image(img_preview, caption="Live Blur Preview", use_column_width=True)
                except Exception as e: 
                    st.error(f"Preview Frame Layout Draw Failure: {e}")
            else:
                st.info("💡 Blur Option ပိတ်ထားပါသည်။ သို့မဟုတ် Preview ပုံမရှိပါ။")

        if st.button("🎬 RENDER MASTER VIDEO", type="primary"):
            st.session_state.md_run_id = str(int(time.time()))
            v_final = f"AETHER_DUBBING_{st.session_state.md_run_id}.mp4"
            st.session_state.final_video_path = v_final
            v_input, a_generated = "md_input.mp4", "md_audio.wav"
            
            with st.spinner("⏳ Master Video အား ပေါင်းစပ်ထုတ်လုပ်နေပါသည်..."):
                try:
                    parsed_timestamps = []
                    if subtitle_mode != "No Subtitle":
                        parsed_timestamps, _ = parse_and_save_real_srt(edited_srt, "subtitles.srt", use_fade=False)

                    # --- Custom FFmpeg Pipeline for Dubbing ---
                    audio = ffmpeg.input(a_generated).audio
                    video = ffmpeg.input(v_input).video
                    
                    if video_ratio == "Original":
                        try:
                            probe = ffmpeg.probe(v_input)
                            v_stream = next((s for s in probe['streams'] if s['codec_type'] == 'video'), None)
                            v_w, v_h = (int(v_stream['width']), int(v_stream['height'])) if v_stream else (1280, 720)
                        except: v_w, v_h = 1280, 720
                    else:
                        v_w, v_h = (720, 1280) if "9:16" in video_ratio else (1280, 720)
                        video = ffmpeg.filter(video, 'scale', v_w, v_h, force_original_aspect_ratio='increase').filter('crop', v_w, v_h)
                    
                    if cb_bypass: video = ffmpeg.filter(video, 'scale', '2*trunc(iw*1.08/2)', '2*trunc(ih*1.08/2)').filter('crop', 'iw/1.08', 'ih/1.08')
                    if cb_mirror: video = ffmpeg.filter(video, 'hflip')
                    if cb_color: video = ffmpeg.filter(video, 'eq', brightness=0.01, contrast=1.04, saturation=1.05)
                    if cb_grain: video = ffmpeg.filter(video, 'noise', alls=2, allf='t+u')
                    if cb_fps: video = ffmpeg.filter(video, 'fps', fps=24, round='near')
                    if cb_freeze: video = ffmpeg.filter(video, 'minterpolate', fps=12, mi_mode='dup')
                    
                    # 🔴 SUPER STABLE BLUR ENGINE
                    if md_blur and blur_w > 0 and blur_h > 0:
                        ff_x, ff_y = int(max(0, min(blur_x, v_w - 1))), int(max(0, min(blur_y, v_h - 1)))
                        ff_w, ff_h = int(max(10, min(blur_w, v_w - ff_x))), int(max(10, min(blur_h, v_h - ff_y)))
                        video = ffmpeg.filter(video, 'delogo', x=ff_x, y=ff_y, w=ff_w, h=ff_h, show=0)

                    # Subtitles Rendering
                    if subtitle_mode in ["Burn into Video", "Both (Burn + SRT)"] and parsed_timestamps:
                        wrap_width = 25 if "9:16" in video_ratio or (video_ratio == "Original" and v_h > v_w) else 45
                        safe_font_path = selected_font.replace('\\', '/')
                        for i, (start, end, text) in enumerate(parsed_timestamps):
                            wrapped_lines = textwrap.wrap(text, width=wrap_width) or [text]
                            max_len = max(len(line) for line in wrapped_lines)
                            centered_text = "\n".join(line.center(max_len, " ") for line in wrapped_lines)
                            with open(f"temp_sub_{i}.txt", "w", encoding="utf-8") as tf: tf.write(centered_text)
                            y_expr = "(h-text_h)/2" if "Center" in sub_position else ("150" if "Top" in sub_position else "h-text_h-120")
                            c_str = "yellow" if "Yellow" in sub_color else ("green" if "Green" in sub_color else ("red" if "Red" in sub_color else ("gold" if "Gold" in sub_color else "white")))
                            video = ffmpeg.filter(video, 'drawtext', textfile=f"temp_sub_{i}.txt", fontfile=safe_font_path, fontcolor=c_str, fontsize=sub_size, bordercolor='black', borderw=sub_thickness, x='(w-text_w)/2', y=y_expr, line_spacing=20, text_align='C', enable=f'between(t,{start},{end})')

                    if use_text_watermark and watermark_text: video = ffmpeg.filter(video, 'drawtext', text=watermark_text, x='w-tw-30', y='30', fontsize=26, fontcolor='white@0.4', fontfile=safe_font_path)
                    if uploaded_logo:
                        try:
                            with open("temp_logo.png", "wb") as f: f.write(uploaded_logo.getbuffer())
                            logo_input = ffmpeg.input("temp_logo.png").filter('scale', -1, 75)
                            video = ffmpeg.overlay(video, logo_input, x='W-w-30', y=30)
                        except: pass

                    ffmpeg.output(video, audio, "temp_dubbed.mp4", vcodec='libx264', pix_fmt='yuv420p', acodec='aac', preset='superfast', crf=22, t=st.session_state.md_audio_dur).overwrite_output().run(cmd=FFMPEG_BINARY, quiet=True)
                    
                    # --- BGM Mixing (Auto-Ducking) ---
                    if selected_bgm not in ["None (BGM မထည့်ပါ)"]:
                        st.info("🎵 Applying Cinematic Auto-Ducking BGM...")
                        bgm_path = os.path.join("bgm_tracks", random.choice(bgm_files) if "Auto" in selected_bgm else selected_bgm)
                        if os.path.exists(bgm_path):
                            ducked = ffmpeg.filter([ffmpeg.input(bgm_path, stream_loop=-1).audio.filter('aresample', 44100).filter('volume', bgm_volume), ffmpeg.input("temp_dubbed.mp4").audio], 'sidechaincompress', threshold=0.04, ratio=4, attack=50, release=300)
                            mixed = ffmpeg.filter([ffmpeg.input("temp_dubbed.mp4").audio, ducked], 'amix', inputs=2, duration='first').filter('volume', 2.0)
                            ffmpeg.output(ffmpeg.input("temp_dubbed.mp4").video, mixed, v_final, vcodec='copy', acodec='aac', t=st.session_state.md_audio_dur).overwrite_output().run(cmd=FFMPEG_BINARY, quiet=True)
                        else: shutil.move("temp_dubbed.mp4", v_final)
                    else: shutil.move("temp_dubbed.mp4", v_final)

                    # Thumbnails
                    try:
                        for tsuffix, t_val in [("A", min(st.session_state.md_audio_dur*0.2, 10)), ("B", min(st.session_state.md_audio_dur*0.5, 20))]:
                            tname = f"thumb_{tsuffix}_{st.session_state.md_run_id}.jpg"
                            if cb_thumb_text: success_thumb, _ = generate_professional_thumbnail(v_input, tname, st.session_state.md_viral_title, t_val, style=md_thumb_style, font_path=selected_font)
                            else: ffmpeg.input(v_input, ss=t_val).output(tname, vframes=1).overwrite_output().run(cmd=FFMPEG_BINARY, quiet=True); success_thumb = os.path.exists(tname)
                            if success_thumb:
                                if tsuffix == "A": st.session_state.thumb_path_A = tname
                                else: st.session_state.thumb_path_B = tname
                    except: pass

                    st.session_state.render_success = True
                except Exception as e: st.error(f"Render Error: {e}")

        # --- DASHBOARD ---
        if st.session_state.render_success:
            st.balloons()
            st.success("🎉 Movie Dubbing Video အောင်မြင်စွာ ထွက်လာပါပြီ!")
            st.markdown(f"<h2 style='color:#38bdf8; text-align:center;'>🔥 {st.session_state.md_viral_title}</h2>", unsafe_allow_html=True)
            
            col_o1, col_o2 = st.columns(2)
            with col_o1:
                st.video(st.session_state.final_video_path)
                st.markdown(get_download_link(st.session_state.final_video_path, f"Dubbed_{st.session_state.md_run_id}.mp4", "📥 Download Video"), unsafe_allow_html=True)
                if subtitle_mode != "No Subtitle" and os.path.exists("subtitles.srt"):
                    st.markdown(get_download_link("subtitles.srt", "Subtitles.srt", "📥 Download Subtitles (.SRT)"), unsafe_allow_html=True)
            with col_o2:
                col_ta, col_tb = st.columns(2)
                if hasattr(st.session_state, 'thumb_path_A') and os.path.exists(st.session_state.thumb_path_A):
                    with col_ta: st.image(st.session_state.thumb_path_A); st.markdown(get_download_link(st.session_state.thumb_path_A, "Thumb_A.jpg", "Download A"), unsafe_allow_html=True)
                if hasattr(st.session_state, 'thumb_path_B') and os.path.exists(st.session_state.thumb_path_B):
                    with col_tb: st.image(st.session_state.thumb_path_B); st.markdown(get_download_link(st.session_state.thumb_path_B, "Thumb_B.jpg", "Download B"), unsafe_allow_html=True)
                
                with st.expander("👁️ Review Scripts"):
                    st.text_area("AI Generated Script:", value=st.session_state.md_generated_script, height=150, disabled=True)
