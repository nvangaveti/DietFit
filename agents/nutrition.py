import os
import json
from state import AgentState
from utils.usda import get_nutrition
from langchain_groq import ChatGroq

def estimate_nutrition_with_llm(food_query: str) -> dict:
    """
    Uses Groq LLM to estimate the calories, protein, carbs, and fat
    for a food query when the USDA database has no match.
    """
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return {"food_name": food_query, "calories": 0, "protein": 0, "carbs": 0, "fat": 0}
        
    system_prompt = (
        "You are a professional nutrition database parser. "
        "Given a food item or dish name, estimate its average nutritional values per standard serving. "
        "You must respond ONLY with a JSON object. Do not include markdown formatting. "
        "The JSON object must have exactly these keys: \n"
        "- 'food_name': string (the common name of the dish)\n"
        "- 'calories': float (total calories in kcal)\n"
        "- 'protein': float (protein in grams)\n"
        "- 'carbs': float (carbohydrates in grams)\n"
        "- 'fat': float (total fat in grams)"
    )
    
    user_prompt = f"Estimate the nutritional macros for a standard serving of: {food_query}"
    
    try:
        model_name = "llama-3.3-70b-versatile"
        llm = ChatGroq(
            temperature=0.1,
            model_name=model_name,
            api_key=api_key,
            model_kwargs={"response_format": {"type": "json_object"}}
        )
        
        messages = [
            ("system", system_prompt),
            ("user", user_prompt)
        ]
        
        try:
            response = llm.invoke(messages)
        except Exception:
            # Fallback to 8b
            fallback_llm = ChatGroq(
                temperature=0.1,
                model_name="llama-3.1-8b-instant",
                api_key=api_key,
                model_kwargs={"response_format": {"type": "json_object"}}
            )
            response = fallback_llm.invoke(messages)
            
        content = response.content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            if lines[0].startswith("```json") or lines[0].startswith("```"):
                content = "\n".join(lines[1:-1])
        content = content.strip()
        
        result = json.loads(content)
        return {
            "food_name": result.get("food_name", food_query),
            "calories": float(result.get("calories", 0)),
            "protein": float(result.get("protein", 0)),
            "carbs": float(result.get("carbs", 0)),
            "fat": float(result.get("fat", 0))
        }
    except Exception as e:
        print(f"Error estimating macros with LLM: {e}")
        return {"food_name": food_query, "calories": 0, "protein": 0, "carbs": 0, "fat": 0}

def nutrition_agent(state: AgentState) -> dict:
    """
    Nutrition agent that looks up the macronutrients of the identified dish.
    Uses USDA database via API first, falling back to LLM estimation.
    """
    dish_name = state.get("dish_name")
    if not dish_name:
        return {"message": "No dish name provided for nutrition lookup."}
        
    macros = get_nutrition(dish_name)
    if macros.get("calories", 0) == 0:
        macros = estimate_nutrition_with_llm(dish_name)
        
    return {
        "dish_calories": float(macros.get("calories", 0.0)),
        "dish_protein": float(macros.get("protein", 0.0)),
        "dish_carbs": float(macros.get("carbs", 0.0)),
        "dish_fat": float(macros.get("fat", 0.0))
    }
