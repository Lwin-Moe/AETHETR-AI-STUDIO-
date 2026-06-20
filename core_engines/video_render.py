import os
import re
import shutil
import textwrap
import subprocess
import ffmpeg
import imageio_ffmpeg
import yt_dlp

# 👇 FIX: Prioritize system FFmpeg
if shutil.which("ffmpeg"):
    FFMPEG_BINARY = "ffmpeg"
else:
    FFMPEG_BINARY = imageio_ffmpeg.get_ffmpeg_exe()

def get_file_duration(file_path):
    """မီဒီယာဖိုင်များ၏ ကြာချိန်ကို တိုင်းတာပေးမည်"""
    try:
        cmd = [FFMPEG_BINARY, "-i", file_path]
        result = subprocess.run(cmd, capture_output=True, text=True, errors='ignore')
        match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", result.stderr)
        if match:
            h, m, s = match.groups()
            return int(h) * 3600 + int(m) * 60 + float(s)
    except Exception: 
        pass
    return 600.0 

# =====================================================================
# 📌 MEDIA ACQUISITION (DOWNLOAD & EXTRACT)
# =====================================================================
def download_video_from_url(url, output_path="input_temp.mp4"):
    """YouTube, FB, TikTok စသည့် URL များမှ ဗီဒီယို ဒေါင်းလုဒ်ဆွဲမည်"""
    if os.path.exists(output_path):
        os.remove(output_path)
    ydl_opts = {
        'outtmpl': output_path,
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'quiet': True, 'no_warnings': True, 'nocheckcertificate': True,
        'ffmpeg_location': FFMPEG_BINARY, 'source_address': '0.0.0.0',
        'extractor_args': {'youtube': {'player_client': ['tv', 'ios', 'web']}}
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        return output_path
    except Exception as e:
        raise Exception(f"Video Download Error: {str(e)}")

def extract_audio_fast(video_in, audio_out="temp_extracted.mp3"):
    """ဗီဒီယိုထဲမှ အသံကို အမြန်ခွဲထုတ်မည်"""
    if os.path.exists(audio_out):
        os.remove(audio_out)
    try:
        (ffmpeg.input(video_in).output(audio_out, acodec='libmp3lame', ac=1, ar='16000')
         .run(cmd=FFMPEG_BINARY, overwrite_output=True, capture_stdout=True, capture_stderr=True))
        if os.path.exists(audio_out):
            return audio_out
    except Exception:
        pass
    return None

# =====================================================================
# 📌 TIKTOK HOOK & LOOP SYSTEM
# =====================================================================
def add_tiktok_hook_overlay(video_input, output_path, hook_text, niche="💡 Fun Facts / Trivia", duration=3.5, font_path="Padauk.ttf"):
    try:
        video = ffmpeg.input(video_input).video
        audio = ffmpeg.input(video_input).audio
        hook_styles = {
            "👻 Horror / Creepypasta": {"text_color": "red", "bg_color": "black@0.8", "font_size": 55},
            "🚀 Motivation / Mindset": {"text_color": "gold", "bg_color": "black@0.6", "font_size": 50},
            "💡 Fun Facts / Trivia": {"text_color": "cyan", "bg_color": "black@0.7", "font_size": 45},
            "🧠 Dark Psychology": {"text_color": "white", "bg_color": "black@0.9", "font_size": 50},
            "📜 Ancient History / Myths": {"text_color": "gold", "bg_color": "black@0.7", "font_size": 48}
        }
        style = hook_styles.get(niche, hook_styles["💡 Fun Facts / Trivia"])
        wrapped_hook = textwrap.wrap(hook_text, width=20)
        if not wrapped_hook: wrapped_hook = [hook_text]
        max_len = max(len(line) for line in wrapped_hook)
        centered_hook = "\n".join(line.center(max_len, " ") for line in wrapped_hook)
        
        with open("hook_text.txt", "w", encoding="utf-8") as f: 
            f.write(centered_hook)
            
        video = ffmpeg.filter(video, 'drawbox', x=0, y='h*0.3', w='iw', h='h*0.4', color=style["bg_color"], thickness='fill', enable=f'between(t,0,{duration})')
        video = ffmpeg.filter(video, 'drawtext', textfile='hook_text.txt', fontfile=font_path.replace('\\', '/'), fontsize=style["font_size"], fontcolor=style["text_color"], bordercolor='black', borderw=3, x='(w-text_w)/2', y='(h-text_h)/2', line_spacing=15, text_align='C', enable=f'between(t,0,{duration})')
        
        if niche == "👻 Horror / Creepypasta":
            video = ffmpeg.filter(video, 'drawbox', x=0, y='h*0.28', w='iw', h='4', color='red@0.9', thickness='fill', enable=f'between(t,0,{duration})')
            video = ffmpeg.filter(video, 'drawbox', x=0, y='h*0.72', w='iw', h='4', color='red@0.9', thickness='fill', enable=f'between(t,0,{duration})')
            
        out = ffmpeg.output(video, audio, output_path, vcodec='libx264', pix_fmt='yuv420p', acodec='aac', audio_bitrate='128k', preset='superfast')
        out.overwrite_output().run(cmd=FFMPEG_BINARY, quiet=True)
        return output_path
    except Exception:
        return video_input

def add_tiktok_loop_point(video_input, output_path, font_path="Padauk.ttf"):
    try:
        dur = get_file_duration(video_input)
        video = ffmpeg.input(video_input).video
        audio = ffmpeg.input(video_input).audio
        video = ffmpeg.filter(video, 'drawtext', text='👆 ပြန်ကြည့်ပါ', fontfile=font_path.replace('\\', '/'), fontsize=35, fontcolor='white', bordercolor='black', borderw=2, x='(w-text_w)/2', y='(h-text_h)/2', enable=f'between(t,{dur-2},{dur})')
        out = ffmpeg.output(video, audio, output_path, vcodec='libx264', pix_fmt='yuv420p', acodec='aac', audio_bitrate='128k', preset='superfast')
        out.overwrite_output().run(cmd=FFMPEG_BINARY, quiet=True)
        return output_path
    except Exception:
        return video_input

# =====================================================================
# 📌 PROFESSIONAL THUMBNAIL SYSTEM
# =====================================================================
THUMBNAIL_STYLES = {
    "🔥 Viral TikTok Style": {"text_position": "center", "font_size_range": (50, 90), "bg_overlay": "gradient_bottom", "text_effect": "stroke_bold", "color_scheme": "yellow_red"},
    "🎬 Cinematic Movie Poster": {"text_position": "bottom_third", "font_size_range": (40, 70), "bg_overlay": "vignette_dark", "text_effect": "shadow_soft", "color_scheme": "white_gold"},
    "👻 Horror / Mystery": {"text_position": "center", "font_size_range": (55, 85), "bg_overlay": "dark_gradient", "text_effect": "shadow_horror", "color_scheme": "red_black"},
    "💎 Premium / Luxury": {"text_position": "bottom_third", "font_size_range": (40, 65), "bg_overlay": "golden_frame", "text_effect": "golden_text", "color_scheme": "gold_cream"},
    "⚡ Clean / Minimal": {"text_position": "center", "font_size_range": (45, 80), "bg_overlay": "subtle_overlay", "text_effect": "clean_white", "color_scheme": "white_soft"}
}

def calculate_optimal_font_size(text, min_size, max_size):
    text_length = len(text)
    if text_length < 20: return max_size
    elif text_length < 40: return int(max_size * 0.85)
    elif text_length < 60: return int(max_size * 0.7)
    elif text_length < 80: return int(max_size * 0.55)
    else: return max(min_size, int(max_size * 0.45))

def wrap_text_for_thumbnail(text, max_width=25):
    text = re.sub(r'\[.*?\]', '', text)
    lines = textwrap.wrap(text, width=max_width, break_long_words=False)
    if not lines: lines = [text[:max_width]]
    max_len = max(len(line) for line in lines)
    centered_lines = [line.center(max_len, " ") for line in lines]
    return "\n".join(centered_lines)

def generate_professional_thumbnail(video_input, output_path, title_text, timestamp, style="🔥 Viral TikTok Style", font_path="Padauk.ttf"):
    try:
        style_config = THUMBNAIL_STYLES.get(style, THUMBNAIL_STYLES["🔥 Viral TikTok Style"])
        video = ffmpeg.input(video_input, ss=timestamp)
        
        if style_config["bg_overlay"] == "gradient_bottom": video = ffmpeg.filter(video, 'drawbox', x=0, y='ih/2', w='iw', h='ih/2', color='black@0.0:black@0.7', thickness='fill')
        elif style_config["bg_overlay"] == "vignette_dark": video = ffmpeg.filter(video, 'vignette', PI=0.5)
        elif style_config["bg_overlay"] == "dark_gradient": video = ffmpeg.filter(video, 'drawbox', x=0, y=0, w='iw', h='ih', color='black@0.4', thickness='fill')
        elif style_config["bg_overlay"] == "subtle_overlay": video = ffmpeg.filter(video, 'drawbox', x=0, y=0, w='iw', h='ih', color='black@0.2', thickness='fill')
        
        font_size = calculate_optimal_font_size(title_text, style_config["font_size_range"][0], style_config["font_size_range"][1])
        if style_config["text_position"] == "center": y_position = "(h-text_h)/2"
        elif style_config["text_position"] == "bottom_third": y_position = "h*0.65"
        elif style_config["text_position"] == "top_third": y_position = "h*0.15"
        else: y_position = "(h-text_h)/2"
        
        color_schemes = {
            "yellow_red": {"text": "yellow", "shadow": "red", "box": "red@0.8"},
            "white_gold": {"text": "white", "shadow": "gold", "box": "black@0.6"},
            "red_black": {"text": "red", "shadow": "black", "box": "black@0.8"},
            "gold_cream": {"text": "gold", "shadow": "brown", "box": "black@0.5"},
            "white_soft": {"text": "white", "shadow": "gray", "box": "black@0.4"}
        }
        colors = color_schemes.get(style_config["color_scheme"], color_schemes["yellow_red"])
        
        if style_config["text_effect"] == "stroke_bold": border_width = 4
        elif style_config["text_effect"] == "shadow_soft": border_width = 2
        elif style_config["text_effect"] == "shadow_horror": border_width = 5
        elif style_config["text_effect"] == "golden_text": border_width = 2
        else: border_width = 3
        
        wrapped_text = wrap_text_for_thumbnail(title_text)
        with open("thumb_pro_text.txt", "w", encoding="utf-8") as f: f.write(wrapped_text)
        
        video = ffmpeg.filter(video, 'drawtext', textfile='thumb_pro_text.txt', fontfile=font_path.replace('\\', '/'), fontcolor=colors["text"], fontsize=font_size, bordercolor=colors["shadow"], borderw=border_width, box=1, boxcolor=colors["box"], boxborderw=15, x='(w-text_w)/2', y=y_position, line_spacing=15, text_align='C')
        ffmpeg.output(video, output_path, vframes=1, qscale=2).overwrite_output().run(cmd=FFMPEG_BINARY, quiet=True)
        return True, output_path
    except Exception as e:
        return False, str(e)

# =====================================================================
# 📌 MAIN VIDEO RENDERING SYSTEM
# =====================================================================
def render_premium_saas_video(in_v, in_a, parsed_timestamps, out_v, ratio, use_bypass=False, use_blur=False, watermark="", subtitle_mode="Both (Burn + SRT)", use_mirror=False, use_color=False, use_grain=False, use_fps=False, sub_position="Bottom", sub_color="Yellow", sub_size=28, sub_thickness=2.5, sub_bg=False, use_freeze=False, logo_path=None, font_path="Padauk.ttf"):
    try:
        a_dur = get_file_duration(in_a)
        video = ffmpeg.input(in_v).video
        v_w, v_h = (720, 1280) if "9:16" in ratio else (1280, 720)
        video = ffmpeg.filter(video, 'scale', v_w, v_h, force_original_aspect_ratio='increase').filter('crop', v_w, v_h)

        if use_bypass: video = ffmpeg.filter(video, 'scale', '2*trunc(iw*1.08/2)', '2*trunc(ih*1.08/2)').filter('crop', 'iw/1.08', 'ih/1.08')
        if use_mirror: video = ffmpeg.filter(video, 'hflip')
        if use_color: video = ffmpeg.filter(video, 'eq', brightness=0.02, contrast=1.05, saturation=1.1)
        if use_grain: video = ffmpeg.filter(video, 'noise', alls=2, allf='t+u')
        if use_fps: video = ffmpeg.filter(video, 'fps', fps=24, round='near')
        if use_freeze: video = ffmpeg.filter(video, 'minterpolate', fps=12, mi_mode='dup')

        audio = ffmpeg.input(in_a).audio
        if use_blur: video = ffmpeg.filter(video, 'drawbox', x=0, y='ih-90', w='iw', h=90, color='black@0.95', thickness='fill')
        if watermark: video = ffmpeg.filter(video, 'drawtext', text=watermark, x='w-tw-15', y='15', fontsize=30, fontcolor='white@0.5')

        if logo_path and os.path.exists(logo_path):
            logo = ffmpeg.input(logo_path)
            logo = ffmpeg.filter(logo, 'scale', -1, 80)
            video = ffmpeg.overlay(video, logo, x='W-w-20', y=20)

        if subtitle_mode in ["Burn into Video", "Both (Burn + SRT)"] and parsed_timestamps:
            wrap_width = 25 if "9:16" in ratio else 45
            safe_font_path = font_path.replace('\\', '/')

            for i, (start, end, text) in enumerate(parsed_timestamps):
                wrapped_lines = textwrap.wrap(text, width=wrap_width)
                if not wrapped_lines: wrapped_lines = [text]
                max_len = max(len(line) for line in wrapped_lines)
                centered_text = "\n".join(line.center(max_len, " ") for line in wrapped_lines)

                txt_filename = f"temp_sub_{i}.txt"
                with open(txt_filename, "w", encoding="utf-8") as tf:
                    tf.write(centered_text)

                if "Center" in sub_position: y_expr = "(h-text_h)/2"
                elif "Top" in sub_position: y_expr = "150"
                else: y_expr = "h-text_h-150"

                c_str = "yellow"
                if "White" in sub_color: c_str = "white"
                elif "Green" in sub_color: c_str = "green"
                elif "Red" in sub_color: c_str = "red"
                elif "Gold" in sub_color: c_str = "gold"

                box_str = 1 if sub_bg else 0
                box_color = 'black@0.6' if sub_bg else 'black@0.0'

                video = ffmpeg.filter(video, 'drawtext', textfile=txt_filename, fontfile=safe_font_path, fontcolor=c_str, fontsize=sub_size, bordercolor='black', borderw=sub_thickness, box=box_str, boxcolor=box_color, boxborderw=10, x='(w-text_w)/2', y=y_expr, line_spacing=20, text_align='C', enable=f'between(t,{start},{end})')

        out = ffmpeg.output(video, audio, out_v, vcodec='libx264', pix_fmt='yuv420p', acodec='aac', preset='superfast', crf=23, t=a_dur)
        out.run(cmd=FFMPEG_BINARY, overwrite_output=True, capture_stdout=True, capture_stderr=True)
        return True, "Success"
    except ffmpeg.Error as e:
        return False, e.stderr.decode('utf-8', errors='ignore')
