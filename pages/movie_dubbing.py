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
from core_engines.video_render import generate_professional_thumbnail, download_video_from_url, extract_audio_fast, FFMPEG_BINARY, VideoConfig

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
    except Exception:
        pass
    return 10.0

def fmt_time(seconds):
    sec = float(seconds)
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    ms = int((sec % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

# 🔴 FIXED render_premium_saas_video (with unlimited atempo chain, no slowdown)
def render_premium_saas_video(in_v, in_a, parsed_timestamps, out_v, ratio,
                               use_bypass=False, use_blur=False, watermark="",
                               subtitle_mode="Both (Burn + SRT)", use_mirror=False,
                               use_color=False, use_grain=False, use_fps=False,
                               sub_style_str="", use_freeze=False, logo_path=None,
                               font_dir="."):
    try:
        a_dur = get_file_duration(in_a)
        v_max_dur = get_file_duration(in_v)

        safe_srt_path = os.path.abspath("subtitles.srt").replace('\\', '/')
        safe_srt_path_escaped = safe_srt_path.replace(':', '\\:')
        safe_font_dir = font_dir.replace('\\', '/').replace(':', '\\:')

        with open("subtitles.srt", "w", encoding="utf-8-sig") as f:
            for i, (start, end, text) in enumerate(parsed_timestamps, start=1):
                if start >= v_max_dur:
                    continue
                safe_end = min(end, v_max_dur)
                def fmt_t(s):
                    return f"{int(s//3600):02d}:{int((s%3600)//60):02d}:{int(s%60):02d},{int((s-int(s))*1000):03d}"
                f.write(f"{i}\n{fmt_t(start)} --> {fmt_t(safe_end)}\n{text}\n\n")

        video = ffmpeg.input(in_v).video
        if use_bypass:
            video = ffmpeg.filter(video, 'scale', '2*trunc(iw*1.08/2)', '2*trunc(ih*1.08/2)').filter('crop', 'iw/1.08', 'ih/1.08')
        if use_mirror:
            video = ffmpeg.filter(video, 'hflip')
        if use_color:
            video = ffmpeg.filter(video, 'eq', brightness=0.02, contrast=1.05, saturation=1.1)
        if use_grain:
            video = ffmpeg.filter(video, 'noise', alls=2, allf='t+u')
        if use_fps:
            video = ffmpeg.filter(video, 'fps', fps=24, round='near')
        if use_freeze:
            video = ffmpeg.filter(video, 'minterpolate', fps=12, mi_mode='dup')

        video = ffmpeg.filter(video, 'scale', 'trunc(oh*a/2)*2', 1080, flags='bicubic')

        # ---------- AUDIO SYNC FIX ----------
        audio = ffmpeg.input(in_a).audio

        # 1. Speed up if audio is longer than video (unlimited atempo chain)
        if a_dur > v_max_dur * 1.01:
            ratio = a_dur / v_max_dur
            chain = []
            temp_r = ratio
            while temp_r > 2.0:
                chain.append("atempo=2.0")
                temp_r /= 2.0
            while temp_r < 0.5:
                chain.append("atempo=0.5")
                temp_r /= 0.5
            chain.append(f"atempo={temp_r:.6f}")
            atempo_filter = ",".join(chain)
            audio = ffmpeg.filter(audio, 'atempo', atempo_filter)

        # 2. Trim to exact video duration and pad with silence if needed
        audio = ffmpeg.filter(audio, 'atrim', start=0, end=v_max_dur)
        audio = ffmpeg.filter(audio, 'apad', whole_dur=v_max_dur)

        # ---------- Visual adjustments ----------
        if use_blur:
            video = ffmpeg.filter(video, 'drawbox', x=0, y='ih-90', w='iw', h=90, color='black@0.95', thickness='fill')
        if ratio == "9:16 (TikTok/Shorts)":
            video = ffmpeg.filter(video, 'crop', 'min(iw, ih*9/16)', 'ih')
        elif ratio == "16:9 (YouTube)":
            video = ffmpeg.filter(video, 'crop', 'iw', 'min(ih, iw*9/16)')

        if watermark:
            video = ffmpeg.filter(video, 'drawtext', text=watermark, x='w-tw-15', y='15', fontsize=30, fontcolor='white@0.5')

        if logo_path and os.path.exists(logo_path):
            logo = ffmpeg.input(logo_path)
            logo = ffmpeg.filter(logo, 'scale', -1, 80)
            video = ffmpeg.overlay(video, logo, x='W-w-20', y=20)

        if subtitle_mode in ["Burn into Video", "Both (Burn + SRT)"] and os.path.exists("subtitles.srt"):
            video = ffmpeg.filter(video, 'subtitles', safe_srt_path_escaped,
                                  charenc='UTF-8', fontsdir=safe_font_dir,
                                  force_style=sub_style_str)

        out = ffmpeg.output(video, audio, out_v,
                            vcodec='libx264', acodec='aac', preset='fast', crf=21,
                            t=v_max_dur)
        out.run(cmd=FFMPEG_BINARY, overwrite_output=True, capture_stdout=True, capture_stderr=True)
        return True, "Success"
    except ffmpeg.Error as e:
        return False, str(e)

def get_file_duration(file_path):
    return get_video_duration(file_path)

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

    # ---------- Sidebar ----------
    with st.sidebar:
        st.markdown("---")
        audio_engine_choice = st.radio("Voice Engine (Dubbing)", [
            "Edge-TTS (Default Free)",
            "Google Synergy TTS (Flash 3.1 Preview)",
            "ElevenLabs (Premium AI)",
            "TTSMaker (Free API)"
        ])
        synergy_key = ""
        eleven_key_input, custom_eleven_id, key_ttsmaker = "", "", ""
        if "Synergy" in audio_engine_choice:
            synergy_key = st.text_input("API Key for Synergy TTS", type="password", value=saved_gemini)
        if "ElevenLabs" in audio_engine_choice:
            eleven_key_input = st.text_input("ElevenLabs API Key", type="password")
            custom_eleven_id = st.text_input("Custom Voice ID")
        if "TTSMaker" in audio_engine_choice:
            key_ttsmaker = st.text_input("TTSMaker API Key", type="password")

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
        md_thumb_style = st.selectbox("🖼️ Thumbnail Style", [
            "🔥 Viral TikTok Style",
            "🎬 Cinematic Movie Poster",
            "👻 Horror / Mystery",
            "💎 Premium / Luxury",
            "⚡ Clean / Minimal"
        ])

        st.markdown("<b>©️ Brand Watermark</b>", unsafe_allow_html=True)
        uploaded_logo = st.file_uploader("🖼️ Add Logo Image", type=["png", "jpg", "jpeg"])
        use_text_watermark = st.checkbox("✍️ Use Text Watermark instead", value=False)
        watermark_text = st.text_input("Text Watermark", "") if use_text_watermark else ""

        subtitle_mode = st.radio("Subtitle Output", [
            "Both (Burn + SRT)",
            "Export SRT File Only",
            "Burn into Video",
            "No Subtitle"
        ])

    # ---------- Main input columns ----------
    st.markdown('<div class="setting-panel"><h3>📺 Media Acquisition & Setup</h3>', unsafe_allow_html=True)
    col_in1, col_in2 = st.columns([1, 1])
    with col_in1:
        video_url = st.text_input("🔗 Paste Short Drama URL Link", placeholder="https://...")
        uploaded_file = st.file_uploader("📥 OR Upload Video File (MP4)", type=["mp4"])

        st.markdown("<br><div class='sub-box'>", unsafe_allow_html=True)
        st.markdown("<p style='font-weight: bold; color: #38bdf8; font-size: 16px;'>✍️ AI Storytelling & Script Rules</p>", unsafe_allow_html=True)
        recap_mode = st.radio("🎬 Recap Mode", [
            "Translate Original Video (မူရင်းကို ဘာသာပြန်မည်)",
            "Create Original AI Story (ကိုယ်ပိုင်ဇာတ်လမ်းဖန်တီးမည်)"
        ])
        script_style = st.selectbox("🎭 Script Style (ဇာတ်ညွှန်း ပုံစံ)", [
            "Normal (ပုံမှန်အညွှန်း)",
            "Slang (လူငယ်သုံး/Gen-Z)",
            "Comedy (ဟာသပြောင်ချော်ချော်)",
            "Suspense (သည်းထိတ်ရင်ဖို)"
        ])
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
        dynamic_options = ["Synergy Puck (Male)", "Synergy Aoede (Female)", "Synergy Charon (Deep)"] if "Synergy" in audio_engine_choice else (
            ["Adam (Deep)", "Rachel (Female)"] if "ElevenLabs" in audio_engine_choice else (
                ["TTSMaker Male", "TTSMaker Female"] if "TTSMaker" in audio_engine_choice else [
                    "ဇော်ဇော် (Male)", "အောင်အောင် (Deep)", "နှင်းနှင်း (Female)"
                ]))
        voice_char = st.selectbox("Select Character Voice", dynamic_options, index=0)
        pitch_level = st.slider("🎙️ Voice Pitch", min_value=-30, max_value=30, value=0, step=5)
        fx_level = st.selectbox("🎧 Cinematic Voice FX", [
            "None", "🎙️ Epic Trailer Voice", "📻 Walkie-Talkie", "🏛️ Cinematic Reverb",
            "👹 Demon / Monster", "🤫 ASMR / Whisper", "🤖 Robot / Cyborg",
            "📞 Old Telephone", "⛰️ Deep Cave Echo", "🌊 Underwater / Muffled",
            "🔥 Motivation", "👻 Horror", "🌀 Spatial 3D Audio", "🎭 Multi-Persona"
        ])

        st.markdown("<div class='sub-box'>", unsafe_allow_html=True)
        st.markdown("<p style='font-weight: bold; color: #818cf8; font-size: 16px;'>📝 Subtitle Pro Settings</p>", unsafe_allow_html=True)
        selected_font = st.selectbox("🔤 Font Style", available_fonts, index=0)
        sub_position = st.selectbox("📍 Position", ["Bottom", "Center", "Top"])
        sub_color = st.selectbox("🎨 Color", [
            "Yellow Text", "White Text", "Neon Green Text", "Red Text", "Gold Text"
        ])
        sub_size = st.slider("🔠 Font Size", 16, 50, 28)
        sub_thickness = st.slider("✒️ Outline Thickness", 1.0, 5.0, 2.5)
        sub_short = st.checkbox("✂️ Short & Punchy (Hormozi)", value=True)
        st.markdown("</div>", unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # ==========================================
    # 🚀 STEP 1: GENERATE DUBBING & ASSETS
    # ==========================================
    if st.button("🚀 STEP 1: Generate AI Dubbing & Assets"):
        if not api_key_input:
            st.error("⚠️ API Key လိုအပ်ပါသည်။")
            return
        if not uploaded_file and not video_url:
            st.error("⚠️ ဗီဒီယိုထည့်ပေးပါ။")
            return

        st.session_state.render_success = False
        st.session_state.md_step1_done = False
        cleanup_temp_files()
        st.session_state.md_run_id = str(int(time.time()))

        pbar = st.progress(0, text="🚀 အလုပ်စတင်နေပါပြီ...")
        v_input, a_extracted, a_generated = "md_input.mp4", "md_extracted.mp3", "md_audio.wav"

        # ---------- 1️⃣ Download / Upload Video ----------
        with st.spinner("⏳ [၁/၄] ဗီဒီယို ဖိုင်အားစနစ်ထဲသို့ ဆွဲသွင်းနေပါသည်..."):
            pbar.progress(10, text="📥 ဗီဒီယိုဆွဲယူနေပါသည်...")
            try:
                if uploaded_file:
                    with open(v_input, "wb") as f:
                        f.write(uploaded_file.read())
                else:
                    download_video_from_url(video_url, v_input)
                extract_audio_fast(v_input, a_extracted)

                v_dur = get_video_duration(v_input)
                st.session_state.md_video_dur = v_dur

                preview_time = min(v_dur / 2, 5.0)
                ffmpeg.input(v_input, ss=preview_time).output(st.session_state.md_preview_frame, vframes=1).overwrite_output().run(cmd=FFMPEG_BINARY, quiet=True)
            except Exception as dl_err:
                st.error(str(dl_err))
                st.stop()

        # ---------- 2️⃣ Generate Script (BACK TO SRT FORMAT) ----------
        with st.spinner(f"⏳ [၂/၄] {ai_provider} ဖြင့် ဇာတ်ညွှန်းထုတ်လုပ်နေပါသည်..."):
            pbar.progress(30, text="🤖 ဇာတ်ညွှန်းနှင့် Title ဖန်တီးနေပါသည်...")
            try:
                extra_rules = ""
                if script_hook:
                    extra_rules += " [HOOK]: Start with an engaging 3-second viral hook."
                if "Slang" in script_style:
                    extra_rules += " [SLANG]: Use modern Myanmar internet slang and Gen-Z conversational tone."
                elif "Comedy" in script_style:
                    extra_rules += " [COMEDY]: Make the narrative highly comedic, sarcastic, and funny."
                if script_curiosity:
                    extra_rules += " [CURIOSITY]: Insert curiosity gaps to retain attention."
                if script_tone:
                    extra_rules += " [TONE]: Inject strong emotions."

                extra_rules += f"\n[CRITICAL TIME LIMIT]: The video is exactly {v_dur:.1f} seconds long. Your Burmese script MUST be concise enough to be read aloud in EXACTLY {v_dur:.1f} seconds. Do NOT write a long essay."
                extra_rules += "\n[ABSOLUTE REQUIREMENT]: Output ONLY pure Myanmar Unicode script (Burmese characters). NO Romanization, NO English, NO other scripts. The script must be natural spoken Burmese."
                extra_rules += "\n[OUTPUT FORMAT]: You MUST output the script in valid SRT format with accurate timestamps that match the scenes."
                extra_rules += "\nAt the absolute end of the response, you MUST include these two lines on separate lines:\n[TITLE: (Provide a viral Burmese title here)]\n[TAGS: #tag1 #tag2]"

                raw_output_text = ""
                keys_list = [k.strip() for k in api_key_input.split(",") if k.strip()]

                if "Gemini" in ai_provider:
                    success_gemini = False
                    last_err = ""
                    for idx, current_key in enumerate(keys_list, 1):
                        st.toast(f"🔄 Script: Key {idx} ဖြင့် စမ်းသပ်နေပါသည်...")
                        try:
                            client = genai.Client(api_key=current_key)
                            target_file = v_input if "Original" in recap_mode else a_extracted
                            media_file = client.files.upload(file=target_file)
                            while "PROCESSING" in str(client.files.get(name=media_file.name).state):
                                time.sleep(2)
                            gemini_prompt = (
                                "Watch the video carefully. Invent an ORIGINAL, highly engaging storytelling recap in Burmese. "
                                "Do NOT just translate. STRICT RULES: 1. NO ENGLISH TRANSLITERATION. 2. Output pure text narrative. "
                                f"{extra_rules}"
                            ) if "Original" in recap_mode else (
                                "Listen to the audio. Translate and adapt the text into highly engaging spoken Burmese. "
                                "STRICT RULES: 1. NO ENGLISH TRANSLITERATION. 2. Output pure text narrative. "
                                f"{extra_rules}"
                            )
                            res = client.models.generate_content(
                                model="gemini-2.5-flash",
                                contents=[media_file, gemini_prompt]
                            )
                            raw_output_text = res.text.strip()
                            client.files.delete(name=media_file.name)
                            success_gemini = True
                            st.toast(f"✅ Script: Key {idx} အောင်မြင်ပါသည်။")
                            break
                        except Exception as e:
                            last_err = str(e)
                            st.toast(f"⚠️ Script: Key {idx} Limit ကုန်/Error တက်သွားပါပြီ။")
                            try:
                                client.files.delete(name=media_file.name)
                            except Exception:
                                pass
                            continue
                    if not success_gemini:
                        raise Exception(f"Gemini Error: {last_err}")
                else:
                    success_llm = False
                    last_err = ""
                    for idx, current_key in enumerate(keys_list, 1):
                        st.toast(f"🔄 Script: Key {idx} ဖြင့် စမ်းသပ်နေပါသည်...")
                        try:
                            client_llm = Groq(api_key=current_key) if "Groq" in ai_provider else openai.OpenAI(api_key=current_key)
                            if "Groq" in ai_provider:
                                with open(a_extracted, "rb") as file:
                                    transcription = client_llm.audio.translations.create(
                                        file=(a_extracted, file.read()),
                                        model="whisper-large-v3",
                                        response_format="verbose_json"
                                    )
                                    tsrt = "".join([
                                        f"{i}\n00:00:00,000 --> 00:00:10,000\n{seg['text']}\n\n"
                                        for i, seg in enumerate(transcription.get('segments', []), 1)
                                    ]) if isinstance(transcription, dict) else str(transcription)
                            else:
                                with open(a_extracted, "rb") as file:
                                    ts_res = client_llm.audio.translations.create(
                                        model="whisper-1", file=file, response_format="srt"
                                    )
                                    tsrt = str(ts_res)

                            base_prompt = f"Translate and adapt the English SRT into engaging Burmese. Output pure text narrative. {extra_rules}"
                            comp = client_llm.chat.completions.create(
                                model="llama-3.3-70b-versatile" if "Groq" in ai_provider else "gpt-4o",
                                messages=[{"role": "user", "content": f"{base_prompt} --- SRT --- {tsrt}"}]
                            )
                            raw_output_text = comp.choices[0].message.content
                            success_llm = True
                            st.toast(f"✅ Script: Key {idx} အောင်မြင်ပါသည်။")
                            break
                        except Exception as e:
                            last_err = str(e)
                            st.toast(f"⚠️ Script: Key {idx} Limit ကုန်/Error တက်သွားပါပြီ။")
                            continue
                    if not success_llm:
                        raise Exception(f"{ai_provider} Error: {last_err}")

                # Extract title and tags
                title_match = re.search(r'\[TITLE:\s*(.*?)\]', raw_output_text, re.IGNORECASE)
                tags_match = re.search(r'\[TAGS:\s*(.*?)\]', raw_output_text, re.IGNORECASE)
                st.session_state.md_viral_title = re.sub(r'[\[\]]', '', title_match.group(1)).strip() if title_match else "Viral Movie Recap"
                st.session_state.md_viral_tags = tags_match.group(1).strip() if tags_match else "#movierecap #myanmar"

                # Clean up the raw SRT text (remove title/tags)
                clean_srt_text = re.sub(r'\[TITLE:.*?\]', '', raw_output_text, flags=re.IGNORECASE)
                clean_srt_text = re.sub(r'\[TAGS:.*?\]', '', clean_srt_text, flags=re.IGNORECASE).strip()

                # Parse the SRT into timestamps and speech text
                parsed_timestamps, speech_text = parse_and_save_real_srt(
                    clean_srt_text,
                    "subtitles.srt",
                    use_fade=False,
                    max_words=3 if sub_short else 6
                )

                st.session_state.md_generated_script = clean_srt_text
                st.session_state.md_generated_srt = clean_srt_text

            except Exception as e:
                st.error(f"Script Error: {e}")
                st.stop()

        # ---------- 3️⃣ Generate TTS Audio (remove tags, use speech text) ----------
        with st.spinner("⏳ [၃/၄] AI Voice Over ထုတ်လုပ်နေပါသည်... (⚡ Smart Auto-Sync)"):
            pbar.progress(50, text="🎙️ အသံသရုပ်ဆောင်ဖန်တီးနေပါသည်...")

            # 🔴 Remove Synergy tags like [pause=1.0] from speech text before TTS
            clean_speech = re.sub(r'\[.*?\]', '', speech_text)
            clean_speech = re.sub(r'\{.*?\}', '', clean_speech)

            tts_keys = [k.strip() for k in (synergy_key if synergy_key else api_key_input).split(",") if k.strip()]
            success_tts = False
            last_tts_err = ""

            for idx, current_key in enumerate(tts_keys, 1):
                try:
                    st.toast(f"🎙️ TTS: Key {idx} ဖြင့် အသံထုတ်လုပ်နေပါသည်...")
                    if os.path.exists(a_generated):
                        os.remove(a_generated)

                    if inspect.iscoroutinefunction(generate_tts):
                        asyncio.run(generate_tts(
                            clean_speech,
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
                            clean_speech,
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
                        st.session_state.md_final_audio_path = a_generated
                        st.session_state.md_audio_dur = get_wav_duration(a_generated)
                        success_tts = True
                        st.toast(f"✅ TTS: Key {idx} အောင်မြင်ပါသည်။ (Audio {st.session_state.md_audio_dur:.2f}s)")
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

        # ---------- 4️⃣ Subtitle already generated from SRT, nothing more ----------
        if subtitle_mode != "No Subtitle":
            pbar.progress(75, text="✅ စာတန်းထိုး အသင့်ဖြစ်ပါပြီ။")
        else:
            pbar.progress(75, text="⏩ Subtitle ပိတ်ထားသဖြင့် ကျော်ဖြတ်နေပါသည်...")

        st.session_state.md_step1_done = True
        pbar.progress(100, text="✅ အဆင့် (၁) ပြီးစီးပါပြီ!")

    # ==========================================
    # 🎬 STEP 2: REVIEW & FINAL RENDER
    # ==========================================
    if st.session_state.md_step1_done:
        st.markdown("<hr><h3 style='color: #38bdf8;'>🛠️ Step 2: Review & Final Render</h3>", unsafe_allow_html=True)

        safe_font_path = os.path.abspath(selected_font).replace('\\', '/').replace(':', '\\:')

        col_r1, col_r2 = st.columns(2)
        with col_r1:
            st.markdown("**📝 Interactive SRT Editor**")
            if subtitle_mode != "No Subtitle":
                edited_srt = st.text_area("စာတန်းထိုးများကို စိတ်ကြိုက် ပြင်ဆင်နိုင်ပါသည်:",
                                          value=st.session_state.md_generated_srt, height=450)
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
                    # Re-parse the edited SRT
                    parsed_timestamps = []
                    if subtitle_mode != "No Subtitle":
                        parsed_timestamps, _ = parse_and_save_real_srt(
                            edited_srt, "subtitles.srt", use_fade=False,
                            max_words=3 if sub_short else 6
                        )

                    render_dur = st.session_state.md_video_dur
                    if render_dur <= 0:
                        render_dur = 10.0

                    # Build subtitle style
                    align_val = 2 if "Bottom" in sub_position else (5 if "Center" in sub_position else 8)
                    prim_c = "&H0000FFFF" if "Yellow" in sub_color else (
                        "&H00FFFFFF" if "White" in sub_color else (
                            "&H0000FF00" if "Green" in sub_color else (
                                "&H000000FF" if "Red" in sub_color else "&H00FFFFFF"
                            )
                        )
                    )
                    dyn_style = f"FontName={selected_font},FontSize={sub_size},PrimaryColour={prim_c},BackColour=0,Outline={sub_thickness},Alignment={align_val},MarginV=60"

                    logo_file_path = None
                    if uploaded_logo and not use_text_watermark:
                        logo_file_path = "temp_logo.png"
                        with open(logo_file_path, "wb") as f:
                            f.write(uploaded_logo.getbuffer())

                    success, err_msg = render_premium_saas_video(
                        v_input, a_generated, parsed_timestamps, v_final,
                        video_ratio, cb_bypass, md_blur, watermark_text,
                        subtitle_mode, cb_mirror, cb_color, cb_grain, cb_fps,
                        dyn_style, cb_freeze, logo_file_path,
                        font_dir=os.path.dirname(selected_font) if os.path.exists(selected_font) else "."
                    )
                    if not success:
                        st.error(f"Render Error: {err_msg}")

                    # BGM
                    if success and selected_bgm not in ["None (BGM မထည့်ပါ)"]:
                        st.info("🎵 Applying Cinematic Auto-Ducking BGM...")
                        bgm_path = os.path.join("bgm_tracks", random.choice(bgm_files) if "Auto" in selected_bgm else selected_bgm)
                        if os.path.exists(bgm_path):
                            try:
                                temp_bgm = "temp_bgm.mp4"
                                v_dur = get_file_duration(v_final)
                                main_v = ffmpeg.input(v_final).video
                                main_a = ffmpeg.input(v_final).audio
                                bgm_a = ffmpeg.input(bgm_path, stream_loop=-1).audio.filter('volume', bgm_volume)
                                ducked = ffmpeg.filter([bgm_a, main_a], 'sidechaincompress', threshold=0.04, ratio=4, attack=50, release=300)
                                mixed = ffmpeg.filter([main_a, ducked], 'amix', inputs=2, duration='first').filter('volume', 2.0)
                                ffmpeg.output(main_v, mixed, temp_bgm, vcodec='copy', acodec='aac', t=v_dur).overwrite_output().run(cmd=FFMPEG_BINARY, quiet=True)
                                shutil.move(temp_bgm, v_final)
                            except Exception as e:
                                st.warning(f"BGM mixing failed: {e}")

                    if success:
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
                    with col_ta:
                        st.image(st.session_state.thumb_path_A)
                        st.markdown(get_download_link(st.session_state.thumb_path_A, "Thumb_A.jpg", "Download A"), unsafe_allow_html=True)
                if hasattr(st.session_state, 'thumb_path_B') and os.path.exists(st.session_state.thumb_path_B):
                    with col_tb:
                        st.image(st.session_state.thumb_path_B)
                        st.markdown(get_download_link(st.session_state.thumb_path_B, "Thumb_B.jpg", "Download B"), unsafe_allow_html=True)

                with st.expander("👁️ Review Scripts"):
                    st.text_area("AI Generated Script:", value=st.session_state.md_generated_script, height=150, disabled=True)
