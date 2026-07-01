from state import AgentState

def calculate_user_targets(weight: float, height: float, age: int, gender: str, activity: str, goal: str, diet: str) -> dict:
    """
    Calculates BMR (using Mifflin-St Jeor) and TDEE based on activity multiplier.
    Adjusts calorie targets based on the fitness goal and splits macros
    (protein, carbs, fat) based on the chosen diet type.
    """
    # 1. BMR calculation
    if gender.lower() == "male":
        bmr = 10 * weight + 6.25 * height - 5 * age + 5
    else:
        bmr = 10 * weight + 6.25 * height - 5 * age - 161
        
    # 2. Activity multiplier
    multipliers = {
        "sedentary": 1.2,
        "lightly active": 1.375,
        "moderately active": 1.55,
        "very active": 1.725,
        "extra active": 1.9,
        "lightly_active": 1.375,
        "moderately_active": 1.55,
        "very_active": 1.725,
        "extra_active": 1.9
    }
    multiplier = multipliers.get(activity.lower(), 1.2)
    tdee = bmr * multiplier
    
    # 3. Goal adjustment
    if goal.lower() in ["lose_fat", "lose fat"]:
        calorie_target = tdee - 500
    elif goal.lower() in ["build_muscle", "build muscle"]:
        calorie_target = tdee + 300
    else:
        calorie_target = tdee
        
    calorie_target = max(calorie_target, 1200.0)
    
    # 4. Diet type macro distribution
    diet_macros = {
        "vegan": (0.50, 0.20, 0.30),
        "keto": (0.05, 0.25, 0.70),
        "balanced": (0.40, 0.30, 0.30),
        "low carb": (0.20, 0.40, 0.40),
        "low_carb": (0.20, 0.40, 0.40)
    }
    carb_pct, protein_pct, fat_pct = diet_macros.get(diet.lower(), (0.40, 0.30, 0.30))
    
    carb_target = (calorie_target * carb_pct) / 4.0
    protein_target = (calorie_target * protein_pct) / 4.0
    fat_target = (calorie_target * fat_pct) / 9.0
    
    return {
        "goal": goal,
        "diet_type": diet,
        "weight_kg": weight,
        "height_cm": height,
        "age": age,
        "gender": gender.lower(),
        "activity_level": activity.lower(),
        "calorie_target": round(calorie_target, 1),
        "protein_target": round(protein_target, 1),
        "carb_target": round(carb_target, 1),
        "fat_target": round(fat_target, 1)
    }

def calculator_agent(state: AgentState) -> dict:
    """
    Agent that processes user inputs to output customized daily calorie & macro targets.
    """
    targets = calculate_user_targets(
        weight=float(state.get("weight_kg", 70.0)),
        height=float(state.get("height_cm", 170.0)),
        age=int(state.get("age", 25)),
        gender=state.get("gender", "male"),
        activity=state.get("activity_level", "sedentary"),
        goal=state.get("goal", "maintain"),
        diet=state.get("diet_type", "balanced")
    )
    return {
        "calorie_target": targets["calorie_target"],
        "protein_target": targets["protein_target"],
        "carb_target": targets["carb_target"],
        "fat_target": targets["fat_target"]
    }
