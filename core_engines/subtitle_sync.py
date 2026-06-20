import os
import re
import whisperx
import torch
import streamlit as st

def fmt_time(seconds):
    """စက္ကန့်များကို SRT Timestamp (HH:MM:SS,mmm) သို့ ပြောင်းပေးမည်"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def strip_audio_tags_pro(text):
    text = re.sub(r'\[.*?\]', '', text)
    text = re.sub(r'\{.*?\}', '', text)
    text = re.sub(r'SPEAKER[_ ]?\d+[:\s]*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'Speaker[_ ]?\d+[:\s]*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\([^)]*\)', '', text)
    text = re.sub(r'\u266a.*?\u266a', '', text)
    return re.sub(r'\s+', ' ', text).strip()

def parse_and_save_real_srt(segments, output_file, use_fade=False):
    final_parsed = []
    full_speech = []

    with open(output_file, "w", encoding="utf-8-sig") as f:
        for i, segment in enumerate(segments, 1):
            start = segment.get("start", 0.0)
            end = segment.get("end", start + 1.0)
            text = segment.get("text", "").strip()
            
            if not text:
                continue

            clean_speech_text = re.sub(r'[^\w\s\u1000-\u109F]', '', text)
            if clean_speech_text.strip():
                full_speech.append(clean_speech_text)

            final_parsed.append((start, end, text))
            f.write(f"{i}\n{fmt_time(start)} --> {fmt_time(end)}\n{text}\n\n")

    return final_parsed, " ".join(full_speech)

# 🔴 STREAMLIT CACHE: Model ကို တစ်ကြိမ်သာ Load လုပ်ရန်
@st.cache_resource(show_spinner=False)
def load_whisperx_model():
    """WhisperX Model ကို Memory တွင် အသေတင်ထားပေးမည့် Cache Function"""
    device = "cuda" if torch.cuda.is_available() else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"
    
    print("🔄 Loading WhisperX Model into Cache...")
    model = whisperx.load_model("large-v3", device, compute_type=compute_type, language="my")
    return model, device

def generate_whisper_sync_srt(audio_file_path, story_text, groq_api_key=None, sub_short=False):
    try:
        # 1. Cached Model ကို လှမ်းခေါ်ခြင်း (အချိန်လုံးဝမကြာတော့ပါ)
        model, device = load_whisperx_model()
        
        # 2. Audio Loading
        audio = whisperx.load_audio(audio_file_path)
        
        # 3. Transcription & VAD
        result = model.transcribe(audio, batch_size=4)
        segments = result["segments"]
        
        # 4. Forced Alignment
        try:
            model_a, metadata = whisperx.load_align_model(language_code="my", fallback=True, device=device)
            result = whisperx.align(segments, model_a, metadata, audio, device, return_char_alignments=False)
            segments = result["segments"]
        except Exception as align_err:
            print(f"⚠️ Alignment optimization skipped: {align_err}")

        # 5. Hormozi Style Chunking
        if sub_short:
            short_segments = []
            for seg in segments:
                words = seg["text"].split()
                if len(words) > 4:
                    chunk_dur = (seg["end"] - seg["start"]) / len(words)
                    for idx in range(0, len(words), 4):
                        chunk = words[idx:idx+4]
                        short_segments.append({
                            "start": seg["start"] + (idx * chunk_dur),
                            "end": seg["start"] + ((idx + len(chunk)) * chunk_dur),
                            "text": " ".join(chunk)
                        })
                else:
                    short_segments.append(seg)
            segments = short_segments

        # 6. SRT သိမ်းဆည်းခြင်း
        fc_parsed, _ = parse_and_save_real_srt(segments, "subtitles.srt", use_fade=False)
        
        # 🔴 CRITICAL: VRAM ရှင်းလင်းခြင်း 
        # Streamlit တွင် နောက်တစ်ကြိမ် Render လုပ်ပါက Memory မပြည့်စေရန် Model_A ကိုသာ ဖျက်မည်။ Main Model ကို Cache တွင် ထားမည်။
        if 'model_a' in locals():
            del model_a
        torch.cuda.empty_cache()
        
        if fc_parsed:
            return True, fc_parsed, None
        else:
            return False, None, "WhisperX မှ အသံနှင့် စာသား ခွဲခြားမှု မရရှိပါ။"
            
    except Exception as e: 
        return False, None, str(e)
