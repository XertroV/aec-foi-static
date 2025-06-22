from env_utils import load_env_var_from_dotenv
load_env_var_from_dotenv('GEMINI_API_KEY') # Assuming this loads the .env file

import google.generativeai as genai
import os
from datetime import datetime
import re, time

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
    prompt = None  # Always define prompt in this scope
    try:
        genai.configure(api_key=GEMINI_API_KEY)

        # Use string-based safety_settings for compatibility (removed problematic category)
        safety_settings = [
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            # Removed 'HARM_CATEGORY_CIVIC_INTEGRITY' due to API error
            # Add more categories as needed
        ]

        model = genai.GenerativeModel(
            model_name,
            safety_settings=safety_settings # Pass the list of dicts here
        )

        prompt = prompt_template.format(text=text_content)
        # Print the start of the prompt for transparency
        prompt_preview = prompt[:200].replace('\n', ' ')
        print(f"[LLM] Prompt start: {prompt_preview}{'...' if len(prompt) > 200 else ''}")

        gen_config = {}
        if max_output_tokens is not None: # Use 'is not None' for clarity with potential 0
            gen_config['max_output_tokens'] = max_output_tokens

        start_time = time.time()  # Start time for rate limiting
        response = model.generate_content(prompt, generation_config=gen_config)

        # Check for empty response or blocked content
        if not response or not hasattr(response, 'text') or not response.text:
            print(f"[Gemini] No response or empty response text for prompt.")
            if return_full_response:
                return ("", {"prompt": prompt})
            return ""

        # Wait based on the number of tokens used to avoid hitting 250k input tokens/minute limit.
        # Gemini's rate limit: 250,000 input tokens per minute per project.
        # Estimate input tokens as len(prompt.split()) * 1.3 (rough approximation for English).
        # Calculate required delay: delay = (tokens_used / 250_000) * 60 seconds
        tokens_used = int(len(prompt.split()) * 1.3)
        delay = (tokens_used / 250_000) * 60
        min_delay = 0.5  # Always wait at least 0.5s to avoid hammering the API
        delay = max(delay, min_delay)
        elapsed_time = time.time() - start_time
        delay = max(delay - elapsed_time, min_delay)  # Ensure we respect the minimum delay
        if delay < 0:
            print(f"[LLM] Warning: Calculated delay is negative ({delay:.2f}s), resetting to minimum delay of {min_delay:.2f}s.")
            delay = min_delay
        print(f"[LLM] Sleeping for {delay:.2f} seconds to respect token rate limits ({tokens_used} tokens used)...")
        time.sleep(delay)

        if return_full_response:
            # Try to convert response to dict for saving
            try:
                raw = response.to_dict() if hasattr(response, 'to_dict') else str(response) # Fallback to str
            except Exception as e:
                print(f"[Gemini] Warning: Could not convert response to dict: {e}")
                raw = str(response)
            # Always include the prompt in the raw response dict for transparency
            if isinstance(raw, dict):
                raw['prompt'] = prompt
            else:
                raw = {"raw_response": raw, "prompt": prompt}
            return response.text.strip(), raw
        return response.text.strip()
    except ValueError as ve:
        # This often catches cases where response.text is empty because content was blocked
        print(f"[Gemini] ValueError (likely content blocked or empty response): {ve}")
        if return_full_response:
            return ("", {"prompt": prompt if prompt else ''})
        return ""
    except Exception as e:
        # Check for retry_delay in Gemini API error message
        retry_delay = None
        # Try to extract retry_delay from error string (protobuf or dict)
        msg = str(e)
        match = re.search(r'retry_delay\s*\{\s*seconds:\s*(\d+)', msg)
        if not match:
            # Try to find '"retry_delay": {"seconds": N}'
            match = re.search(r'"retry_delay"\s*:\s*\{\s*"seconds"\s*:\s*(\d+)', msg)
        if match:
            retry_delay = int(match.group(1))
            retry_delay2 = retry_delay * 2 + 1
            print(f"[Gemini] API requested retry_delay: sleeping for min:{retry_delay} / actual:{retry_delay2} seconds...")
            time.sleep(retry_delay2)
        print(f"[Gemini] An unexpected error occurred: {e}")
        if return_full_response:
            return ("", {"prompt": prompt if prompt else ''})
        return ""
