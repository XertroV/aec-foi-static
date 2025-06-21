from env_utils import load_env_var_from_dotenv
load_env_var_from_dotenv('GEMINI_API_KEY') # Assuming this loads the .env file

import google.generativeai as genai
import os
from datetime import datetime
# Explicitly import the necessary types for clarity
from google.generativeai.types import (
    HarmCategory,
    HarmBlockThreshold,
    SafetySetting,
)

# Initialize Gemini API key from environment
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY environment variable not set.")

def generate_summary(text_content, prompt_template, model_name, max_output_tokens=None, return_full_response=False):
    """
    Generate a summary using Google Gemini API.
    Args:
        text_content (str): The text to summarize.
        prompt_template (str): The prompt template, should contain {text}.
        model_name (str): Gemini model name (e.g., 'gemini-2.5-flash').
        max_output_tokens (int, optional): Max tokens for output.
        return_full_response (bool): If True, return (summary, raw_response) tuple.
    Returns:
        str or (str, dict): The generated summary, or (summary, raw_response) if requested.
    """
    try:
        genai.configure(api_key=GEMINI_API_KEY)

        # CORRECT WAY to set safety_settings:
        # Create a list of SafetySetting objects, each specifying a category and threshold.
        # This explicitly tells the API to BLOCK_NONE for all relevant categories.
        safety_settings = [
            SafetySetting(
                category=HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                threshold=HarmBlockThreshold.BLOCK_NONE,
            ),
            SafetySetting(
                category=HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                threshold=HarmBlockThreshold.BLOCK_NONE,
            ),
            SafetySetting(
                category=HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                threshold=HarmBlockThreshold.BLOCK_NONE,
            ),
            SafetySetting(
                category=HarmCategory.HARM_CATEGORY_HARASSMENT,
                threshold=HarmBlockThreshold.BLOCK_NONE,
            ),
            SafetySetting(
                category=HarmCategory.HARM_CATEGORY_CIVIC_INTEGRITY,
                threshold=HarmBlockThreshold.BLOCK_NONE,
            ),
            # Add any other categories you wish to explicitly set to BLOCK_NONE
            # For example, to unblock medical content if your data might contain it:
            # SafetySetting(
            #     category=HarmCategory.HARM_CATEGORY_MEDICAL,
            #     threshold=HarmBlockThreshold.BLOCK_NONE,
            # ),
        ]

        model = genai.GenerativeModel(
            model_name,
            safety_settings=safety_settings # Pass the correctly formatted list here
        )

        prompt = prompt_template.format(text=text_content)
        gen_config = {}
        if max_output_tokens is not None: # Use 'is not None' for clarity with potential 0
            gen_config['max_output_tokens'] = max_output_tokens

        response = model.generate_content(prompt, generation_config=gen_config)

        # Check for empty response or blocked content
        if not response or not hasattr(response, 'text') or not response.text:
            print(f"[Gemini] No response or empty response text for prompt.")
            return ("", {}) if return_full_response else ""

        if return_full_response:
            # Try to convert response to dict for saving
            try:
                raw = response.to_dict() if hasattr(response, 'to_dict') else str(response) # Fallback to str
            except Exception as e:
                print(f"[Gemini] Warning: Could not convert response to dict: {e}")
                raw = str(response)
            return response.text.strip(), raw
        return response.text.strip()
    except ValueError as ve:
        # This often catches cases where response.text is empty because content was blocked
        print(f"[Gemini] ValueError (likely content blocked or empty response): {ve}")
        return ("", {}) if return_full_response else ""
    except Exception as e:
        print(f"[Gemini] An unexpected error occurred: {e}")
        return ("", {}) if return_full_response else ""
