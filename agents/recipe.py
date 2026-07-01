import os
from tavily import TavilyClient
from langchain_groq import ChatGroq
from state import AgentState

def get_recipe_from_tavily(dish_name: str) -> dict:
    """
    Queries Tavily to find recipe search results for the dish, then uses Groq LLM
    to generate a clean structured recipe (ingredients, quantities, step-by-step).
    """
    tavily_key = os.environ.get("TAVILY_API_KEY")
    groq_key = os.environ.get("GROQ_API_KEY")
    
    search_context = ""
    source_url = ""
    
    # 1. Search Tavily for the recipe if key exists
    if tavily_key:
        try:
            tavily = TavilyClient(api_key=tavily_key)
            query = f"standard recipe ingredients and preparation steps for {dish_name}"
            response = tavily.search(query=query, max_results=1)
            results = response.get("results", [])
            if results:
                search_context = results[0].get("content", "")
                source_url = results[0].get("url", "")
        except Exception as e:
            print(f"Tavily search error: {e}")
            
    # 2. Use Groq LLM to format/structure the recipe
    if not groq_key:
        return {
            "original_recipe": search_context if search_context else f"Standard recipe for {dish_name}.",
            "recipe_source_url": source_url
        }
        
    system_prompt = (
        "You are an expert chef. Your task is to write a clean, structured recipe for the requested dish. "
        "Use the provided search context and your own database of recipes. "
        "The recipe MUST be formatted cleanly in Markdown with exactly these two sections:\n"
        "### 🛒 Ingredients Required & Quantities\n"
        "- [Ingredient Name]: [Quantity/Measurement]\n\n"
        "### 🍳 Step-by-Step Instructions\n"
        "1. [Step 1]\n"
        "2. [Step 2]...\n"
        "Make sure ingredients have realistic portion/quantity measures. "
        "Do not include any conversational intro/outro text, just return the structured recipe."
    )
    
    user_prompt = f"Dish Name: {dish_name}\n"
    if search_context:
        user_prompt += f"Search snippet content: {search_context}"
        
    try:
        model_name = "llama-3.3-70b-versatile"
        llm = ChatGroq(temperature=0.2, model_name=model_name, api_key=groq_key)
        messages = [("system", system_prompt), ("user", user_prompt)]
        
        try:
            response = llm.invoke(messages)
        except Exception:
            fallback_llm = ChatGroq(temperature=0.2, model_name="llama-3.1-8b-instant", api_key=groq_key)
            response = fallback_llm.invoke(messages)
            
        return {
            "original_recipe": response.content.strip(),
            "recipe_source_url": source_url
        }
    except Exception as e:
        return {
            "original_recipe": f"Error generating recipe: {e}",
            "recipe_source_url": source_url
        }

def recipe_agent(state: AgentState) -> dict:
    """
    Recipe agent that queries Tavily and structures it into ingredients, quantities,
    and preparation instructions.
    """
    dish_name = state.get("dish_name")
    if not dish_name:
        return {"message": "No dish name provided for recipe agent."}
        
    recipe_info = get_recipe_from_tavily(dish_name)
    return {
        "original_recipe": recipe_info.get("original_recipe", ""),
        "recipe_source_url": recipe_info.get("recipe_source_url", "")
    }
