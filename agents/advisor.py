import os
import json
from langchain_groq import ChatGroq
from state import AgentState

def get_diet_advice(profile: dict, dish_macros: dict, original_recipe: str, recipe_source_url: str = "") -> dict:
    """
    Uses Groq LLM to check if a dish fits the user's target macros,
    suggesting substitutions and portion adjustments.
    """
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return {
            "verdict": "Modification recommended",
            "adjusted_recipe": "Unable to calculate adjustment: Groq API Key missing.",
            "explanation": "Please add GROQ_API_KEY to your environment."
        }
        
    goal = profile.get("goal", "maintain")
    diet = profile.get("diet_type", "balanced")
    cal_target = profile.get("calorie_target", 2000.0)
    prot_target = profile.get("protein_target", 150.0)
    carb_target = profile.get("carb_target", 200.0)
    fat_target = profile.get("fat_target", 70.0)
    
    dish_name = dish_macros.get("food_name", "dish")
    dish_cal = dish_macros.get("calories", 0)
    dish_prot = dish_macros.get("protein", 0)
    dish_carb = dish_macros.get("carbs", 0)
    dish_fat = dish_macros.get("fat", 0)
    
    system_prompt = (
        "You are an expert sports nutritionist and chef. Your task is to analyze a food dish and its recipe, "
        "and determine if it fits the user's daily nutritional targets and dietary preferences. "
        "You must adjust the recipe's portion size or swap ingredients to optimize the alignment with the user's targets. "
        "Compare the macros of one serving of this dish to the user's DAILY macro targets. "
        "If a standard serving size of the dish is way too high in calories or carbs/fat for their diet (e.g. Keto, Vegan), "
        "propose a scaled portion size (e.g. 'Eat 60% of a standard portion') or substitute ingredients (e.g. 'Swap white rice for cauliflower rice'). "
        "Be specific with the math. Show the calculated macros of both the original dish and the adjusted dish. "
        "You must respond ONLY with a JSON object. Do not include any markdown styling (like ```json) in your response, just return the raw JSON string. "
        "The JSON object must have exactly these keys: \n"
        "- 'verdict': either 'Fits your diet' or 'Modification recommended'\n"
        "- 'adjusted_recipe': markdown text outlining the new portions or ingredient substitutions and the adjusted recipe steps. "
        "At the end of the recipe steps, you MUST add a new line providing a link to visit the recipe site. For example: "
        "'[🔗 Visit Recipe Source Site](URL)' where URL is the RECIPE SOURCE URL provided in the prompt. "
        "If no URL is provided or if the URL is empty, please state '[🔗 Visit Recipe Source Site](No URL provided)'.\n"
        "- 'explanation': a paragraph explaining your analysis, comparing the original dish macros with the user's daily goals, and justifying the adjustments.\n"
        "- 'original_dish_macros': a string summarizing the original macros (calories, protein, carbs, fat).\n"
        "- 'adjusted_dish_macros': a string summarizing the adjusted macros (calories, protein, carbs, fat)."
    )
    
    user_prompt = f"""
    USER PROFILE:
    - Goal: {goal}
    - Diet Type: {diet}
    - Daily Targets: {cal_target} kcal | Protein: {prot_target}g | Carbs: {carb_target}g | Fat: {fat_target}g
    
    DISH & MACROS (typically per 100g or standard serving in USDA database):
    - Dish Name: {dish_name}
    - Calories: {dish_cal} kcal
    - Protein: {dish_prot}g
    - Carbs: {dish_carb}g
    - Fat: {dish_fat}g
    
    ORIGINAL RECIPE DETAILS / SEARCH RESULT:
    {original_recipe}
    
    RECIPE SOURCE URL:
    {recipe_source_url}
    """
    
    try:
        model_name = "llama-3.3-70b-versatile"
        llm = ChatGroq(
            temperature=0.2,
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
            fallback_llm = ChatGroq(
                temperature=0.2,
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
        orig_m = result.get("original_dish_macros", f"{dish_cal} kcal, P: {dish_prot}g, C: {dish_carb}g, F: {dish_fat}g")
        adj_m = result.get("adjusted_dish_macros", "Adjusted macros details in recipe")
        explanation = result.get("explanation", "")
        
        full_explanation = (
            f"{explanation}\n\n"
            f"**Original Recipe Macros:** {orig_m}\n\n"
            f"**Adjusted Recipe Macros:** {adj_m}"
        )
        
        return {
            "verdict": result.get("verdict", "Modification recommended"),
            "adjusted_recipe": result.get("adjusted_recipe", "Eat standard portions."),
            "explanation": full_explanation
        }
    except Exception as e:
        return {
            "verdict": "Modification recommended",
            "adjusted_recipe": f"Error running advisor LLM: {e}",
            "explanation": "No explanation available due to model or processing errors."
        }

def advisor_agent(state: AgentState) -> dict:
    """
    Advisor agent that evaluates profiles, macro targets, and original recipes
    to yield personalized recipes and macro adjustments.
    """
    profile = {
        "goal": state.get("goal", "maintain"),
        "diet_type": state.get("diet_type", "balanced"),
        "calorie_target": float(state.get("calorie_target", 2000.0)),
        "protein_target": float(state.get("protein_target", 150.0)),
        "carb_target": float(state.get("carb_target", 200.0)),
        "fat_target": float(state.get("fat_target", 70.0))
    }
    
    dish_macros = {
        "food_name": state.get("dish_name", "dish"),
        "calories": float(state.get("dish_calories", 0.0)),
        "protein": float(state.get("dish_protein", 0.0)),
        "carbs": float(state.get("dish_carbs", 0.0)),
        "fat": float(state.get("dish_fat", 0.0))
    }
    
    original_recipe = state.get("original_recipe", "")
    recipe_source_url = state.get("recipe_source_url", "")
    
    advice = get_diet_advice(profile, dish_macros, original_recipe, recipe_source_url)
    return {
        "verdict": advice.get("verdict", "Modification recommended"),
        "adjusted_recipe": advice.get("adjusted_recipe", ""),
        "explanation": advice.get("explanation", "")
    }
