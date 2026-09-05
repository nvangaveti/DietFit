"""Comprehensive Unit & Integration Tests for Non-Food Detection Safeguard.

Verifies:
1. utils.gemini.analyze_dish_image parses is_food correctly and handles non-food payloads safely.
2. agents.vision.vision_agent maps is_food into state.
3. graph.route_post_vision immediately terminates at END when is_food is False or confidence < 0.70.
4. graph.route_start routes directly to nutrition when dish_name override is provided.
5. End-to-end graph behavior with non-food detection and manual dish fallback.
"""

import sys
import os
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from state import AgentState
from utils.gemini import analyze_dish_image
from agents.vision import vision_agent
from graph import route_post_vision, route_start, app_graph, END


class TestNonFoodSafeguard(unittest.TestCase):

    @patch("utils.gemini.genai.GenerativeModel")
    @patch("utils.gemini.Image.open")
    def test_analyze_dish_image_non_food(self, mock_img_open, mock_gen_model):
        """Verify analyze_dish_image correctly parses is_food: false from Gemini."""
        mock_model_instance = MagicMock()
        mock_gen_model.return_value = mock_model_instance
        mock_response = MagicMock()
        mock_response.text = '{"is_food": false, "dish_name": null, "confidence": 0.0}'
        mock_model_instance.generate_content.return_value = mock_response

        res = analyze_dish_image("fake_non_food_path.jpg", user_id="test_user")
        self.assertFalse(res["is_food"])
        self.assertIsNone(res["dish_name"])
        self.assertEqual(res["confidence"], 0.0)

    @patch("utils.gemini.genai.GenerativeModel")
    @patch("utils.gemini.Image.open")
    def test_analyze_dish_image_valid_food(self, mock_img_open, mock_gen_model):
        """Verify analyze_dish_image correctly parses valid food response."""
        mock_model_instance = MagicMock()
        mock_gen_model.return_value = mock_model_instance
        mock_response = MagicMock()
        mock_response.text = '{"is_food": true, "dish_name": "Grilled Salmon", "confidence": 0.95}'
        mock_model_instance.generate_content.return_value = mock_response

        res = analyze_dish_image("fake_salmon_path.jpg", user_id="test_user")
        self.assertTrue(res["is_food"])
        self.assertEqual(res["dish_name"], "Grilled Salmon")
        self.assertEqual(res["confidence"], 0.95)

    @patch("agents.vision.analyze_dish_image")
    def test_vision_agent_state_mapping(self, mock_analyze):
        """Verify vision_agent propagates is_food to return state dict."""
        mock_analyze.return_value = {"is_food": False, "dish_name": None, "confidence": 0.0}
        state: AgentState = {"image_path": "random_object.jpg"}
        res = vision_agent(state)
        self.assertFalse(res["is_food"])
        self.assertEqual(res["vision_confidence"], 0.0)

        mock_analyze.return_value = {"is_food": True, "dish_name": "Chicken Curry", "confidence": 0.88}
        res_food = vision_agent(state)
        self.assertTrue(res_food["is_food"])
        self.assertEqual(res_food["dish_name"], "Chicken Curry")
        self.assertEqual(res_food["vision_confidence"], 0.88)

    def test_route_post_vision_safeguard(self):
        """Verify route_post_vision terminates graph when is_food is False or confidence is low."""
        # Non-food case -> Must return END
        non_food_state = {"is_food": False, "vision_confidence": 0.0, "dish_name": None}
        self.assertEqual(route_post_vision(non_food_state), END)

        # Low confidence food case -> Must return END
        low_conf_food_state = {"is_food": True, "vision_confidence": 0.55, "dish_name": "Stew"}
        self.assertEqual(route_post_vision(low_conf_food_state), END)

        # High confidence food case -> Must proceed to nutrition
        confident_food_state = {"is_food": True, "vision_confidence": 0.85, "dish_name": "Oatmeal"}
        self.assertEqual(route_post_vision(confident_food_state), "nutrition")

    def test_route_start_manual_dish_override(self):
        """Verify route_start routes directly to nutrition when manual dish name is provided."""
        override_state = {
            "status": "analyze",
            "dish_name": "Grilled Chicken Salad",
            "image_path": "photo.jpg"
        }
        self.assertEqual(route_start(override_state), "nutrition")

        initial_image_state = {
            "status": "analyze",
            "dish_name": None,
            "image_path": "photo.jpg"
        }
        self.assertEqual(route_start(initial_image_state), "vision")

    @patch("agents.vision.analyze_dish_image")
    def test_app_graph_non_food_execution_halts(self, mock_analyze):
        """Verify full app_graph execution stops immediately after vision when non-food is detected."""
        mock_analyze.return_value = {"is_food": False, "dish_name": None, "confidence": 0.0}
        
        input_state = {
            "status": "analyze",
            "email": "user@dietfit.ai",
            "goal": "lose_fat",
            "diet_type": "balanced",
            "calorie_target": 2000.0,
            "protein_target": 150.0,
            "carb_target": 200.0,
            "fat_target": 70.0,
            "image_path": "mock_chair.jpg"
        }
        
        result_state = app_graph.invoke(input_state)
        # Should have run vision but halted before nutrition
        self.assertFalse(result_state.get("is_food"))
        self.assertEqual(result_state.get("vision_confidence"), 0.0)
        self.assertIsNone(result_state.get("dish_calories"))
        self.assertIsNone(result_state.get("adjusted_recipe"))
        self.assertIsNone(result_state.get("verdict"))


if __name__ == "__main__":
    unittest.main()
