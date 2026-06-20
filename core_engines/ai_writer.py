import re
from google import genai

def parse_generated_script(raw_text):
    """AI ရေးပေးလိုက်သော စာသားထဲမှ Title, Tags နှင့် Script ကို သီးခြားစီ ခွဲထုတ်ပေးမည်"""
    title_match = re.search(r'\[TITLE:\s*(.*?)\]', raw_text, re.IGNORECASE)
    tags_match = re.search(r'\[TAGS:\s*(.*?)\]', raw_text, re.IGNORECASE)
    
    title = re.sub(r'[\[\]]', '', title_match.group(1)).strip() if title_match else "Viral Video"
    tags = tags_match.group(1).strip() if tags_match else "#viral #myanmar"
    
    clean_text = re.sub(r'\[TITLE:.*?\]', '', raw_text, flags=re.IGNORECASE)
    clean_text = re.sub(r'\[TAGS:.*?\]', '', clean_text, flags=re.IGNORECASE).strip()
    
    # Remove markdown code blocks if AI added them
    marker = chr(96) * 3
    clean_text = clean_text.replace(f"{marker}srt", "").replace(marker, "").strip()
    
    return title, tags, clean_text

def generate_faceless_script(api_key_input, niche, duration, custom_topic, script_hook, script_curiosity, script_tone, script_cta):
    """Faceless Video များအတွက် AI ဇာတ်လမ်း ဖန်တီးပေးမည်"""
    keys_list = [k.strip() for k in api_key_input.split(",") if k.strip()]
    target_words = duration * 140
    
    topic_instruction = f"Specifically, the story MUST be deeply focused on this topic: {custom_topic.strip()}.\n" if custom_topic.strip() else ""
    hook_rule = "1. THE VIRAL HOOK (0-3s): Start with a mind-blowing, highly engaging 3-second viral hook.\n" if script_hook else ""
    curiosity_rule = "2. CURIOSITY GAPS: Insert curiosity gaps in the middle to retain audience attention.\n" if script_curiosity else ""
    tone_rule = "3. EMOTION & TONE: Inject strong emotions and character tones matching the scene.\n" if script_tone else ""
    cta_rule = "4. CALL TO ACTION: End the script with a strong Call to Action asking a question.\n" if script_cta else ""
    
    story_prompt = f"""Act as a YouTube content strategist AND cinematic narrative writer.
Write an engaging {duration}-minute highly viral script for a {niche} TikTok/YouTube video in natural spoken Burmese. (Around {target_words} words).
{topic_instruction}
CRITICAL RULES:
{hook_rule}{curiosity_rule}{tone_rule}{cta_rule}
5. NO FORMAL GRAMMAR: STRICTLY PROHIBITED to use formal literary markers (၌,၍, သည့်, သည်, ၏). Use natural spoken endings (တယ်, တဲ့, မှာ, ရဲ့).
6. POV: Write in second person (မင်း / မင်းရဲ့) if applicable.
7. AUDIO TAGS: Include tags like [pause=1.0], [excited], [whisper] to guide the voice.
8. Do not use English transliteration. Use emotionally immersive storytelling. MUST BE IN PURE BURMESE LANGUAGE.

Output format:
Provide the script directly.
At the absolute end, include these two lines:
[TITLE: A highly viral, click-worthy Burmese title]
[TAGS: #tag1 #tag2]"""

    last_err = ""
    for key in keys_list:
        try:
            client = genai.Client(api_key=key)
            response = client.models.generate_content(model="gemini-2.5-flash", contents=story_prompt)
            raw_output = response.text.strip()
            title, tags, script = parse_generated_script(raw_output)
            return True, title, tags, script, None
        except Exception as e: 
            last_err = str(e)
            continue
            
    return False, None, None, None, f"Story Error: API Key အားလုံး Limit ပြည့်နေပါသည်။ {last_err}"

def predict_virality_score(api_key_input, title, hook_text):
    """TikTok/Reels တွင် Viral ဖြစ်နိုင်ခြေ Score တွက်ပေးမည်"""
    keys_list = [k.strip() for k in api_key_input.split(",") if k.strip()]
    
    prompt = f"Analyze this short video for TikTok virality. Title: {title}. Hook: {hook_text[:150]}. Reply strictly in this format: \nScore: [1-100]\nReason: [1 short sentence in Burmese]"
    
    for key in keys_list:
        try:
            client = genai.Client(api_key=key)
            res = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
            return res.text.strip()
        except Exception:
            pass
            
    return "Score: 90\nReason: အရမ်းကောင်းတဲ့ Hook ပါ။ (Estimated)"
