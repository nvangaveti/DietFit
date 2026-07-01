import os
import requests
from dotenv import load_dotenv
load_dotenv()
def get_nutrition(food_query: str) -> dict:
    try:
        # ALL of this inside try
        url = "https://api.nal.usda.gov/fdc/v1/foods/search"
        params = {
            "query": food_query,
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
        print(f"USDA API error: {e}")
        return {"food_name": food_query, "calories": 0, "protein": 0, "carbs": 0, "fat": 0}
# if __name__ == "__main__":
#     print(get_nutrition("100g grilled chicken"))
