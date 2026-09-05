import os
import json
import google.generativeai as genai
from PIL import Image
from utils.ratelimit import check_abuse_limit, record_abuse_call, RateLimitExceeded
from utils.security_logger import log_security_event, EVENT_API_ERROR, EVENT_ABUSE_THROTTLED

def analyze_dish_image(image_input, user_id: str = "anonymous") -> dict:
    """
    Uses Gemini Flash to analyze an image, classifying whether it is a food dish,
    and returning the dish name and confidence score.
    Returns: {"is_food": bool, "dish_name": Optional[str], "confidence": float}
    """
    if not user_id or user_id == "anonymous":
        try:
            import streamlit as st
            if hasattr(st, "user") and getattr(st.user, "email", None):
                user_id = st.user.email
        except Exception:
            pass
    clean_user = str(user_id).strip().lower() if user_id else "anonymous"
    rate_limit_key = f"{clean_user}:gemini_vision"

    # Enforce AI generation rate limits & abuse prevention per user
    allowed, cooldown = check_abuse_limit("ai_generation", rate_limit_key)
    if not allowed:
        log_security_event(
            event_type=EVENT_ABUSE_THROTTLED,
            severity="WARNING",
            actor=clean_user,
            action_taken="THROTTLE",
            resource=rate_limit_key,
            details={"cooldown": cooldown}
        )
        print(f"Gemini Vision Rate Limit Exceeded for {clean_user}: Cooldown active for {cooldown}s")
        return {"is_food": False, "dish_name": "Rate Limited (Please wait)", "confidence": 0.0, "rate_limited": True}

    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY not found in environment variables")
    
    genai.configure(api_key=api_key)
    record_abuse_call("ai_generation", rate_limit_key)
    
    # Use gemini-2.5-flash for maximum stability and support.
    model = genai.GenerativeModel('gemini-2.5-flash')
    
    try:
        image = Image.open(image_input)
        prompt = (
            "Examine this image carefully.\n"
            "1. Determine whether the image contains a food dish or edible meal.\n"
            "2. If it contains a food dish, set 'is_food' to true, identify the common name of the dish in 'dish_name', "
            "and set your confidence score (0.0 to 1.0) in 'confidence'.\n"
            "3. If it does NOT contain any food or meal (e.g., random objects, scenery, text, screenshots, humans, animals, electronics), "
            "set 'is_food' to false, 'dish_name' to null, and 'confidence' to 0.0.\n\n"
            "Respond ONLY with a JSON object containing:\n"
            "- 'is_food': boolean (true or false)\n"
            "- 'dish_name': string or null\n"
            "- 'confidence': float between 0.0 and 1.0"
        )
        
        response = model.generate_content(
            [prompt, image],
            generation_config={
                "response_mime_type": "application/json",
                "temperature": 0.0
            }
        )
        
        result = json.loads(response.text)
        is_food = bool(result.get("is_food", True))
        dish_name = result.get("dish_name")
        conf = float(result.get("confidence", 0.5 if is_food else 0.0))

        if not is_food or not dish_name:
            return {
                "is_food": False,
                "dish_name": None,
                "confidence": 0.0
            }

        return {
            "is_food": True,
            "dish_name": str(dish_name),
            "confidence": conf
        }
    except Exception as e:
        log_security_event(
            event_type=EVENT_API_ERROR,
            severity="ERROR",
            actor="system",
            action_taken="FALLBACK",
            resource="gemini_vision",
            details={"error": str(e)}
        )
        print(f"Gemini Vision API error: {e}")
        return {"is_food": False, "dish_name": "Unknown Dish", "confidence": 0.0}

if __name__ == "__main__":
    # Test stub
    import sys
    if len(sys.argv) > 1:
        img_path = sys.argv[1]
        print(f"Analyzing {img_path}...")
        print(analyze_dish_image(img_path))
    else:
        print("Please provide an image path to test.")

def generate_llm_text(prompt: str, system_prompt: str = "", json_mode: bool = False, user_id: str = "anonymous") -> str:
    """
    General text generation using Gemini Flash (gemini-2.5-flash).
    """
    if not user_id or user_id == "anonymous":
        try:
            import streamlit as st
            if hasattr(st, "user") and getattr(st.user, "email", None):
                user_id = st.user.email
        except Exception:
            pass
    clean_user = str(user_id).strip().lower() if user_id else "anonymous"
    rate_limit_key = f"{clean_user}:gemini_llm"
    
    # Enforce AI generation rate limits & abuse prevention per user
    allowed, cooldown = check_abuse_limit("ai_generation", rate_limit_key)
    if not allowed:
        log_security_event(
            event_type=EVENT_ABUSE_THROTTLED,
            severity="WARNING",
            actor=clean_user,
            action_taken="THROTTLE",
            resource=rate_limit_key,
            details={"cooldown": cooldown}
        )
        print(f"Gemini LLM Rate Limit Exceeded for {clean_user}: Cooldown active for {cooldown}s")
        raise RateLimitExceeded("ai_generation", cooldown, f"AI generation throttled. Retry after {cooldown}s.")

    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY not found in environment variables")
    
    genai.configure(api_key=api_key)
    record_abuse_call("ai_generation", rate_limit_key)
    model = genai.GenerativeModel('gemini-2.5-flash')
    
    full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
    config = {"temperature": 0.0}
    if json_mode:
        config["response_mime_type"] = "application/json"
    
    response = model.generate_content(full_prompt, generation_config=config)
    return response.text.strip()

