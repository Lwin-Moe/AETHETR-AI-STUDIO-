# ... (previous code up to TTS generation block) ...

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
                        target_dur = st.session_state.md_video_dur

                        # 🔴 SYNC FIX: Robust duration matching
                        audio_to_process = a_generated
                        current_dur = a_dur_raw

                        # First atempo pass
                        if current_dur > 0 and target_dur > 0:
                            ratio = current_dur / target_dur
                            # If ratio is too close to 1.0, skip
                            if abs(ratio - 1.0) > 0.01:
                                filt = get_atempo_filter(ratio)
                                if filt:
                                    synced_path = "md_audio_synced1.wav"
                                    # Use ffmpeg with atempo and output format
                                    cmd_sync = [
                                        FFMPEG_BINARY, "-y",
                                        "-i", audio_to_process,
                                        "-filter:a", filt,
                                        "-c:a", "pcm_s16le",
                                        synced_path
                                    ]
                                    subprocess.run(cmd_sync, capture_output=True)
                                    if os.path.exists(synced_path) and os.path.getsize(synced_path) > 100:
                                        audio_to_process = synced_path
                                        # Re-check duration
                                        current_dur = get_wav_duration(audio_to_process)
                                        st.toast(f"⚡ First sync: {a_dur_raw:.2f}s → {current_dur:.2f}s (target {target_dur:.2f}s)")

                        # Second pass if still off by >0.1s
                        if abs(current_dur - target_dur) > 0.1 and target_dur > 0:
                            residual_ratio = current_dur / target_dur
                            if abs(residual_ratio - 1.0) > 0.01:
                                filt2 = get_atempo_filter(residual_ratio)
                                if filt2:
                                    synced2 = "md_audio_synced2.wav"
                                    cmd_sync2 = [
                                        FFMPEG_BINARY, "-y",
                                        "-i", audio_to_process,
                                        "-filter:a", filt2,
                                        "-c:a", "pcm_s16le",
                                        synced2
                                    ]
                                    subprocess.run(cmd_sync2, capture_output=True)
                                    if os.path.exists(synced2) and os.path.getsize(synced2) > 100:
                                        audio_to_process = synced2
                                        current_dur = get_wav_duration(audio_to_process)
                                        st.toast(f"⚡ Second sync: now {current_dur:.2f}s (target {target_dur:.2f}s)")

                        # Final trim/pad to exact target duration
                        final_audio = "md_audio_exact.wav"
                        # Use atrim to cut exactly (or pad if shorter, but it should be very close)
                        trim_filter = f"atrim=0:{target_dur}"
                        cmd_final = [
                            FFMPEG_BINARY, "-y",
                            "-i", audio_to_process,
                            "-af", trim_filter,
                            "-t", str(target_dur),
                            "-c:a", "pcm_s16le",
                            final_audio
                        ]
                        subprocess.run(cmd_final, capture_output=True)
                        if os.path.exists(final_audio) and os.path.getsize(final_audio) > 100:
                            a_final_target = final_audio
                        else:
                            a_final_target = audio_to_process  # fallback

                        st.session_state.md_final_audio_path = a_final_target
                        st.session_state.md_audio_dur = get_wav_duration(a_final_target)
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
