import streamlit as st
import os
import time
import subprocess
import shutil
import re
import textwrap
import urllib.parse
import requests
import ffmpeg
from google import genai
from groq import Groq
import openai

# ခွဲထုတ်ထားသော စက်ယန္တရား (Engines) များကို လှမ်းခေါ်ခြင်း
from utils.helpers import get_available_fonts, get_download_link, cleanup_temp_files, load_key
from core_engines.subtitle_sync import parse_and_save_real_srt
from core_engines.video_render import render_premium_saas_video, VideoConfig, get_file_duration, download_video_from_url, extract_audio_fast, FFMPEG_BINARY

def generate_hybrid_thumbnail(bg_image_path, output_path, title_text, font_path="Padauk.ttf"):
    try:
        wrapped_text = "\n".join(line.center(max(len(l) for l in textwrap.wrap(title_text, 25)), " ") for line in (textwrap.wrap(title_text, 25) or [title_text]))
        with open("thumb_custom_text.txt", "w", encoding="utf-8") as f: f.write(wrapped_text)
        
        video = ffmpeg.input(bg_image_path)
        video = ffmpeg.filter(video, 'drawbox', x=0, y=0, w='iw', h='ih', color='black@0.4', thickness='fill')
        video = ffmpeg.filter(video, 'drawtext', textfile='thumb_custom_text.txt', fontfile=font_path.replace('\\', '/'), fontcolor='gold', fontsize=75, bordercolor='black', borderw=4, box=1, boxcolor='black@0.6', boxborderw=20, x='(w-text_w)/2', y='(h-text_h)/2', line_spacing=15, text_align='C')
        ffmpeg.output(video, output_path, vframes=1, qscale=2).overwrite_output().run(cmd=FFMPEG_BINARY, quiet=True)
        return True
    except Exception: return False

def render_translation_studio(api_key_input, saved_gemini, ai_provider, groq_key_fc):
    st.markdown('<div class="setting-panel"><h3>🌍 Global Auto-Translation Studio</h3>', unsafe_allow_html=True)
    st.markdown("Any Language ဗီဒီယိုများကို မိမိနှစ်သက်ရာ ဘာသာစကားသို့ သဘာဝကျကျ အလိုအလျောက် စာတန်းထိုး ဘာသာပြန်ပါ။ (K-Drama, Douyin, Rednote)")

    available_fonts = get_available_fonts()
    
    if "ts_step1_done" not in st.session_state: st.session_state.ts_step1_done = False
    if "ts_original_srt" not in st.session_state: st.session_state.ts_original_srt = ""
    if "ts_translated_srt" not in st.session_state: st.session_state.ts_translated_srt = ""
    if "ts_viral_title" not in st.session_state: st.session_state.ts_viral_title = ""
    if "ts_bg_image" not in st.session_state: st.session_state.ts_bg_image = None
    if "ts_input_video" not in st.session_state: st.session_state.ts_input_video = "ts_input.mp4"
    if "ts_preview_frame" not in st.session_state: st.session_state.ts_preview_frame = "ts_preview.jpg"

    with st.sidebar:
        st.markdown("---")
        st.markdown("<b>🌐 Translation Settings</b>", unsafe_allow_html=True)
        target_lang = st.selectbox("Target Language", ["Myanmar (မြန်မာ)", "English", "Thai (ไทย)", "Indonesian (ไทย)"])
        
        trans_tone = st.selectbox("🎭 Translation Style", ["Natural & Conversational (သဘာဝကျကျ)", "Gen-Z / Slang (လူငယ်သုံးစကား)", "Formal / Direct (တိုက်ရိုက်ဘာသာပြန်)"])
        
        st.markdown("<b>🎥 Copyright Bypass Options</b>", unsafe_allow_html=True)
        video_ratio = st.selectbox("Crop Ratio", ["Original", "9:16 (TikTok/Shorts)", "16:9 (YouTube)"])
        cb_bypass = st.checkbox("🔍 Smart Zoom", value=True)
        cb_mirror = st.checkbox("🪞 Mirror Effect", value=False)
        cb_color = st.checkbox("🎨 Color Tweaks", value=False)
        cb_fps = st.checkbox("🎬 Cinematic 24 FPS", value=False)
        
        st.markdown("<b>🎬 Visual & Watermark</b>", unsafe_allow_html=True)
        ts_blur = st.checkbox("⬛ Hardcoded Subtitle Blocker (မူရင်းစာတန်းကိုဖုံးမည်)", value=True)
        use_text_watermark = st.checkbox("✍️ Add Text Watermark", value=False)
        watermark_text = st.text_input("Text Watermark", "") if use_text_watermark else ""
        uploaded_logo = st.file_uploader("🖼️ Add Logo Image", type=["png", "jpg"])

        st.markdown("<b>📝 Subtitle Output Settings</b>", unsafe_allow_html=True)
        ts_font = st.selectbox("🔤 Font Style", available_fonts, index=0)
        ts_sub_pos = st.selectbox("📍 Position", ["Bottom", "Center", "Top"])
        ts_sub_col = st.selectbox("🎨 Color", ["Yellow Text", "White Text", "Neon Green Text"])
        ts_sub_size = st.slider("🔠 Font Size", 16, 50, 28)
        ts_sub_mode = st.radio("Output Mode", ["Both (Burn + SRT)", "Export SRT File Only", "Burn into Video", "No Subtitle"])

    col_in1, col_in2 = st.columns(2)
    with col_in1:
        st.markdown("<div class='sub-box'>", unsafe_allow_html=True)
        st.markdown("<p style='font-weight: bold; color: #38bdf8;'>📺 Media Acquisition</p>", unsafe_allow_html=True)
        video_url = st.text_input("🔗 Video URL (Douyin, Rednote, YT, FB)", placeholder="https://...")
        uploaded_file = st.file_uploader("📥 OR Upload Video (MP4/WEBM)", type=["mp4", "webm", "m4v"])
        
        st.markdown("<p style='font-weight: bold; color: #10b981; margin-top:15px;'>📖 Custom Dictionary (Optional)</p>", unsafe_allow_html=True)
        custom_dict = st.text_area("အမည်နာမ မှတ်ဉာဏ်များ (ဥပမာ: Naruto=နာရူတို)", placeholder="Gojo=ဂိုဂျို\nOppa=အိုပါး", height=80)
        st.markdown("</div>", unsafe_allow_html=True)

    with col_in2:
        st.markdown("<div class='sub-box'>", unsafe_allow_html=True)
        st.markdown("<p style='font-weight: bold; color: #c084fc;'>🖼️ Smart Thumbnail Settings</p>", unsafe_allow_html=True)
        gen_thumb = st.checkbox("🎨 Generate AI Art Background (Pollinations)", value=True)
        custom_thumb_title = st.text_input("✍️ Custom Title (Optional)", placeholder="AI Title အစား ကိုယ်တိုင်ပေးလိုပါက ထည့်ပါ")
        st.markdown("<small style='color:gray;'>* AI Art ပေါ်တွင် ရွှေရောင်စာတန်းကို FFmpeg ဖြင့် အလိုအလျောက် ရိုက်နှိပ်ပေးပါမည်။</small>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("---")

    # ==========================================
    # 🚀 STEP 1: TRANSLATION & ASSET GENERATION
    # ==========================================
    if st.button("🚀 STEP 1: Generate Translation & Assets"):
        if not api_key_input: st.error("⚠️ API Key လိုအပ်ပါသည်။"); return
        if not uploaded_file and not video_url: st.error("⚠️ Media ထည့်ပေးပါ။"); return
        
        cleanup_temp_files()
        st.session_state.ts_step1_done = False
        pbar = st.progress(0, text="📥 ဗီဒီယို ပြင်ဆင်နေပါသည်...")
        v_input, a_out = "ts_input.mp4", "ts_audio.mp3"

        try:
            if uploaded_file:
                with open(v_input, "wb") as f: f.write(uploaded_file.read())
            else: download_video_from_url(video_url, v_input)
            extract_audio_fast(v_input, a_out)
            
            # Extract preview frame
            ffmpeg.input(v_input, ss=min(get_file_duration(v_input)/2, 5)).output(st.session_state.ts_preview_frame, vframes=1).overwrite_output().run(cmd=FFMPEG_BINARY, quiet=True)
        except Exception as e: st.error(str(e)); st.stop()

        pbar.progress(30, text="📝 မူရင်းဘာသာစကားကို နားထောင်နေပါသည်...")
        try:
            whisper_key = groq_key_fc if groq_key_fc else (load_key("GROQ_API_KEY") or api_key_input)
            if whisper_key.startswith("gsk_"):
                client_audio = Groq(api_key=whisper_key)
                with open(a_out, "rb") as f: transcription = client_audio.audio.transcriptions.create(file=(a_out, f.read()), model="whisper-large-v3", response_format="verbose_json")
                raw_srt = ""
                segments = transcription.segments if hasattr(transcription, 'segments') else transcription.get('segments', [])
                for i, segment in enumerate(segments, 1):
                    start = segment['start'] if isinstance(segment, dict) else segment.start
                    end = segment['end'] if isinstance(segment, dict) else segment.end
                    text = segment['text'] if isinstance(segment, dict) else segment.text
                    def format_srt_time(seconds):
                        h = int(seconds // 3600); m = int((seconds % 3600) // 60); s = int(seconds % 60); ms = int((seconds % 1) * 1000)
                        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
                    raw_srt += f"{i}\n{format_srt_time(start)} --> {format_srt_time(end)}\n{text.strip()}\n\n"
                st.session_state.ts_original_srt = raw_srt
            else:
                openai.api_key = whisper_key
                with open(a_out, "rb") as f: transcript = openai.audio.transcriptions.create(model="whisper-1", file=f, response_format="srt")
                st.session_state.ts_original_srt = str(transcript)
        except Exception as e: st.error(f"Whisper Error: {e}"); st.stop()

        pbar.progress(50, text=f"🌍 {target_lang} သို့ ဘာသာပြန်နေပါသည်...")
        try:
            dict_prompt = f"\n[CRITICAL]: Apply this custom dictionary EXACTLY. Do not translate these names:\n{custom_dict}" if custom_dict.strip() else ""
            
            tone_instructions = "Translate literally word-by-word."
            if "Natural" in trans_tone:
                tone_instructions = "Translate contextually and naturally. Use natural everyday spoken language (e.g., instead of translating 'What's up' literally, use the natural greeting equivalent in the target language). Avoid sounding like a robot."
            elif "Gen-Z" in trans_tone:
                tone_instructions = "Translate using modern internet slang, Gen-Z expressions, and trendy social media language. Make it highly engaging for TikTok/Shorts audience."

            translation_prompt = f"""You are an expert Localizer and Subtitle Translator. Translate the following SRT file to {target_lang}.
            RULES: 
            1. Maintain the EXACT SRT timestamp format and numbering. DO NOT break the SRT structure.
            2. {tone_instructions}
            3. Do NOT add any extra text, notes, or explanations outside the SRT format.{dict_prompt}
            4. At the very end of your response, add a viral Title on a new line EXACTLY like this: [TITLE: Your Viral Title]"""

            raw_translation = ""
            if "Gemini" in ai_provider:
                client = genai.Client(api_key=api_key_input.split(",")[0])
                res = client.models.generate_content(model="gemini-2.5-flash", contents=[translation_prompt, f"--- SRT ---\n{st.session_state.ts_original_srt}"])
                raw_translation = res.text
            else:
                client_llm = Groq(api_key=api_key_input) if "Groq" in ai_provider else openai
                comp = client_llm.chat.completions.create(model="llama-3.3-70b-versatile" if "Groq" in ai_provider else "gpt-5.5-pro", messages=[{"role": "user", "content": translation_prompt + "\n\n" + st.session_state.ts_original_srt}])
                raw_translation = comp.choices[0].message.content

            t_match = re.search(r'\[TITLE:\s*(.*?)\]', raw_translation, re.IGNORECASE)
            st.session_state.ts_viral_title = re.sub(r'[\[\]]', '', t_match.group(1)).strip() if t_match else "Viral Video"
            st.session_state.ts_translated_srt = re.sub(r'\[TITLE:.*?\]', '', raw_translation, flags=re.IGNORECASE).strip()
        except Exception as e: st.error(f"Translation Error: {e}"); st.stop()

        if gen_thumb:
            pbar.progress(80, text="🎨 Thumbnail ပုံရိပ် ဖန်တီးနေပါသည်...")
            try:
                if "Gemini" in ai_provider:
                    p_res = genai.Client(api_key=api_key_input.split(",")[0]).models.generate_content(model="gemini-2.5-flash", contents=[f"Create a highly detailed, cinematic English image generation prompt (max 30 words) describing this title: {st.session_state.ts_viral_title}. Output ONLY the prompt."])
                    img_prompt = p_res.text.strip()
                else:
                    img_prompt = f"Cinematic epic scene for {st.session_state.ts_viral_title}, 8k resolution, highly detailed"

                encoded_prompt = urllib.parse.quote(img_prompt)
                url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1280&height=720&nologo=true"
                res = requests.get(url, timeout=60)
                if res.status_code == 200:
                    bg_path = "ts_bg_image.jpg"
                    with open(bg_path, "wb") as f: f.write(res.content)
                    st.session_state.ts_bg_image = bg_path
            except Exception: pass

        st.session_state.ts_step1_done = True
        pbar.progress(100, text="✅ အဆင့် (၁) ပြီးစီးပါပြီ!")

    # ==========================================
    # 🎬 STEP 2: REVIEW & FINAL RENDER
    # ==========================================
    if st.session_state.ts_step1_done:
        st.markdown("<hr><h3 style='color: #38bdf8;'>🛠️ Step 2: Review & Final Render</h3>", unsafe_allow_html=True)
        
        col_r1, col_r2 = st.columns(2)
        with col_r1:
            st.markdown("**📝 Interactive SRT Editor**")
            edited_srt = st.text_area("စာတန်းထိုးများကို စိတ်ကြိုက် ဝင်ရောက်ပြင်ဆင်နိုင်ပါသည်:", value=st.session_state.ts_translated_srt, height=400)
            
        with col_r2:
            st.markdown("**👁️ Subtitle Blocker Settings**")
            if ts_blur:
                blur_height = st.slider("⬛ Black Bar အမြင့် (px)", 50, 400, 100, help="မူရင်းစာတန်းကို ဖုံးကွယ်မည့် အနက်ရောင်ဘား၏ အမြင့်ကို ချိန်ညှိပါ")
                # 🔴 OpenCV အစား ပေါ့ပါးသော PIL (Pillow) ဖြင့် ပြောင်းလဲရေးသားထားသည်
                if os.path.exists(st.session_state.ts_preview_frame):
                    from PIL import Image, ImageDraw
                    try:
                        img = Image.open(st.session_state.ts_preview_frame).convert("RGBA")
                        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
                        draw = ImageDraw.Draw(overlay)
                        # Black box with 80% opacity (alpha 200/255)
                        draw.rectangle([0, img.height - blur_height, img.width, img.height], fill=(0, 0, 0, 200))
                        img_new = Image.alpha_composite(img, overlay)
                        st.image(img_new, caption="Live Blur Preview", use_column_width=True)
                    except Exception:
                        st.image(st.session_state.ts_preview_frame, caption="Preview")
            else:
                blur_height = 0
                st.info("Subtitle Blocker ပိတ်ထားပါသည်။")

            st.markdown("**🖼️ Thumbnail Preview**")
            final_title = custom_thumb_title if custom_thumb_title.strip() else st.session_state.ts_viral_title
            st.success(f"Title: {final_title}")
            if st.session_state.ts_bg_image and os.path.exists(st.session_state.ts_bg_image):
                st.image(st.session_state.ts_bg_image, caption="AI Background")

        if st.button("🎬 RENDER MASTER VIDEO", type="primary"):
            run_id = str(int(time.time()))
            v_final = f"TRANSLATED_FINAL_{run_id}.mp4"
            thumb_final = f"THUMB_FINAL_{run_id}.jpg"
            st.session_state.final_video_path = v_final
            
            with st.spinner("⏳ Master Video ပေါင်းစပ်နေပါသည်..."):
                try:
                    parsed_timestamps, _ = parse_and_save_real_srt(edited_srt, "subtitles.srt", use_fade=False)
                    
                    render_cfg = VideoConfig(
                        ratio=video_ratio, use_bypass=cb_bypass, subtitle_mode=ts_sub_mode, 
                        sub_position=ts_sub_pos, sub_color=ts_sub_col, sub_size=ts_sub_size, 
                        sub_thickness=2.5, sub_bg=False, font_path=ts_font, use_fps=cb_fps, 
                        use_mirror=cb_mirror, use_color=cb_color, watermark=watermark_text, logo_path=uploaded_logo
                    )

                    audio = ffmpeg.input("ts_input.mp4").audio
                    video = ffmpeg.input("ts_input.mp4").video
                    
                    if video_ratio != "Original":
                        v_w, v_h = (720, 1280) if "9:16" in video_ratio else (1280, 720)
                        video = ffmpeg.filter(video, 'scale', v_w, v_h, force_original_aspect_ratio='increase').filter('crop', v_w, v_h)
                    
                    if cb_bypass: video = ffmpeg.filter(video, 'scale', '2*trunc(iw*1.08/2)', '2*trunc(ih*1.08/2)').filter('crop', 'iw/1.08', 'ih/1.08')
                    if cb_mirror: video = ffmpeg.filter(video, 'hflip')
                    
                    if ts_blur and blur_height > 0:
                        video = ffmpeg.filter(video, 'drawbox', x=0, y=f'ih-{blur_height}', w='iw', h=blur_height, color='black@0.9', thickness='fill')

                    if render_cfg.subtitle_mode in ["Burn into Video", "Both (Burn + SRT)"] and parsed_timestamps:
                        wrap_width = 25 if "9:16" in render_cfg.ratio else 45
                        safe_font_path = render_cfg.font_path.replace('\\', '/')

                        for i, (start, end, text) in enumerate(parsed_timestamps):
                            wrapped_lines = textwrap.wrap(text, width=wrap_width)
                            if not wrapped_lines: wrapped_lines = [text]
                            max_len = max(len(line) for line in wrapped_lines)
                            centered_text = "\n".join(line.center(max_len, " ") for line in wrapped_lines)
                            txt_filename = f"temp_sub_{i}.txt"
                            with open(txt_filename, "w", encoding="utf-8") as tf: tf.write(centered_text)

                            if "Center" in render_cfg.sub_position: y_expr = "(h-text_h)/2"
                            elif "Top" in render_cfg.sub_position: y_expr = "150"
                            else: y_expr = "h-text_h-100"

                            c_str = "yellow" if "Yellow" in render_cfg.sub_color else ("green" if "Green" in render_cfg.sub_color else "white")
                            video = ffmpeg.filter(video, 'drawtext', textfile=txt_filename, fontfile=safe_font_path, fontcolor=c_str, fontsize=render_cfg.sub_size, bordercolor='black', borderw=2.5, x='(w-text_w)/2', y=y_expr, line_spacing=20, text_align='C', enable=f'between(t,{start},{end})')

                    out = ffmpeg.output(video, audio, v_final, vcodec='libx264', pix_fmt='yuv420p', acodec='aac', preset='superfast', crf=23, t=get_file_duration("ts_input.mp4"))
                    out.overwrite_output().run(cmd=FFMPEG_BINARY, quiet=True)
                    st.session_state.render_success = True

                    if st.session_state.ts_bg_image and gen_thumb:
                        generate_hybrid_thumbnail(st.session_state.ts_bg_image, thumb_final, final_title, ts_font)
                        st.session_state.thumb_path_A = thumb_final

                except Exception as e:
                    st.error(f"Render Error: {e}")

        if st.session_state.render_success:
            st.balloons()
            st.success("🎉 ဘာသာပြန် Video အောင်မြင်စွာ ထွက်လာပါပြီ!")
            col_o1, col_o2 = st.columns(2)
            with col_o1:
                st.video(st.session_state.final_video_path)
                st.markdown(get_download_link(st.session_state.final_video_path, "Translated_Video.mp4", "📥 Download Video"), unsafe_allow_html=True)
                if ts_sub_mode != "No Subtitle" and os.path.exists("subtitles.srt"):
                    st.markdown(get_download_link("subtitles.srt", "Translated_Subs.srt", "📥 Download Subtitles (.SRT)"), unsafe_allow_html=True)
            with col_o2:
                if st.session_state.thumb_path_A and os.path.exists(st.session_state.thumb_path_A):
                    st.image(st.session_state.thumb_path_A, caption="Custom AI Thumbnail")
                    st.markdown(get_download_link(st.session_state.thumb_path_A, "Thumbnail.jpg", "📥 Download Thumbnail"), unsafe_allow_html=True)
