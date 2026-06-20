import re
from groq import Groq

def fmt_time(seconds):
    """စက္ကန့်များကို SRT Timestamp (HH:MM:SS,mmm) သို့ ပြောင်းပေးမည်"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def strip_audio_tags_pro(text):
    """ဇာတ်ညွှန်းထဲမှ အသံ Tag များနှင့် မလိုအပ်သော စာသားများကို ရှင်းလင်းမည်"""
    text = re.sub(r'\[.*?\]', '', text)
    text = re.sub(r'\{.*?\}', '', text)
    text = re.sub(r'SPEAKER[_ ]?\d+[:\s]*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'Speaker[_ ]?\d+[:\s]*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\([^)]*\)', '', text)
    text = re.sub(r'\u266a.*?\u266a', '', text)
    return re.sub(r'\s+', ' ', text).strip()

def parse_and_save_real_srt(raw_srt_text, output_file, use_fade=False):
    """Raw SRT Text ကို ဖတ်၍ .srt ဖိုင်အဖြစ် တကယ့် Hard Drive တွင် သိမ်းဆည်းပေးမည်"""
    lines = raw_srt_text.strip().split('\n')
    parsed_lines = []
    current_start, current_end = 0.0, 0.0
    current_text = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.isdigit() and len(line) < 5:
            continue

        if "-->" in line:
            if current_text:
                parsed_lines.append((current_start, current_end, " ".join(current_text)))
                current_text = []

            parts = line.split("-->")
            try:
                def parse_lenient(t_str):
                    t_str = t_str.strip().replace('.', ',')
                    if ',' not in t_str:
                        t_str += ",000"
                    main_t, ms = t_str.split(',')
                    tp = main_t.split(':')
                    if len(tp) == 1:
                        return int(tp[0]) + float(ms.ljust(3, '0'))/1000.0
                    elif len(tp) == 2:
                        return int(tp[0])*60 + int(tp[1]) + float(ms.ljust(3, '0'))/1000.0
                    else:
                        return int(tp[0])*3600 + int(tp[1])*60 + int(tp[2]) + float(ms.ljust(3, '0'))/1000.0

                current_start = parse_lenient(parts[0])
                current_end = parse_lenient(parts[1])
            except Exception:
                pass
        else:
            if not re.match(r'^\[.*?\]$', line):
                current_text.append(line)

    if current_text:
        parsed_lines.append((current_start, current_end, " ".join(current_text)))

    final_parsed = []
    prev_end = 0.0
    full_speech = []

    for start, end, txt in parsed_lines:
        if start < prev_end:
            start = prev_end + 0.1
        if end - start < 0.8:
            end = start + 0.8
        prev_end = end

        clean_speech_text = re.sub(r'[^\w\s\u1000-\u109F]', '', txt)
        if clean_speech_text.strip():
            full_speech.append(clean_speech_text)

        final_parsed.append((start, end, txt))

    with open(output_file, "w", encoding="utf-8-sig") as f:
        for i, (s, e, t) in enumerate(final_parsed, 1):
            f.write(f"{i}\n{fmt_time(s)} --> {fmt_time(e)}\n{t}\n\n")

    return final_parsed, " ".join(full_speech)

def generate_whisper_sync_srt(audio_file_path, story_text, groq_api_key, sub_short=False):
    """Whisper ဖြင့် Word-Level Sync ချိန်ညှိပေးသော Main Function (Export အဖြစ် သုံးရန်)"""
    try:
        client_groq = Groq(api_key=groq_api_key)
        
        with open(audio_file_path, "rb") as file:
            transcription = client_groq.audio.transcriptions.create(
                file=(audio_file_path, file.read()),
                model="whisper-large-v3",
                response_format="verbose_json",
                language="my",
                timestamp_granularities=["word"] 
            )

        whisper_words = []
        if isinstance(transcription, dict):
            if transcription.get('words'): whisper_words = transcription['words']
            elif transcription.get('segments'):
                for seg in transcription['segments']:
                    if isinstance(seg, dict) and seg.get('words'): whisper_words.extend(seg['words'])
        elif hasattr(transcription, 'words') and transcription.words:
            whisper_words = transcription.words
        elif hasattr(transcription, 'segments') and transcription.segments:
            for seg in transcription.segments:
                seg_words = getattr(seg, 'words', []) or []
                whisper_words.extend(seg_words)

        clean_script = strip_audio_tags_pro(story_text)
        script_words = clean_script.split()
        
        total_sw = len(script_words)
        total_ww = len(whisper_words)
        raw_srt_str = ""
        chunk_idx = 1

        if total_sw > 0 and total_ww >= 3:
            chunk_size = 3 if sub_short else 6 
            min_duration = 1.0 
            
            for i in range(0, total_sw, chunk_size):
                chunk_words = script_words[i:i + chunk_size]
                chunk_text = ' '.join(chunk_words)
                
                start_script_idx = i
                end_script_idx = min(i + len(chunk_words) - 1, total_sw - 1)
                
                start_whisper_idx = int((start_script_idx / total_sw) * total_ww)
                end_whisper_idx = int((end_script_idx / total_sw) * total_ww)
                
                start_whisper_idx = max(0, min(start_whisper_idx, total_ww - 1))
                end_whisper_idx = max(0, min(end_whisper_idx, total_ww - 1))
                
                w_start = whisper_words[start_whisper_idx]
                w_end = whisper_words[end_whisper_idx]
                
                if isinstance(w_start, dict):
                    start_time = w_start['start']
                    end_time = w_end['end']
                else:
                    start_time = w_start.start
                    end_time = w_end.end
                    
                if end_time - start_time < min_duration:
                    end_time = start_time + min_duration
                    
                start_time = max(0, start_time)
                
                raw_srt_str += f"{chunk_idx}\n{fmt_time(start_time)} --> {fmt_time(end_time)}\n{chunk_text}\n\n"
                chunk_idx += 1
                
            fc_parsed, _ = parse_and_save_real_srt(raw_srt_str, "subtitles.srt", use_fade=False)
            return True, fc_parsed, None
        else:
            return False, None, "Whisper ဆီမှ Word-level timestamps အလုံအလောက် မရရှိပါ။ (Audio ဖိုင်တိုလွန်းနေနိုင်ပါသည်)"
            
    except Exception as e: 
        return False, None, str(e)
