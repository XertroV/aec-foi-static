import google.generativeai as genai
import os
from datetime import datetime

# Initialize Gemini API key from environment
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY environment variable not set.")

def generate_summary(text_content, prompt_template, model_name, max_output_tokens=None):
    """
    Generate a summary using Google Gemini API.
    Args:
        text_content (str): The text to summarize.
        prompt_template (str): The prompt template, should contain {text}.
        model_name (str): Gemini model name (e.g., 'gemini-2.5-flash').
        max_output_tokens (int, optional): Max tokens for output.
    Returns:
        str: The generated summary, or empty string on error.
    """
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(
            model_name,
            safety_settings={
                cat: genai.types.HarmBlockThreshold.BLOCK_NONE
                for cat in genai.types.HarmCategory
            }
        )
        prompt = prompt_template.format(text=text_content)
        gen_config = {}
        if max_output_tokens:
            gen_config['max_output_tokens'] = max_output_tokens
        response = model.generate_content(prompt, generation_config=gen_config)
        if not response or not hasattr(response, 'text'):
            print(f"[Gemini] No response or empty response for prompt.")
            return ""
        return response.text.strip()
    except ValueError as ve:
        print(f"[Gemini] ValueError: {ve}")
        return ""
    except Exception as e:
        print(f"[Gemini] Error: {e}")
        return ""
