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
import wave
import inspect
from google import genai
from groq import Groq
import openai

from utils.helpers import get_available_fonts, get_download_link, cleanup_temp_files, load_key
from core_engines.audio_tts import generate_tts
from core_engines.subtitle_sync import parse_and_save_real_srt
from core_engines.video_render import render_premium_saas_video, generate_professional_thumbnail, download_video_from_url, extract_audio_fast, FFMPEG_BINARY, VideoConfig

# 🔴 BULLETPROOF DURATION ENGINE
def get_wav_duration(file_path):
    try:
        with wave.open(file_path, 'r') as wf:
            return wf.getnframes() / float(wf.getframerate())
    except Exception:
        return 0.0

def get_video_duration(file_path):
    try:
        cmd = [FFMPEG_BINARY, "-i", file_path]
        result = subprocess.run(cmd, capture_output=True, text=True, errors='ignore')
        match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", result.stderr)
        if match:
            h, m, s = match.groups()
            return int(h) * 3600 + int(m) * 60 + float(s)
    except Exception: pass
    return 10.0

def fmt_time(seconds):
    sec = float(seconds)
    h = int(sec // 3600); m = int((sec % 3600) // 60); s = int(sec % 60); ms = int((sec % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

# 🔴 SYNC FIX: unlimited atempo chaining
def get_atempo_filter(ratio):
    if abs(ratio - 1.0) < 0.01:
        return None
    chain = []
    while ratio > 2.0:
        chain.append("atempo=2.0")
        ratio /= 2.0
    while ratio < 0.5:
        chain.append("atempo=0.5")
        ratio /= 0.5
    chain.append(f"atempo={ratio:.6f}")
    return ",".join(chain)

# 🔴 BURMESE UNICODE DETECTOR (stronger)
def is_burmese_script(text, threshold=0.6):
    """Check if at least threshold fraction of letters are in Myanmar Unicode range."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return False
    burmese_count = sum(1 for c in letters if '\u1000' <= c <= '\u109F')
    return (burmese_count / len(letters)) >= threshold

def render_movie_dubbing_studio(api_key_input, saved_gemini, ai_provider, groq_key_fc=None):
    st.markdown('<div class="setting-panel"><h3>🎙️ Movie Dubbing & Recap Studio</h3>', unsafe_allow_html=True)
    st.markdown("နိုင်ငံခြား ဇာတ်လမ်းတိုများကို မြန်မာလို အလိုအလျောက် ဘာသာပြန်ပြီး အသံထည့်ပါ။ (⚡ Smart Auto-Sync V52 စနစ်ပါဝင်သည်)")

    available_fonts = get_available_fonts()

    if "md_step1_done" not in st.session_state: st.session_state.md_step1_done = False
    if "md_generated_srt" not in st.session_state: st.session_state.md_generated_srt = ""
    if "md_generated_script" not in st.session_state: st.session_state.md_generated_script = ""
    if "md_viral_title" not in st.session_state: st.session_state.md_viral_title = ""
    if "md_viral_tags" not in st.session_state: st.session_state.md_viral_tags = ""
    if "md_run_id" not in st.session_state: st.session_state.md_run_id = str(int(time.time()))
    if "md_preview_frame" not in st.session_state: st.session_state.md_preview_frame = "md_preview.jpg"
    if "md_audio_dur" not in st.session_state: st.session_state.md_audio_dur = 0.0
    if "md_video_dur" not in st.session_state: st.session_state.md_video_dur = 10.0
    if "md_final_audio_path" not in st.session_state: st.session_state.md_final_audio_path = "md_audio.wav"

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
        sub_short = st.checkbox("✂️ Short & Punchy (Hormozi)", value=True)
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

                v_dur = get_video_duration(v_input)
                st.session_state.md_video_dur = v_dur

                preview_time = min(v_dur / 2, 5.0)
                ffmpeg.input(v_input, ss=preview_time).output(st.session_state.md_preview_frame, vframes=1).overwrite_output().run(cmd=FFMPEG_BINARY, quiet=True)
            except Exception as dl_err: st.error(str(dl_err)); st.stop()

        with st.spinner(f"⏳ [၂/၄] {ai_provider} ဖြင့် ဇာတ်ညွှန်းထုတ်လုပ်နေပါသည်..."):
            pbar.progress(30, text="🤖 ဇာတ်ညွှန်းနှင့် Title ဖန်တီးနေပါသည်...")
            try:
                extra_rules = ""
                if script_hook: extra_rules += " [HOOK]: Start with an engaging 3-second viral hook."
                if "Slang" in script_style: extra_rules += " [SLANG]: Use modern Myanmar internet slang and Gen-Z conversational tone."
                elif "Comedy" in script_style: extra_rules += " [COMEDY]: Make the narrative highly comedic, sarcastic, and funny."
                if script_curiosity: extra_rules += " [CURIOSITY]: Insert curiosity gaps to retain attention."
                if script_tone: extra_rules += " [TONE]: Inject strong emotions."
                extra_rules += f"\n[CRITICAL TIME LIMIT]: The video is exactly {v_dur:.1f} seconds long. Your Burmese script MUST be concise enough to be read aloud in EXACTLY {v_dur:.1f} seconds. Do NOT write a long essay."

                # 🔴 BURMESE FIX: Get English description first, then translate
                keys_list = [k.strip() for k in api_key_input.split(",") if k.strip()]
                english_story = ""
                success_script = False

                # --- Step A: Get English script / translation ---
                if "Gemini" in ai_provider:
                    for idx, current_key in enumerate(keys_list, 1):
                        st.toast(f"🔄 Script (English): Key {idx} ဖြင့် စမ်းသပ်နေပါသည်...")
                        try:
                            client = genai.Client(api_key=current_key)
                            target_file = v_input if "Original" in recap_mode else a_extracted
                            media_file = client.files.upload(file=target_file)
                            while "PROCESSING" in str(client.files.get(name=media_file.name).state): time.sleep(2)
                            # First get English story
                            eng_prompt = f"Watch the video carefully. Describe the story in English with a viral narrative style. Keep it concise, around {v_dur:.1f} seconds read time. At the end, provide a viral title and tags in English." if "Original" in recap_mode else f"Listen to the audio. Transcribe/translate it into English. Then create a viral recap in English. Keep it concise. At the end, [TITLE: ...] [TAGS: ...]"
                            res = client.models.generate_content(model="gemini-2.5-flash", contents=[media_file, eng_prompt])
                            english_story = res.text.strip()
                            client.files.delete(name=media_file.name)
                            success_script = True
                            st.toast(f"✅ English script ready.")
                            break
                        except Exception as e:
                            last_err = str(e)
                            st.toast(f"⚠️ Key {idx} Error: {e}")
                            try: client.files.delete(name=media_file.name)
                            except: pass
                            continue
                    if not success_script: raise Exception(f"Gemini English Error: {last_err}")
                else:
                    for idx, current_key in enumerate(keys_list, 1):
                        st.toast(f"🔄 Script (English): Key {idx} ဖြင့် စမ်းသပ်နေပါသည်...")
                        try:
                            client_llm = Groq(api_key=current_key) if "Groq" in ai_provider else openai.OpenAI(api_key=current_key)
                            # Get English transcription
                            if "Groq" in ai_provider:
                                with open(a_extracted, "rb") as file: transcription = client_llm.audio.translations.create(file=(a_extracted, file.read()), model="whisper-large-v3", response_format="text")
                                eng_text = str(transcription)
                            else:
                                with open(a_extracted, "rb") as file: ts_res = client_llm.audio.translations.create(model="whisper-1", file=file, response_format="text")
                                eng_text = str(ts_res)
                            # Create English story
                            eng_prompt = f"Turn this transcription into a viral storytelling recap in English. Keep it within {v_dur:.1f} seconds spoken length. At the end, [TITLE: ...] [TAGS: ...]"
                            comp = client_llm.chat.completions.create(model="llama-3.3-70b-versatile" if "Groq" in ai_provider else "gpt-4o", messages=[{"role": "user", "content": f"{eng_prompt}\n\nTranscription: {eng_text}"}])
                            english_story = comp.choices[0].message.content
                            success_script = True
                            st.toast(f"✅ English script ready.")
                            break
                        except Exception as e:
                            last_err = str(e)
                            st.toast(f"⚠️ Key {idx} Error: {e}")
                            continue
                    if not success_script: raise Exception(f"{ai_provider} English Error: {last_err}")

                # --- Step B: Translate to Burmese with strict prompt ---
                burmese_script = ""
                trans_success = False
                # Reuse first key for translation (any provider)
                trans_key = keys_list[0]
                for attempt in range(3):  # retry translation 3 times
                    st.toast(f"🔄 Burmese translation attempt {attempt+1}...")
                    try:
                        # Build translation prompt: we need natural Burmese, no Romanization
                        trans_prompt = (
                            "Translate the following English text into natural, fluent Myanmar (Burmese) script.\n"
                            "ABSOLUTE RULES:\n"
                            "- Use ONLY Burmese Unicode characters (e.g., ကခဂဃ...).\n"
                            "- Absolutely NO Romanization, NO English words, NO other scripts.\n"
                            "- Preserve the viral tone and excitement.\n"
                            "- Keep the same [TITLE: ...] and [TAGS: ...] format at the end.\n\n"
                            f"English text:\n{english_story}"
                        )
                        if "Gemini" in ai_provider:
                            client = genai.Client(api_key=trans_key)
                            res = client.models.generate_content(model="gemini-2.5-flash", contents=trans_prompt)
                            burmese_script = res.text.strip()
                        else:
                            client = Groq(api_key=trans_key) if "Groq" in ai_provider else openai.OpenAI(api_key=trans_key)
                            comp = client.chat.completions.create(model="llama-3.3-70b-versatile" if "Groq" in ai_provider else "gpt-4o", messages=[{"role": "user", "content": trans_prompt}])
                            burmese_script = comp.choices[0].message.content.strip()

                        # Check quality: must be majority Burmese
                        if is_burmese_script(burmese_script, threshold=0.6):
                            trans_success = True
                            st.toast(f"✅ Burmese translation successful!")
                            break
                        else:
                            st.toast(f"⚠️ Burmese check failed (attempt {attempt+1}). Retrying...")
                            # Make the prompt even stronger for next retry
                            trans_prompt = (
                                "CRITICAL: The previous output contained non-Burmese characters. "
                                "Now STRICTLY output ONLY Myanmar Unicode script. Do not add any Latin letters or other scripts. "
                                "Translate this English text to natural Burmese:\n" + english_story
                            )
                    except Exception as e:
                        st.toast(f"⚠️ Translation error: {e}")
                if not trans_success:
                    st.error("❌ AI cannot produce proper Burmese script. Please switch to a different AI provider (e.g., Gemini) or check your API quota.")
                    st.stop()

                # Extract title and tags
                title_match = re.search(r'\[TITLE:\s*(.*?)\]', burmese_script, re.IGNORECASE)
                tags_match = re.search(r'\[TAGS:\s*(.*?)\]', burmese_script, re.IGNORECASE)
                st.session_state.md_viral_title = re.sub(r'[\[\]]', '', title_match.group(1)).strip() if title_match else "မြန်မာရုပ်ရှင် ဇာတ်တိုကို"
                st.session_state.md_viral_tags = tags_match.group(1).strip() if tags_match else "#movie #myanmar"
                clean_script = re.sub(r'\[TITLE:.*?\]', '', burmese_script, flags=re.IGNORECASE)
                st.session_state.md_generated_script = re.sub(r'\[TAGS:.*?\]', '', clean_script, flags=re.IGNORECASE).strip()

            except Exception as e: st.error(f"Script generation failed: {e}"); st.stop()

        with st.spinner("⏳ [၃/၄] AI Voice Over ထုတ်လုပ်နေပါသည်... (⚡ Smart Auto-Sync ချိန်ညှိနေပါသည်)"):
            pbar.progress(50, text="🎙️ အသံသရုပ်ဆောင်ဖန်တီးနေပါသည်...")

            tts_keys = [k.strip() for k in (synergy_key if synergy_key else api_key_input).split(",") if k.strip()]
            success_tts = False
            last_tts_err = ""

            for idx, current_key in enumerate(tts_keys, 1):
                try:
                    st.toast(f"🎙️ TTS: Key {idx} ဖြင့် အသံထုတ်လုပ်နေပါသည်...")
                    if os.path.exists(a_generated): os.remove(a_generated)

                    if inspect.iscoroutinefunction(generate_tts):
                        asyncio.run(generate_tts(
                            st.session_state.md_generated_script,
                            voice_char,
                            a_generated,
                            engine=audio_engine_choice,
                            ttsmaker_key=key_ttsmaker,
                            eleven_key=eleven_key_input,
                            custom_eleven_id=custom_eleven_id,
                            gemini_key=current_key,
                            pitch=pitch_level,
                            voice_fx=fx_level
                        ))
                    else:
                        generate_tts(
                            st.session_state.md_generated_script,
                            voice_char,
                            a_generated,
                            engine=audio_engine_choice,
                            ttsmaker_key=key_ttsmaker,
                            eleven_key=eleven_key_input,
                            custom_eleven_id=custom_eleven_id,
                            gemini_key=current_key,
                            pitch=pitch_level,
                            voice_fx=fx_level
                        )

                    if os.path.exists(a_generated) and os.path.getsize(a_generated) > 100:
                        a_dur_raw = get_wav_duration(a_generated)

                        # 🔴 SYNC FIX
                        a_final_target = a_generated
                        if a_dur_raw > 0 and v_dur > 0:
                            ratio = a_dur_raw / v_dur
                            filt = get_atempo_filter(ratio)
                            if filt:
                                synced_audio = "md_audio_synced.wav"
                                subprocess.run([FFMPEG_BINARY, "-y", "-i", a_generated, "-filter:a", filt, synced_audio], capture_output=True)
                                if os.path.exists(synced_audio) and os.path.getsize(synced_audio) > 100:
                                    a_final_target = synced_audio
                                else:
                                    a_final_target = a_generated

                            exact_audio = "md_audio_exact.wav"
                            pad_filter = f"apad=whole_dur={v_dur}"
                            subprocess.run([FFMPEG_BINARY, "-y", "-i", a_final_target, "-af", pad_filter, "-t", str(v_dur), exact_audio], capture_output=True)
                            if os.path.exists(exact_audio) and os.path.getsize(exact_audio) > 100:
                                a_final_target = exact_audio

                        st.session_state.md_final_audio_path = a_final_target
                        st.session_state.md_audio_dur = get_wav_duration(a_final_target)
                        success_tts = True
                        st.toast(f"✅ TTS: Key {idx} အောင်မြင်ပါသည်။")
                        break
                    else:
                        last_tts_err = "Generated audio file is missing or empty."
                        st.toast(f"⚠️ TTS: Key {idx} မှ အသံမထွက်ပါ။")
                except Exception as e:
                    last_tts_err = str(e)
                    st.toast(f"⚠️ TTS: Key {idx} Error တက်သွားပါပြီ။")
                    continue

            if not success_tts:
                st.error(f"❌ TTS Error on ALL keys: {last_tts_err}. Please check your quota.")
                st.stop()

        if subtitle_mode != "No Subtitle":
            with st.spinner("⏳ [၄/၄] Whisper ဖြင့် အသံနှင့် စာတန်းကို ချိန်ညှိနေပါသည်... (V52 Auto Interpolation)"):
                pbar.progress(70, text="📝 Whisper Sync ပြုလုပ်နေပါသည်...")

                a_sync_input = "md_audio_optimized.mp3"
                try:
                    subprocess.run([FFMPEG_BINARY, "-y", "-i", st.session_state.md_final_audio_path, "-ar", "16000", "-ac", "1", "-b:a", "32k", a_sync_input], capture_output=True)
                    if not os.path.exists(a_sync_input): a_sync_input = st.session_state.md_final_audio_path
                except Exception:
                    a_sync_input = st.session_state.md_final_audio_path

                whisper_key_raw = (groq_key_fc or load_key("GROQ_API_KEY") or load_key("saved_groq_key.txt") or api_key_input).strip()
                whisper_keys = [k.strip() for k in whisper_key_raw.split(",") if k.strip()]

                sync_success = False; last_sync_err = ""
                max_retries_per_key = 3

                for idx, w_key in enumerate(whisper_keys, 1):
                    st.toast(f"📝 Sync: Key {idx} ဖြင့် စာတန်းထိုး ချိန်ညှိနေပါသည်...")
                    for attempt in range(max_retries_per_key):
                        try:
                            raw_srt_str = ""
                            chunk_idx = 1
                            client_audio = Groq(api_key=w_key) if w_key.startswith("gsk_") else openai.OpenAI(api_key=w_key)

                            with open(a_sync_input, "rb") as f:
                                if w_key.startswith("gsk_"):
                                    transcription = client_audio.audio.transcriptions.create(
                                        file=(a_sync_input, f.read()),
                                        model="whisper-large-v3",
                                        response_format="verbose_json",
                                        language="my"
                                    )
                                else:
                                    transcription = client_audio.audio.transcriptions.create(
                                        model="whisper-1",
                                        file=f,
                                        response_format="verbose_json",
                                        language="my"
                                    )

                            segments = transcription.segments if hasattr(transcription, 'segments') else transcription.get('segments', [])

                            for segment in segments:
                                start = float(segment['start'] if isinstance(segment, dict) else getattr(segment, 'start', 0.0))
                                end = float(segment['end'] if isinstance(segment, dict) else getattr(segment, 'end', 0.0))
                                text = str(segment['text'] if isinstance(segment, dict) else getattr(segment, 'text', '')).strip()

                                words = text.split()
                                chunk_size = 3 if sub_short else 6
                                for j in range(0, len(words), chunk_size):
                                    chunk = " ".join(words[j:j+chunk_size])
                                    chunk_start = start + (j / len(words)) * (end - start)
                                    chunk_end = start + (min(j + chunk_size, len(words)) / len(words)) * (end - start)

                                    raw_srt_str += f"{chunk_idx}\n{fmt_time(chunk_start)} --> {fmt_time(chunk_end)}\n{chunk}\n\n"
                                    chunk_idx += 1

                            st.session_state.md_generated_srt = raw_srt_str.strip()
                            sync_success = True
                            st.toast(f"✅ Sync: Key {idx} အောင်မြင်ပါသည်။")
                            break
                        except Exception as e:
                            last_sync_err = str(e)
                            if "500" in str(e) or "Internal Server Error" in str(e):
                                time.sleep(5); continue
                            else: break
                    if sync_success: break
                    else: st.toast(f"⚠️ Sync: Key {idx} အလုပ်မလုပ်ပါ။")

                if not sync_success:
                    st.error(f"❌ Whisper Sync Error: {last_sync_err}"); st.stop()
        else: pbar.progress(75, text="⏩ Subtitle ပိတ်ထားသဖြင့် ကျော်ဖြတ်နေပါသည်...")

        st.session_state.md_step1_done = True
        pbar.progress(100, text="✅ အဆင့် (၁) ပြီးစီးပါပြီ!")

    # ==========================================
    # 🎬 STEP 2: REVIEW & FINAL RENDER (unchanged from previous sync fix)
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
            v_input = "md_input.mp4"
            a_generated = st.session_state.md_final_audio_path

            with st.spinner("⏳ Master Video အား ပေါင်းစပ်ထုတ်လုပ်နေပါသည်..."):
                try:
                    parsed_timestamps = []
                    if subtitle_mode != "No Subtitle":
                        parsed_timestamps, _ = parse_and_save_real_srt(edited_srt, "subtitles.srt", use_fade=False)

                    render_dur = st.session_state.md_video_dur
                    if render_dur <= 0: render_dur = 10.0

                    audio = ffmpeg.input(a_generated).audio
                    video = ffmpeg.input(v_input).video

                    v_w_safe, v_h_safe = 1280, 720
                    if video_ratio == "Original":
                        try:
                            probe = ffmpeg.probe(v_input)
                            v_stream = next((s for s in probe['streams'] if s['codec_type'] == 'video'), None)
                            if v_stream:
                                v_w_safe = int(v_stream['width'])
                                v_h_safe = int(v_stream['height'])
                        except BaseException: pass
                    else:
                        v_w_safe, v_h_safe = (720, 1280) if "9:16" in video_ratio else (1280, 720)
                        video = ffmpeg.filter(video, 'scale', w=v_w_safe, h=v_h_safe, force_original_aspect_ratio='increase').filter('crop', w=v_w_safe, h=v_h_safe)

                    v_w_safe = v_w_safe - (v_w_safe % 2)
                    v_h_safe = v_h_safe - (v_h_safe % 2)

                    if cb_bypass:
                        scale_w = int(v_w_safe * 1.08); scale_w = scale_w - (scale_w % 2)
                        scale_h = int(v_h_safe * 1.08); scale_h = scale_h - (scale_h % 2)
                        video = ffmpeg.filter(video, 'scale', w=scale_w, h=scale_h).filter('crop', w=v_w_safe, h=v_h_safe)

                    if cb_mirror: video = ffmpeg.filter(video, 'hflip')
                    if cb_color: video = ffmpeg.filter(video, 'eq', brightness=0.01, contrast=1.04, saturation=1.05)
                    if cb_grain: video = ffmpeg.filter(video, 'noise', alls=2, allf='t+u')
                    if cb_fps: video = ffmpeg.filter(video, 'fps', fps=24)
                    if cb_freeze: video = ffmpeg.filter(video, 'fps', fps=12)

                    if md_blur and blur_w > 0 and blur_h > 0:
                        ff_x = max(0, min(int(blur_x), v_w_safe - 2))
                        ff_y = max(0, min(int(blur_y), v_h_safe - 2))
                        ff_w = max(4, min(int(blur_w), v_w_safe - ff_x - 1))
                        ff_h = max(4, min(int(blur_h), v_h_safe - ff_y - 1))
                        video = ffmpeg.filter(video, 'delogo', x=ff_x, y=ff_y, w=ff_w, h=ff_h, show=0)

                    if subtitle_mode in ["Burn into Video", "Both (Burn + SRT)"] and parsed_timestamps:
                        wrap_width = 25 if "9:16" in video_ratio or (video_ratio == "Original" and v_h_safe > v_w_safe) else 45
                        safe_font_path = os.path.abspath(selected_font).replace('\\', '/').replace(':', '\\:')

                        for i, (start, end, text) in enumerate(parsed_timestamps):
                            wrapped_lines = textwrap.wrap(text, width=wrap_width) or [text]
                            max_len = max(len(line) for line in wrapped_lines)
                            centered_text = "\n".join(line.center(max_len, " ") for line in wrapped_lines)

                            txt_filename = f"temp_sub_{i}.txt"
                            with open(txt_filename, "w", encoding="utf-8") as tf: tf.write(centered_text)
                            abs_txt_filename = os.path.abspath(txt_filename).replace('\\', '/').replace(':', '\\:')

                            y_expr = "(h-text_h)/2" if "Center" in sub_position else ("150" if "Top" in sub_position else "h-text_h-120")
                            c_str = "yellow" if "Yellow" in sub_color else ("green" if "Green" in sub_color else ("red" if "Red" in sub_color else ("gold" if "Gold" in sub_color else "white")))

                            video = ffmpeg.filter(video, 'drawtext', textfile=abs_txt_filename, fontfile=safe_font_path, fontcolor=c_str, fontsize=sub_size, bordercolor='black', borderw=sub_thickness, x='(w-text_w)/2', y=y_expr, line_spacing=20, text_align='C', enable=f'between(t,{start},{end})')

                    if use_text_watermark and watermark_text:
                        video = ffmpeg.filter(video, 'drawtext', text=watermark_text, x='w-tw-30', y='30', fontsize=26, fontcolor='white@0.4', fontfile=safe_font_path)

                    if uploaded_logo:
                        try:
                            logo_path = "temp_logo.png"
                            with open(logo_path, "wb") as f: f.write(uploaded_logo.getbuffer())
                            logo_input = ffmpeg.input(logo_path).filter('scale', -1, 75)
                            video = ffmpeg.overlay(video, logo_input, x='W-w-30', y=30)
                        except BaseException: pass

                    try:
                        (
                            ffmpeg.output(video, audio, "temp_dubbed.mp4", vcodec='libx264', pix_fmt='yuv420p', acodec='aac', preset='superfast', crf=22, t=render_dur)
                            .overwrite_output()
                            .run(cmd=FFMPEG_BINARY, capture_stderr=True)
                        )
                    except ffmpeg.Error as e:
                        err_msg = e.stderr.decode('utf8', errors='ignore') if e.stderr else str(e)
                        raise Exception(f"Video Rendering Engine Failed:\n```\n{err_msg}\n```")

                    if selected_bgm not in ["None (BGM မထည့်ပါ)"]:
                        st.info("🎵 Applying Cinematic Auto-Ducking BGM...")
                        bgm_path = os.path.join("bgm_tracks", random.choice(bgm_files) if "Auto" in selected_bgm else selected_bgm)
                        if os.path.exists(bgm_path):
                            try:
                                main_a = ffmpeg.input("temp_dubbed.mp4").audio
                                bgm_a = ffmpeg.input(bgm_path, stream_loop=-1).audio.filter('volume', bgm_volume)
                                mixed = ffmpeg.filter([main_a, bgm_a], 'amix', inputs=2, duration='longest')
                                ffmpeg.output(ffmpeg.input("temp_dubbed.mp4").video, mixed, v_final, vcodec='copy', acodec='aac', t=render_dur).overwrite_output().run(cmd=FFMPEG_BINARY, capture_stderr=True)
                            except ffmpeg.Error as e:
                                err_msg = e.stderr.decode('utf8', errors='ignore') if e.stderr else str(e)
                                st.warning(f"BGM Mixing failed, skipping BGM:\n{err_msg}")
                                shutil.move("temp_dubbed.mp4", v_final)
                        else: shutil.move("temp_dubbed.mp4", v_final)
                    else: shutil.move("temp_dubbed.mp4", v_final)

                    try:
                        for tsuffix, t_val in [("A", min(render_dur*0.2, 10)), ("B", min(render_dur*0.5, 20))]:
                            tname = f"thumb_{tsuffix}_{st.session_state.md_run_id}.jpg"
                            if cb_thumb_text: success_thumb, _ = generate_professional_thumbnail(v_input, tname, st.session_state.md_viral_title, t_val, style=md_thumb_style, font_path=selected_font)
                            else: ffmpeg.input(v_input, ss=t_val).output(tname, vframes=1).overwrite_output().run(cmd=FFMPEG_BINARY, quiet=True); success_thumb = os.path.exists(tname)
                            if success_thumb:
                                if tsuffix == "A": st.session_state.thumb_path_A = tname
                                else: st.session_state.thumb_path_B = tname
                    except BaseException: pass

                    st.session_state.render_success = True
                except Exception as e:
                    st.error(f"Render Core Error:\n\n{e}")

        # --- DASHBOARD ---
        if st.session_state.render_success:
            st.balloons()
            st.success("🎉 Movie Dubbing Video အောင်မြင်စွာ ထွက်လာပါပြီ!")
            st.markdown(f"<h2 style='color:#38bdf8; text-align:center;'>🔥 {st.session_state.md_viral_title}</h2>", unsafe_allow_html=True)

            col_o1, col_o2 = st.columns(2)
            with col_o1:
                if st.session_state.get("final_video_path") and os.path.exists(st.session_state.final_video_path):
                    st.video(st.session_state.final_video_path)
                    st.markdown(get_download_link(st.session_state.final_video_path, f"Dubbed_{st.session_state.md_run_id}.mp4", "📥 Download Video"), unsafe_allow_html=True)
                else:
                    st.warning("⚠️ Video file missing after render. Please try rendering again.")

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
