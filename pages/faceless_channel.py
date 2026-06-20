import streamlit as st
import os
import time
import asyncio
import subprocess
import shutil
import random
import re
import urllib.parse
import requests
from google import genai

# ခွဲထုတ်ထားသော စက်ယန္တရား (Engines) များကို လှမ်းခေါ်ခြင်း
from utils.helpers import get_available_fonts, get_download_link, cleanup_temp_files
from core_engines.ai_writer import generate_faceless_script, predict_virality_score
from core_engines.audio_tts import generate_tts
from core_engines.subtitle_sync import generate_whisper_sync_srt
from core_engines.video_render import render_premium_saas_video, VideoConfig, generate_professional_thumbnail, get_file_duration, FFMPEG_BINARY

def render_faceless_studio(api_key_input, saved_gemini, groq_key_fc):
    st.markdown('<div class="setting-panel"><h3>👻 Fully-Automated Faceless Channel Studio</h3>', unsafe_allow_html=True)
    st.markdown("TikTok, FB Reels များအတွက် Reddit Stories, Horror ပုံပြင်များကိုဖန်တီးပါ။ (Pro Features Enabled)")
    
    available_fonts = get_available_fonts()
    
    with st.sidebar:
        st.markdown("---")
        st.markdown("<b>🎨 Visual & Niche Settings</b>", unsafe_allow_html=True)
        fc_niche = st.selectbox("Select Niche", ["👻 Horror / Creepypasta", "💔 Reddit Relationship Drama", "🧠 Dark Psychology", "💡 Fun Facts / Trivia", "🚀 Motivation / Mindset", "📜 Ancient History / Myths"], key="fc_niche_select")
        fc_ratio = st.selectbox("Video Ratio", ["9:16 (TikTok/Shorts)", "16:9 (YouTube)"], key="fc_ratio")
        fc_duration = st.slider("⏱️ Story Duration (Minutes)", 1, 10, 3)
        fc_thumb_style = st.selectbox("🖼️ Thumbnail Style", ["🔥 Viral TikTok Style", "🎬 Cinematic Movie Poster", "👻 Horror / Mystery", "💎 Premium / Luxury", "⚡ Clean / Minimal"], key="fc_thumb_style")

        st.markdown("---")
        st.markdown("<b>🎙️ Voice & Audio Settings</b>", unsafe_allow_html=True)
        fc_audio_engine = st.radio("Voice Engine", ["Edge-TTS (Free)", "Google Synergy TTS (API)"], key="fc_engine")
        fc_synergy_key = ""
        if "Synergy" in fc_audio_engine:
            fc_synergy_key = st.text_input("Synergy TTS Key", type="password", value=saved_gemini, key="fc_syn")
        fc_voice_char = st.selectbox("Voice Model", ["Synergy Puck (Male)", "Synergy Charon (Deep)"] if "Synergy" in fc_audio_engine else ["ဇော်ဇော် (Male)", "အောင်အောင် (Deep)", "နှင်းနှင်း (Female)"], key="fc_voice")
        
        # 🔴 PRO FEATURE 1: Smart Niche-to-FX Mapping (အလိုအလျောက် ညှိနှိုင်းပေးမည့်စနစ်)
        niche_fx_map = {
            "👻 Horror / Creepypasta": "👻 Deep & Chilling (Horror)",
            "💔 Reddit Relationship Drama": "🎭 Multi-Persona (Auto-Pitch)",
            "🧠 Dark Psychology": "🌀 Spatial 3D Audio (Pan L/R)",
            "💡 Fun Facts / Trivia": "None",
            "🚀 Motivation / Mindset": "🔥 Deep & Energetic (Motivation)",
            "📜 Ancient History / Myths": "🏛️ Cinematic Reverb"
        }
        fx_options = ["None", "👹 Demon / Horror", "🤫 ASMR / Whisper", "🎙️ Epic Trailer", "🤖 Robot / Cyborg", "📞 Old Telephone", "🏛️ Cinematic Reverb", "⛰️ Deep Cave Echo", "🌊 Underwater / Muffled", "🔥 Deep & Energetic (Motivation)", "👻 Deep & Chilling (Horror)", "🌀 Spatial 3D Audio (Pan L/R)", "🎭 Multi-Persona (Auto-Pitch)"]
        default_fx = niche_fx_map.get(fc_niche, "None")
        default_index = fx_options.index(default_fx) if default_fx in fx_options else 0
        fc_fx = st.selectbox("Voice FX (Effect)", fx_options, index=default_index, key="fc_fx")
        
        # 🔴 PRO FEATURE 3: Auto-SFX Engine Toggle
        fc_use_sfx = st.checkbox("🎬 Auto-SFX Engine (Cinematic Impacts & Whooshes)", value=True, help="sfx/impact.mp3 နှင့် sfx/whoosh.mp3 ဖိုင်များ လိုအပ်ပါသည်။")

        st.markdown("<b>📝 Subtitle Pro Settings</b>", unsafe_allow_html=True)
        fc_selected_font = st.selectbox("🔤 Font Style", available_fonts, index=0, key="fc_font")
        fc_sub_position = st.selectbox("📍 Position", ["Center", "Bottom", "Top"], index=0, key="fc_sub_pos")
        fc_sub_color = st.selectbox("🎨 Color", ["Yellow Text", "White Text", "Neon Green Text", "Red Text", "Gold Text"], index=0, key="fc_sub_col")
        fc_sub_size = st.slider("🔠 Font Size", 16, 50, 28, key="fc_sub_size")
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

        fc_custom_topic = ""
        fc_script_hook, fc_script_curiosity, fc_script_tone, fc_script_cta = False, False, False, False
        if "Auto" in fc_script_mode:
            fc_custom_topic = st.text_input("💡 ဇာတ်လမ်း အကြောင်းအရာ (Optional):", placeholder="ဥပမာ - သရဲဘုံကျောင်း, ပင်လယ်ဓားပြ...", key="fc_topic")
            st.markdown("<br><p style='color:#38bdf8; font-weight:bold;'>✍️ AI Storytelling Rules</p>", unsafe_allow_html=True)
            fc_script_hook = st.checkbox("🪝 3-Second Viral Hook (အစချီ ဆွဲဆောင်မည်)", value=True, key="fc_hook")
            fc_script_curiosity = st.checkbox("🤯 Curiosity Gaps (စိတ်ဝင်စားမှု အရှိန်တင်မည်)", value=True, key="fc_curiosity")
            fc_script_tone = st.checkbox("🎭 Emotion & Tone (ဇာတ်ကောင်စရိုက် သွင်းမည်)", value=True, key="fc_tone")
            fc_script_cta = st.checkbox("💬 Call to Action (Commentခေါ်မည်)", value=False, key="fc_cta")

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
            st.error("⚠️ Google Gemini API Key ထည့်သွင်းပေးပါ။")
            return
        elif "Manual" in fc_script_mode and not fc_manual_script.strip():
            st.error("⚠️ Manual ဇာတ်ညွှန်းထည့်သွင်းပေးပါ။")
            return
        elif "Upload" in fc_visual_mode and not fc_uploaded_images:
            st.error("⚠️ အနည်းဆုံးပုံ (၁) ပုံ Upload တင်ပေးပါ။")
            return

        st.session_state.render_success = False
        cleanup_temp_files()
        run_id = str(int(time.time()))
        v_final = f"FACELESS_FINAL_{run_id}.mp4"
        st.session_state.final_video_path = v_final
        pbar = st.progress(0, text="🚀 အလိုအလျောက် ဖန်တီးမှုစတင်နေပါပြီ...")
        
        fc_story_text = ""
        
        # --- [အဆင့် ၁/၅] AI Script ---
        if "Manual" in fc_script_mode:
            pbar.progress(10, text="📝 Manual ဇာတ်ညွှန်းအား ဖတ်ယူနေပါသည်...")
            fc_story_text = fc_manual_script.strip()
        else:
            with st.spinner(f"⏳ [အဆင့်၁/၅] Gemini ဖြင့် {fc_duration} မိနစ်စာ ဇာတ်လမ်း ရေးသားနေပါသည်..."):
                pbar.progress(10, text="📝 ဇာတ်လမ်း ရေးသားနေပါသည်...")
                
                # 🔴 PRO FEATURE 4: Context-Aware SSML Injection
                context_rules = ""
                if "Horror" in fc_niche or "Psychology" in fc_niche:
                    context_rules = "[CRITICAL SSML: Add Synergy tags like [pause=1.5] before scary reveals. Use [whisper] for dark secrets.]"
                elif "Motivation" in fc_niche:
                    context_rules = "[CRITICAL SSML: Add [shout] or highly energetic tone tags at the climax points.]"
                elif "Reddit" in fc_niche:
                    context_rules = "[CRITICAL SSML: Add [sigh], [cry], or [pause=1.0] to show deep emotional pacing.]"
                
                fc_custom_topic_with_ssml = f"{fc_custom_topic} {context_rules}".strip()

                success_ai, title, tags, script, err = generate_faceless_script(
                    api_key_input, fc_niche, fc_duration, fc_custom_topic_with_ssml, 
                    fc_script_hook, fc_script_curiosity, fc_script_tone, fc_script_cta
                )
                if not success_ai:
                    st.error(err)
                    st.stop()
                    
                st.session_state.viral_title = title
                st.session_state.viral_tags = tags
                fc_story_text = script

        # --- [အဆင့် ၂/၅] AI TTS ---
        with st.spinner("⏳ [အဆင့်၂/၅] AI သရုပ်ဆောင်ဖြင့် အသံဖန်တီးနေပါသည်..."):
            pbar.progress(30, text="🎙️ အသံဖန်တီးနေပါသည်...")
            try:
                clean_story = re.sub(r'\[.*?\]', '', fc_story_text)
                asyncio.run(generate_tts(
                    fc_story_text if "Synergy" in fc_audio_engine else clean_story, 
                    fc_voice_char, "fc_audio.wav", engine=fc_audio_engine, 
                    gemini_key=fc_synergy_key if fc_synergy_key else api_key_input, 
                    voice_fx=fc_fx
                ))
                fc_audio_dur = get_file_duration("fc_audio.wav")
                if fc_audio_dur < 5.0: 
                    st.error("❌ အသံထုတ်လုပ်ခြင်းမအောင်မြင်ပါ။ ပြန်လည်ကြိုးစားပါ။")
                    st.stop()
            except Exception as e: 
                st.error(f"Audio Error: {e}")
                st.stop()

        # --- [အဆင့် ၃/၅] Visuals AI & Dynamic Ken Burns ---
        with st.spinner("⏳ [အဆင့်၃/၅] Visuals များကို ပြင်ဆင်နေပါသည်..."):
            pbar.progress(50, text="🎥 Visuals ပြင်ဆင်နေပါသည်...")
            try:
                generated_clips = []
                v_w, v_h = (720, 1280) if "9:16" in fc_ratio else (1280, 720)
                
                # 🔴 PRO FEATURE 2: Dynamic Ken Burns Camera Movements
                pan_directions = [
                    "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'", # Center Zoom In
                    "x='0':y='0'", # Top Left Zoom
                    "x='iw-(iw/zoom)':y='ih-(ih/zoom)'", # Bottom Right Zoom
                    "x='(iw-iw/zoom)*time/duration':y='ih/2-(ih/zoom/2)'", # Pan Right
                    "x='(iw-iw/zoom)*(1-time/duration)':y='ih/2-(ih/zoom/2)'" # Pan Left
                ]

                if "Upload" in fc_visual_mode:
                    clip_dur = fc_audio_dur / len(fc_uploaded_images)
                    global_clip_dur = clip_dur
                    for i, img_file in enumerate(fc_uploaded_images):
                        img_path = f"fc_img_{i}.jpg"
                        clip_path = f"fc_clip_{i}.mp4"
                        img_file.seek(0)
                        with open(img_path, "wb") as f: f.write(img_file.read())
                        pbar.progress(50 + int((i/len(fc_uploaded_images))*15), text=f"🎥 Animation သွင်းနေပါသည် ({i+1}/{len(fc_uploaded_images)})...")
                        
                        direction = random.choice(pan_directions)
                        vf_expr = f"scale=-2:2000,zoompan=z='min(zoom+0.001,1.15)':d={int(clip_dur*25)}:{direction}:s={v_w}x{v_h},fps=25"
                        subprocess.run([FFMPEG_BINARY, "-y", "-loop", "1", "-framerate", "25", "-i", img_path, "-t", str(clip_dur), "-vf", vf_expr, "-c:v", "libx264", "-preset", "superfast", clip_path], capture_output=True)
                        if os.path.exists(clip_path): generated_clips.append(clip_path)
                else:
                    style_mapping = {
                        "👻 Horror / Creepypasta": "Ultra-realistic cinematic horror, 8k, eerie volumetric lighting, chilling atmosphere",
                        "💔 Reddit Relationship Drama": "Cinematic drama photography, moody soft lighting, hyper-detailed faces",
                        "🧠 Dark Psychology": "Neo-noir psychological thriller style, high contrast moody lighting",
                        "💡 Fun Facts / Trivia": "Vibrant Pixar 3D animation style, incredibly detailed, 8k",
                        "🚀 Motivation / Mindset": "Epic cinematic photography, golden hour god rays, dramatic sky",
                        "📜 Ancient History / Myths": "Epic fantasy concept art, dramatic cinematic lighting, intricate details"
                    }
                    current_style = style_mapping.get(fc_niche, "Cinematic, highly detailed 8k masterpiece")
                    img_count = max(4, int(fc_audio_dur // 12))
                    keys_list = [k.strip() for k in api_key_input.split(",") if k.strip()]
                    
                    search_keywords = []
                    for key in keys_list:
                        try:
                            client = genai.Client(api_key=key)
                            img_prompt_instruction = f"""Act as a professional Midjourney Prompt Engineer. Based on this story, give me exactly {img_count} highly detailed, epic English image generation prompts.
GLOBAL STYLE DNA: {current_style}. Format strictly separated by a pipe '|' with NO newlines.
Story: {fc_story_text[:500]}"""
                            prompt_req = client.models.generate_content(model="gemini-2.5-flash", contents=img_prompt_instruction)
                            raw_kws = prompt_req.text.replace('\n', '|').split('|')
                            search_keywords = [kw.strip() for kw in raw_kws if len(kw.strip()) > 5][:img_count]
                            break
                        except Exception: continue

                    if not search_keywords: search_keywords = [f"{current_style}, epic scene {i}" for i in range(img_count)]
                    total_clips = len(search_keywords)
                    clip_dur = fc_audio_dur / total_clips
                    global_clip_dur = clip_dur

                    def generate_pollinations_image(prompt_text, idx):
                        try:
                            final_prompt = prompt_text.strip() + ", masterpiece, 8k resolution, highly realistic"
                            encoded_prompt = urllib.parse.quote(final_prompt)
                            url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width={v_w}&height={v_h}&nologo=true"
                            res = requests.get(url, timeout=60)
                            if res.status_code == 200:
                                img_path = f"fc_img_{idx}.jpg"
                                clip_path = f"fc_clip_{idx}.mp4"
                                with open(img_path, "wb") as f: f.write(res.content)
                                
                                direction = random.choice(pan_directions)
                                vf_expr = f"scale=-2:2000,zoompan=z='min(zoom+0.001,1.15)':d={int(clip_dur*25)}:{direction}:s={v_w}x{v_h},fps=25"
                                subprocess.run([FFMPEG_BINARY, "-y", "-loop", "1", "-framerate", "25", "-i", img_path, "-t", str(clip_dur), "-vf", vf_expr, "-c:v", "libx264", "-preset", "superfast", clip_path], capture_output=True)
                                return clip_path
                        except Exception: pass
                        return None
                        
                    for i, kw in enumerate(search_keywords):
                        pbar.progress(50 + int(((i+1)/total_clips)*15), text=f"🎨 AI ဖြင့် ပုံများ ဖန်တီးနေပါသည် (Clip {i+1}/{total_clips})...")
                        generated_clip = generate_pollinations_image(kw, i)
                        if generated_clip and os.path.exists(generated_clip): generated_clips.append(generated_clip)
                        time.sleep(2)
                        
                    if not generated_clips: 
                        st.error("❌ Visual Generation Failed.")
                        st.stop()

                pbar.progress(65, text="🎞️ ဗီဒီယိုများကို ပေါင်းစပ်နေပါသည်...")
                with open("fc_concat.txt", "w") as f:
                    for c in generated_clips: f.write(f"file '{c}'\n")
                subprocess.run([FFMPEG_BINARY, "-y", "-stream_loop", "-1", "-f", "concat", "-safe", "0", "-i", "fc_concat.txt", "-t", str(fc_audio_dur), "-c", "copy", "fc_video_loop.mp4"], capture_output=True)
            except Exception as e: 
                st.error(f"Visual Error: {e}")
                st.stop()

        # --- [အဆင့် ၄/၅] Whisper Sync ---
        with st.spinner("⏳ [အဆင့်၄/၅] စာတန်းထိုးများကို ချိန်ညှိနေပါသည်..."):
            pbar.progress(70, text="📝 Timeline ချိန်ညှိနေပါသည်...")
            fc_parsed = None
            if groq_key_fc:
                try:
                    success_sync, parsed_data, err_sync = generate_whisper_sync_srt("fc_audio.wav", fc_story_text, groq_key_fc, fc_sub_short)
                    if success_sync: fc_parsed = parsed_data
                except Exception: pass
            if not fc_parsed:
                st.error("SRT Error: API Limit သို့မဟုတ် Key မှန်ကန်မှု စစ်ဆေးပါ။")
                st.stop()

        # --- [အဆင့် ၅/၅] Master Rendering ---
        with st.spinner("⏳ [အဆင့်၅/၅] အားလုံးကိုပေါင်းစပ်ပြီး Master Video ထုတ်လုပ်နေပါသည်..."):
            pbar.progress(85, text="🎬 Master Rendering အလုပ်လုပ်နေပါသည်...")
            try:
                render_cfg = VideoConfig(
                    ratio=fc_ratio, use_bypass=True, subtitle_mode=fc_subtitle_mode, 
                    sub_position=fc_sub_position, sub_color=fc_sub_color, sub_size=fc_sub_size, 
                    sub_thickness=2.5, sub_bg=False, font_path=fc_selected_font,
                    use_sfx=fc_use_sfx, transition_interval=global_clip_dur # 🔴 Auto-SFX parameters
                )
                
                success, err_msg = render_premium_saas_video("fc_video_loop.mp4", "fc_audio.wav", fc_parsed, v_final, render_cfg)
                if not success: 
                    st.error(f"❌ Video Output Failure: {err_msg}")
                    st.stop()

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
                        success_thumb, _ = generate_professional_thumbnail(v_final, thumb_name, st.session_state.viral_title if st.session_state.viral_title else "Viral Video", t_val, style=fc_thumb_style, font_path=fc_selected_font)
                        if success_thumb:
                            if thumb_suffix == "A": st.session_state.thumb_path_A = thumb_name
                            elif thumb_suffix == "B": st.session_state.thumb_path_B = thumb_name
                except Exception: pass
                        
                pbar.progress(100, text="✅ အားလုံးပြီးစီးပါပြီ!")
                st.balloons()
                st.success("🎉 Faceless Video ထုတ်လုပ်မှု အောင်မြင်စွာ ပြီးစီးပါပြီ!")
                st.session_state.viral_score = predict_virality_score(api_key_input, st.session_state.viral_title, fc_story_text)
                
                col_f1, col_f2 = st.columns(2)
                with col_f1:
                    if os.path.exists(st.session_state.final_video_path):
                        st.video(st.session_state.final_video_path)
                        st.markdown(get_download_link(st.session_state.final_video_path, "Viral_Faceless.mp4", "Download Final Video"), unsafe_allow_html=True)
                with col_f2:
                    st.info(f"📈 **Viral Prediction:**\n{st.session_state.viral_score}")
                    if st.session_state.thumb_path_A: st.image(st.session_state.thumb_path_A, caption="Thumbnail A")
                    st.text_area("ဇာတ်လမ်း:", value=fc_story_text, height=150, disabled=True)
            except Exception as e: 
                st.error(f"Render Error: {e}")
                st.stop()
