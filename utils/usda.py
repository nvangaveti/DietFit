import os
import requests
from dotenv import load_dotenv
from utils.validation import sanitize_for_prompt
from utils.ratelimit import check_abuse_limit, record_abuse_call
from utils.security_logger import log_security_event, EVENT_API_ERROR, EVENT_ABUSE_THROTTLED
load_dotenv()

def get_nutrition(food_query: str, user_id: str = "anonymous") -> dict:
    try:
        if not user_id or user_id == "anonymous":
            try:
                import streamlit as st
                if hasattr(st, "user") and getattr(st.user, "email", None):
                    user_id = st.user.email
            except Exception:
                pass
        clean_user = str(user_id).strip().lower() if user_id else "anonymous"
        rate_limit_key = f"{clean_user}:usda_endpoint"

        # Enforce external API rate limit and abuse defense per user
        is_allowed, cooldown = check_abuse_limit("api_query", rate_limit_key)
        if not is_allowed:
            log_security_event(
                event_type=EVENT_ABUSE_THROTTLED,
                severity="WARNING",
                actor=clean_user,
                action_taken="THROTTLE",
                resource=rate_limit_key,
                details={"cooldown": cooldown, "query": food_query}
            )
            print(f"USDA API Rate Limit Exceeded for {clean_user}: Cooldown active for {cooldown}s")
            return {"food_name": food_query, "calories": 0, "protein": 0, "carbs": 0, "fat": 0, "rate_limited": True}

        # Sanitize query to prevent parameter tampering or injection
        clean_query = sanitize_for_prompt(food_query, max_length=120)
        if not clean_query:
            return {"food_name": "unknown", "calories": 0, "protein": 0, "carbs": 0, "fat": 0}
            
        record_abuse_call("api_query", rate_limit_key)
        url = "https://api.nal.usda.gov/fdc/v1/foods/search"
        params = {
            "query": clean_query,
            "api_key": os.environ.get("USDA_API_KEY"),
            "pageSize": 1
        }
        response = requests.get(url, params = params)
        data = response.json()
        food = data["foods"][0]
        nutrients = food["foodNutrients"]
        
        calories = 0
        protein = 0
        carbs = 0
        fat = 0
        
        for nutrient in nutrients:
            name = nutrient.get("nutrientName", "")
            value = nutrient.get("value", 0)
            if name == "Energy":
                calories = value
            elif name == "Protein":
                protein = value
            elif name == "Carbohydrate, by difference":      
                carbs = value
            elif name == "Total lipid (fat)":      
                fat = value
        
        return {
            "food_name": food["description"],
            "calories": calories,
            "protein": protein,
            "carbs": carbs,
            "fat": fat
        }
    
    except Exception as e:
        log_security_event(
            event_type=EVENT_API_ERROR,
            severity="ERROR",
            actor="system",
            action_taken="FALLBACK",
            resource="usda_endpoint",
            details={"error": str(e), "food_query": food_query}
        )
        print(f"USDA API error: {e}")
        return {"food_name": food_query, "calories": 0, "protein": 0, "carbs": 0, "fat": 0}
# if __name__ == "__main__":
#     print(get_nutrition("100g grilled chicken"))
