import os
import ffmpeg
import textwrap
from core.utils.ffmpeg_utils import get_file_duration, FFMPEG_BINARY

def render_premium_saas_video(in_v, in_a, parsed_timestamps, out_v, ratio, use_bypass=False, use_blur=False, watermark="", subtitle_mode="Both (Burn + SRT)", use_mirror=False, use_color=False, use_grain=False, use_fps=False, sub_position="Bottom", sub_color="Yellow", sub_size=26, sub_thickness=2.5, sub_bg=False, use_freeze=False, logo_path=None):
    try:
        a_dur = get_file_duration(in_a)
        
        video = ffmpeg.input(in_v).video
        
        v_w, v_h = (720, 1280) if "9:16" in ratio else (1280, 720)
        video = ffmpeg.filter(video, 'scale', v_w, v_h, force_original_aspect_ratio='increase').filter('crop', v_w, v_h)
        
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
        
        audio = ffmpeg.input(in_a).audio
        if use_blur: 
            video = ffmpeg.filter(video, 'drawbox', x=0, y='ih-90', w='iw', h=90, color='black@0.95', thickness='fill')
        if watermark: 
            video = ffmpeg.filter(video, 'drawtext', text=watermark, x='w-tw-15', y='15', fontsize=30, fontcolor='white@0.5')
        
        if logo_path and os.path.exists(logo_path):
            logo = ffmpeg.input(logo_path)
            logo = ffmpeg.filter(logo, 'scale', -1, 80)
            video = ffmpeg.overlay(video, logo, x='W-w-20', y=20)

        if subtitle_mode in ["Burn into Video", "Both (Burn + SRT)"] and parsed_timestamps:
            wrap_width = 25 if "9:16" in ratio else 45
            
            for i, (start, end, text) in enumerate(parsed_timestamps):
                wrapped_text = textwrap.fill(text, width=wrap_width)
                txt_filename = f"temp_sub_{i}.txt"
                with open(txt_filename, "w", encoding="utf-8") as tf:
                    tf.write(wrapped_text)
                
                if "Center" in sub_position: 
                    y_expr = "(h-text_h)/2"
                elif "Top" in sub_position: 
                    y_expr = "150"
                else: 
                    y_expr = "h-text_h-150"
                
                c_str = "yellow"
                if "White" in sub_color: c_str = "white"
                elif "Green" in sub_color: c_str = "green"
                elif "Red" in sub_color: c_str = "red"
                elif "Gold" in sub_color: c_str = "gold"

                box_str = 1 if sub_bg else 0
                box_color = 'black@0.6' if sub_bg else 'black@0.0'
                
                escaped_text = wrapped_text.replace("'", "\u2019").replace(":", "\\:")

                video = ffmpeg.filter(video, 'drawtext', textfile=txt_filename, fontfile='Padauk.ttf', fontcolor=c_str, fontsize=sub_size, bordercolor='black', borderw=sub_thickness, box=box_str, boxcolor=box_color, boxborderw=10, x='(w-text_w)/2', y=y_expr, line_spacing=20, enable=f'between(t,{start},{end})')

        out = ffmpeg.output(video, audio, out_v, vcodec='libx264', pix_fmt='yuv420p', acodec='aac', preset='superfast', crf=23, t=a_dur)
        out.run(cmd=FFMPEG_BINARY, overwrite_output=True, capture_stdout=True, capture_stderr=True)
        return True, "Success"
    except ffmpeg.Error as e: 
        return False, e.stderr.decode('utf-8', errors='ignore')