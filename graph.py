from langgraph.graph import StateGraph, END
from state import AgentState

# Import agents
from agents.calculator import calculator_agent
from agents.vision import vision_agent
from agents.nutrition import nutrition_agent
from agents.recipe import recipe_agent
from agents.advisor import advisor_agent

def route_start(state: AgentState) -> str:
    """
    Decides the initial agent node based on the operation status.
    """
    # Calibration flow
    if state.get("status") == "calibrate":
        return "calculator"
        
    # Analysis flow: if dish name is already provided (confirmed), run nutrition directly
    if state.get("dish_name"):
        return "nutrition"
        
    # Default is running vision analysis
    return "vision"

def route_post_vision(state: AgentState) -> str:
    """
    If vision confidence is low, we exit to let the user confirm.
    Otherwise we proceed directly to nutrition.
    """
    conf = float(state.get("vision_confidence", 0.0))
    if conf < 0.70:
        return END
    return "nutrition"

# Initialize graph builder
workflow = StateGraph(AgentState)

# Add agent nodes
workflow.add_node("calculator", calculator_agent)
workflow.add_node("vision", vision_agent)
workflow.add_node("nutrition", nutrition_agent)
workflow.add_node("recipe", recipe_agent)
workflow.add_node("advisor", advisor_agent)

# Set conditional entry point
workflow.set_conditional_entry_point(
    route_start,
    {
        "calculator": "calculator",
        "vision": "vision",
        "nutrition": "nutrition"
    }
)

# Connect nodes
workflow.add_edge("calculator", END)

workflow.add_conditional_edges(
    "vision",
    route_post_vision,
    {
        END: END,
        "nutrition": "nutrition"
    }
)

workflow.add_edge("nutrition", "recipe")
workflow.add_edge("recipe", "advisor")
workflow.add_edge("advisor", END)

# Compile graph
app_graph = workflow.compile()
