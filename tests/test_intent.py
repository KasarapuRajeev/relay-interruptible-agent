import unittest

from relay.intent import understand


class IntentTests(unittest.TestCase):
    def test_extracts_travel_slots(self):
        update = understand(
            "Plan a 3-day trip to Delhi under ₹30,000", "unknown", {}
        )
        self.assertEqual(update.intent, "travel_planning")
        self.assertEqual(update.slots["destination"], "Delhi")
        self.assertEqual(update.slots["budget_inr"], 30000)
        self.assertEqual(update.slots["duration_days"], 3)

    def test_localized_correction(self):
        update = understand(
            "Actually change it to Jaipur under ₹20,000",
            "travel_planning",
            {"destination": "Delhi", "budget_inr": 30000, "duration_days": 3},
        )
        self.assertEqual(set(update.corrected_slots), {"destination", "budget_inr"})
        self.assertNotIn("duration_days", update.slots)

    def test_cancel_is_explicit(self):
        update = understand("Stop and forget it", "travel_planning", {})
        self.assertTrue(update.is_cancel)

    def test_cancelled_subject_with_replacement_is_a_new_instruction(self):
        update = understand(
            "Actually cancel cars. Compare electric scooters under ₹80,000.",
            "research",
            {"topic": "electric cars for college students"},
        )
        self.assertFalse(update.is_cancel)
        self.assertEqual(update.intent, "research")
        self.assertEqual(update.slots["topic"], "electric scooters under ₹80,000")
        self.assertEqual(update.slots["budget_inr"], 80000)
        self.assertIn("topic", update.corrected_slots)

    def test_weather_location_is_not_misclassified_as_travel(self):
        update = understand("What is the current weather in Bengaluru?", "unknown", {})
        self.assertEqual(update.intent, "weather_information")
        self.assertEqual(update.slots["location"], "Bengaluru")
        self.assertNotIn("destination", update.slots)

    def test_calculation_has_a_distinct_intent(self):
        update = understand("Calculate (1250 * 3) + 499", "unknown", {})
        self.assertEqual(update.intent, "calculation")
        self.assertEqual(update.slots["expression"], "(1250 * 3) + 499")

    def test_destination_correction_recovers_from_previous_general_message(self):
        update = understand(
            "Actually change it to Jaipur under ₹20,000",
            "general_assistance",
            {},
        )
        self.assertEqual(update.intent, "travel_planning")
        self.assertEqual(update.slots["destination"], "Jaipur")
        self.assertEqual(update.slots["budget_inr"], 20000)

    def test_research_topic_is_preserved_while_constraints_are_corrected(self):
        initial = understand("Research laptops under ₹70,000", "unknown", {})
        self.assertEqual(initial.intent, "research")
        self.assertEqual(initial.slots["topic"], "laptops under ₹70,000")

        correction = understand(
            "Actually under ₹55,000 and prioritize battery life",
            "research",
            {**initial.slots, "budget_inr": 70000},
        )
        self.assertEqual(correction.intent, "research")
        self.assertNotIn("topic", correction.slots)
        self.assertEqual(correction.slots["budget_inr"], 55000)
        self.assertEqual(correction.slots["priority"], "battery life")


if __name__ == "__main__":
    unittest.main()
