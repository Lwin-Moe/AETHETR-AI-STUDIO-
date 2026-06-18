import re

def parse_and_save_real_srt(raw_srt_text, output_file, use_fade=False):
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
            def fmt(sec):
                return f"{int(sec//3600):02d}:{int((sec%3600)//60):02d}:{int(sec%60):02d},{int((sec%1)*1000):03d}"
            f.write(f"{i}\n{fmt(s)} --> {fmt(e)}\n{t}\n\n")
            
    return final_parsed, " ".join(full_speech)