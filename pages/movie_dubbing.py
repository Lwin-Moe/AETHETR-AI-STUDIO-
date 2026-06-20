import streamlit as st
import os
import time
import asyncio
import subprocess
import shutil
import random
import re
import textwrap
import ffmpeg
from google import genai
from groq import Groq
import openai

# ခွဲထုတ်ထားသော စက်ယန္တရား (Engines) များကို လှမ်းခေါ်ခြင်း
from utils.helpers import get_available_fonts, get_download_link, cleanup_temp_files
from core_engines.audio_tts import generate_tts
from core_engines.subtitle_sync import generate_whisper_sync_srt
from core_engines.video_render import render_premium_saas_video, VideoConfig, get_file_duration, download_video_from_url, extract_audio_fast, FFMPEG_BINARY

def render_movie_dubbing_studio(api_key_input, saved_gemini, ai_provider, groq_key_fc):
    """Movie Dubbing Studio ၏ UI အပြည့်အစုံနှင့် Workflow ကို မောင်းနှင်မည့် Function"""
    st.markdown('<div class="setting-panel"><h3>🎙️ Movie Dubbing & Recap Studio</h3>', unsafe_allow_html=True)
    st.markdown("နိုင်ငံခြား ဇာတ်လမ်းတိုများကို မြန်မာလို အလိုအလျောက် ဘာသာပြန်ပြီး အသံထည့်ပါ။ (Whisper Sync Enabled)")

    available_fonts = get_available_fonts()

    with st.sidebar:
        st.markdown("---")
        audio_engine_choice = st.radio("Voice Engine (Dubbing)", ["Edge-TTS (Default Free)", "Google Synergy TTS (Flash 3.1 Preview)", "ElevenLabs (Premium AI)", "TTSMaker (Free API)"])
        
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
        script_hook = st.checkbox("🪝 3-Second Viral Hook (အစချီ ဆွဲဆောင်မည်)", value=True, key="md_hook")
        script_curiosity = st.checkbox("🤯 Curiosity Gaps (စိတ်ဝင်စားမှု အရှိန်တင်မည်)", value=True, key="md_curiosity")
        script_tone = st.checkbox("🎭 Emotion & Tone (ဇာတ်ကောင်စရိုက် သွင်းမည်)", value=True, key="md_tone")
        script_cta = st.checkbox("💬 Call to Action (Commentခေါ်မည်)", value=False, key="md_cta")
        st.markdown("</div>", unsafe_allow_html=True)
        
        st.markdown("<div class='sub-box'>", unsafe_allow_html=True)
        st.markdown("<p style='font-weight: bold; color: #10b981; font-size: 16px;'>🎵 Audio Mixing & Auto-Ducking</p>", unsafe_allow_html=True)
        bgm_options = ["None (BGM မထည့်ပါ)"]
        bgm_files = [f for f in os.listdir("bgm_tracks") if f.endswith(".mp3")] if os.path.exists("bgm_tracks") else []
        if bgm_files:
            bgm_options.insert(1, "🤖 Auto (Random Select)")
            bgm_options.extend(bgm_files)
        selected_bgm = st.selectbox("🎼 Background Music", bgm_options, key="md_bgm")
        bgm_volume = st.slider("🔊 BGM Volume", 1, 50, 10, key="md_bgm_vol") / 100.0
        st.markdown("</div>", unsafe_allow_html=True)

    with col_in2:
        dynamic_options = ["Synergy Puck (Male)", "Synergy Aoede (Female)", "Synergy Charon (Male - Deep)"] if "Synergy" in audio_engine_choice else (["Adam (Male Deep)", "Rachel (Female)"] if "ElevenLabs" in audio_engine_choice else (["TTSMaker Male", "TTSMaker Female"] if "TTSMaker" in audio_engine_choice else ["ဇော်ဇော် (Male)", "အောင်အောင် (Deep)", "နှင်းနှင်း (Female)"]))
        voice_char = st.selectbox("Select Character Voice", dynamic_options, index=0)
        pitch_level = st.slider("🎙️ Voice Pitch (Frequency Adjust)", min_value=-30, max_value=30, value=0, step=5)
        fx_level = st.selectbox("🎧 Cinematic Voice FX", ["None", "🎙️ Epic Trailer Voice", "📻 Walkie-Talkie", "🏛️ Cinematic Reverb", "👹 Demon / Monster", "🤫 ASMR / Whisper", "🤖 Robot / Cyborg", "📞 Old Telephone", "⛰️ Deep Cave Echo", "🌊 Underwater / Muffled", "🔥 Deep & Energetic (Motivation)", "👻 Deep & Chilling (Horror)"])

        st.markdown("<div class='sub-box'>", unsafe_allow_html=True)
        st.markdown("<p style='font-weight: bold; color: #818cf8; font-size: 16px;'>📝 Subtitle Pro Settings</p>", unsafe_allow_html=True)
        if subtitle_mode in ["Both (Burn + SRT)", "Burn into Video"]:
            selected_font = st.selectbox("🔤 Font Style", available_fonts, index=0, key="md_font")
            sub_position = st.selectbox("📍 Position", ["Bottom", "Center", "Top"], key="md_sub_pos")
            sub_color = st.selectbox("🎨 Color", ["Yellow Text", "White Text", "Neon Green Text", "Red Text", "Gold Text"], key="md_sub_col")
            sub_size = st.slider("🔠 Font Size", 16, 50, 28, key="md_sub_size")
            sub_thickness = st.slider("✒️ Outline Thickness", 1.0, 5.0, 2.5, key="md_sub_thick")
            col_s1, col_s2 = st.columns(2)
            with col_s1:
                sub_bg = st.checkbox("🔲 Background Box", value=True, key="md_sub_bg")
                sub_short = st.checkbox("✂️ Short & Punchy (Hormozi)", value=True, key="md_sub_short")
        else:
            st.info("💡 Burn into Video ရွေးထားမှ ချိန်ညှိနိုင်ပါမည်။")
            selected_font, sub_position, sub_color, sub_size, sub_thickness, sub_bg, sub_short = "Padauk.ttf", "Bottom", "Yellow", 28, 2.5, True, False
        st.markdown("</div>", unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # 🚀 EXECUTION WORKFLOW
    if st.button("🚀 START ONE-CLICK WORKFLOW MONETIZE GENERATOR"):
        if not api_key_input:
            st.error("⚠️ AI API Key လိုအပ်ပါသည်။")
            return
        if not groq_key_fc:
            st.error("⚠️ Groq API Key လိုအပ်ပါသည်။ (Whisper Alignment အတွက်မဖြစ်မနေလိုပါသည်)")
            return
        elif not uploaded_file and not video_url:
            st.error("⚠️ ဗီဒီယိုဖိုင်သို့မဟုတ် Link ထည့်ပေးပါ။")
            return

        st.session_state.render_success = False
        cleanup_temp_files()

        run_id = str(int(time.time()))
        v_final = f"AETHER_RECAP_FINAL_{run_id}.mp4"
        st.session_state.final_video_path = v_final
        v_input, a_extracted, a_generated, srt_final = "input_temp.mp4", "temp_extracted.mp3", "voice_temp.wav", "subtitles.srt"
        pbar = st.progress(0, text="🚀 အလုပ်စတင်နေပါပြီ...")
        
        # --- [အဆင့် ၁/၆] Video Fetching ---
        with st.spinner("⏳ [အဆင့်၁/၆] ဗီဒီယို ဖိုင်အားစနစ်ထဲသို့ ဆွဲသွင်းနေပါသည်..."):
            pbar.progress(10, text="📥 [အဆင့် ၁/၆] ဗီဒီယိုဆွဲယူနေပါသည်...")
            try:
                if uploaded_file:
                    with open(v_input, "wb") as f: f.write(uploaded_file.read())
                else: 
                    download_video_from_url(video_url, v_input)
            except Exception as dl_err:
                st.error(str(dl_err))
                st.stop()
            extract_audio_fast(v_input, a_extracted)

        # --- [အဆင့် ၂/၆] AI Script & Tags ---
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
                            
                            # 🔴 GOLDEN RULE UPDATE: No More SRT Timestamps Generation from Gemini
                            gemini_prompt = f"Watch the provided video carefully. Invent a completely ORIGINAL, highly engaging storytelling recap in Burmese. Do NOT just translate. STRICT RULES: 1. Include Synergy Audio Tags like [pause=1.0], [excited]. 2. NO ENGLISH TRANSLITERATION. 3. Output pure text narrative. {extra_rules}" if "Original" in recap_mode else f"Listen to the audio. Translate and adapt the text into highly engaging, natural spoken Burmese. STRICT RULES: 1. Include Synergy Audio Tags like [pause=1.0], [excited]. 2. NO ENGLISH TRANSLITERATION. 3. Output pure text narrative. {extra_rules}"
                            
                            response = client.models.generate_content(model="gemini-2.5-flash", contents=[media_file, gemini_prompt])
                            raw_output_text = response.text.strip()
                            client.files.delete(name=media_file.name)
                            success_gemini = True; break
                        except Exception as e: 
                            last_err = str(e); continue
                    if not success_gemini: raise Exception(f"Gemini API Error: {last_err}")
                else:
                    client = Groq(api_key=api_key_input) if "Groq" in ai_provider else openai
                    if "Groq" in ai_provider:
                        with open(a_extracted, "rb") as file: transcription = client.audio.translations.create(file=(a_extracted, file.read()), model="whisper-large-v3", response_format="verbose_json")
                        tsrt = "".join([f"{i}\n00:00:00,000 --> 00:00:10,000\n{seg['text']}\n\n" for i, seg in enumerate(transcription.get('segments', []), 1)]) if isinstance(transcription, dict) else str(transcription)
                    else:
                        openai.api_key = api_key_input
                        with open(a_extracted, "rb") as file: tsrt = openai.audio.translations.create(model="whisper-1", file=file, response_format="srt")

                    base_prompt = f"Translate and adapt the text into engaging Burmese. Add audio tags. Output pure text narrative. {extra_rules}"
                    comp = client.chat.completions.create(model="llama-3.3-70b-versatile" if "Groq" in ai_provider else ("gpt-5.5-pro" if "5.5" in ai_provider else "gpt-4o"), messages=[{"role": "user", "content": f"{base_prompt} --- TEXT --- {tsrt}"}])
                    raw_output_text = comp.choices[0].message.content

                title_match = re.search(r'\[TITLE:\s*(.*?)\]', raw_output_text, re.IGNORECASE)
                tags_match = re.search(r'\[TAGS:\s*(.*?)\]', raw_output_text, re.IGNORECASE)
                st.session_state.viral_title = re.sub(r'[\[\]]', '', title_match.group(1)).strip() if title_match else "Viral Movie Recap"
                st.session_state.viral_tags = tags_match.group(1).strip() if tags_match else "#movierecap #myanmar"

                clean_raw_text = re.sub(r'\[TITLE:.*?\]', '', raw_output_text, flags=re.IGNORECASE)
                clean_raw_text = re.sub(r'\[TAGS:.*?\]', '', clean_raw_text, flags=re.IGNORECASE).strip()
                st.session_state.generated_script = clean_raw_text

                # Thumbnail generation block
                try:
                    t_A = min(get_file_duration(v_input)*0.2, 10)
                    t_B = min(get_file_duration(v_input)*0.5, 20)
                    for thumb_suffix, t_val in [("A", t_A), ("B", t_B)]:
                        thumb_name = f"thumb_{thumb_suffix}_{run_id}.jpg"
                        try:
                            stream = ffmpeg.input(v_input, ss=t_val)
                            if cb_thumb_text:
                                wrapped_lines = textwrap.wrap(st.session_state.viral_title, width=25)
                                max_l = max(len(l) for l in wrapped_lines) if wrapped_lines else 0
                                c_text = "\n".join(l.center(max_l, " ") for l in wrapped_lines)
                                with open("thumb_text.txt", "w", encoding="utf-8") as tf: tf.write(c_text)
                                if os.path.exists(selected_font): 
                                    stream = ffmpeg.filter(stream.video, 'drawtext', textfile='thumb_text.txt', fontfile=selected_font.replace('\\','/'), fontcolor='white', fontsize=65, x='(w-text_w)/2', y='(h-text_h)/2', box=1, boxcolor='red@0.9', boxborderw=20, borderw=3, bordercolor='black', line_spacing=15, text_align='C')
                            ffmpeg.output(stream, thumb_name, vframes=1).overwrite_output().run(cmd=FFMPEG_BINARY, quiet=True)
                        except Exception: pass
                        if thumb_suffix == "A" and os.path.exists(thumb_name): st.session_state.thumb_path_A = thumb_name
                        elif thumb_suffix == "B" and os.path.exists(thumb_name): st.session_state.thumb_path_B = thumb_name
                except Exception: pass
            except Exception as e: 
                st.error(f"Logic Error: {e}")
                st.stop()

        # --- [အဆင့် ၃/၆] AI Voice Generation ---
        with st.spinner(f"⏳ [အဆင့်၃/၆] AI Voice Over ထုတ်လုပ်နေပါသည်..."):
            pbar.progress(50, text="🎙️ [အဆင့် ၃/၆] အသံသရုပ်ဆောင်ဖန်တီးနေပါသည်...")
            try: 
                asyncio.run(generate_tts(
                    clean_raw_text, voice_char, a_generated, engine=audio_engine_choice, 
                    ttsmaker_key=key_ttsmaker, eleven_key=eleven_key_input, custom_eleven_id=custom_eleven_id, 
                    gemini_key=synergy_key if synergy_key else api_key_input, pitch=pitch_level, voice_fx=fx_level
                ))
            except Exception as e: 
                st.error(f"အသံထုတ်လုပ်ခြင်းမအောင်မြင်ပါ: {e}")
                st.stop()

        # --- [အဆင့် ၄/၆] Whisper Forced Alignment ---
        with st.spinner("⏳ [အဆင့်၄/၆] Whisper ဖြင့် အသံနှင့် စာတန်းကို တိကျစွာ ချိန်ညှိနေပါသည်..."):
            pbar.progress(70, text="📝 [အဆင့် ၄/၆] Whisper Word-level Sync ပြုလုပ်နေပါသည်...")
            try:
                success_sync, parsed_timestamps, err_sync = generate_whisper_sync_srt(a_generated, clean_raw_text, groq_key_fc, sub_short)
                if not success_sync:
                    st.error(f"❌ Whisper Sync Error: {err_sync}")
                    st.stop()
            except Exception as e:
                st.error(f"❌ Alignment Failed: {e}")
                st.stop()

        # --- [အဆင့် ၅/၆] Final Video Merge ---
        with st.spinner("⏳ [အဆင့်၅/၆] ဗီဒီယိုနှင့် စာတန်းထိုးပေါင်းစပ်နေပါသည်..."):
            pbar.progress(85, text="🎬 [အဆင့် ၅/၆] Master Video Rendering ပြုလုပ်နေပါသည်...")
            
            # 🔴 ARCHITECTURE UPGRADE: Sending VideoConfig object
            render_cfg = VideoConfig(
                ratio=video_ratio, use_bypass=cb_bypass, use_blur=cb_blur, watermark=watermark_text, 
                subtitle_mode=subtitle_mode, use_mirror=cb_mirror, use_color=cb_color, use_grain=cb_grain, 
                use_fps=cb_fps, sub_position=sub_position, sub_color=sub_color, sub_size=sub_size, 
                sub_thickness=sub_thickness, sub_bg=sub_bg, use_freeze=cb_freeze, logo_path=uploaded_logo, 
                font_path=selected_font
            )
            
            success, err_msg = render_premium_saas_video(v_input, a_generated, parsed_timestamps, v_final, render_cfg)
            if not success: 
                st.error(f"❌ Render Failure: {err_msg}")
                st.stop()

        # --- [အဆင့် ၆/၆] BGM Mixing ---
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
        if success: 
            st.session_state.render_success = True

    # 🚀 OUTPUT DASHBOARD
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
                if os.path.exists("subtitles.srt"): 
                    st.markdown(get_download_link("subtitles.srt", "Aether_Subs.srt", "Download Subtitles (.SRT)"), unsafe_allow_html=True)
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

            with st.expander("👁️ Original Transcript", expanded=False): 
                st.text_area("မူရင်းစာသား:", value=st.session_state.original_transcript, height=150, disabled=True)
            with st.expander("🇲🇲 AI Generated Script", expanded=True): 
                st.text_area("AI မှရေးသားထားသော ဇာတ်ညွှန်း:", value=st.session_state.generated_script, height=250, disabled=True)
            st.markdown('</div>', unsafe_allow_html=True)
