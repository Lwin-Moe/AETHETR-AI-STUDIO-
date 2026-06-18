import os
import re
import subprocess
import shutil
import yt_dlp
import ffmpeg
import imageio_ffmpeg

if shutil.which("ffmpeg"):
    FFMPEG_BINARY = "ffmpeg"
else:
    FFMPEG_BINARY = imageio_ffmpeg.get_ffmpeg_exe()

def cleanup_temp_files():
    for f in os.listdir("."):
        if f.startswith(("fc_clip_", "fc_img_", "raw_fc_clip_", "temp_", "subtitles.", "thumb_A_", "thumb_B_", "FACELESS_FINAL_", "AETHER_RECAP_FINAL_", "fc_audio.wav", "fc_video_loop.mp4")):
            try:
                os.remove(f)
            except Exception:
                pass

def get_file_duration(file_path):
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

def download_video_from_url(url, output_path="input_temp.mp4"):
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
        raise Exception(f"YouTube Download Error: {str(e)}")

def extract_audio_fast(video_in, audio_out="temp_extracted.mp3"):
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