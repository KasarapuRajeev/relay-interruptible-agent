import unittest

from relay.impact import classify_impact, score_dependency
from relay.plans import ContextDiff


class ImpactEngineTests(unittest.TestCase):
    def test_semantic_cost_dependency_matches_budget_change(self):
        diff = ContextDiff.between({"budget": 70000}, {"budget": 55000})
        score, reason = score_dependency("price_search", diff)

        self.assertGreaterEqual(score, 0.9)
        self.assertIn("semantic concept", reason)

    def test_new_priority_value_impacts_battery_evidence(self):
        diff = ContextDiff.between(
            {"priority": "video editing"},
            {"priority": "battery life"},
        )
        decision = classify_impact(
            target_id="battery-review",
            target_type="evidence",
            dependencies=["battery_reviews"],
            context_diff=diff,
        )

        self.assertEqual(decision.action, "invalidate")
        self.assertGreaterEqual(decision.score, 0.7)
        self.assertEqual(decision.matched_dependencies, ["battery_reviews"])

    def test_unrelated_evidence_is_preserved_with_explanation(self):
        diff = ContextDiff.between({"budget": 70000}, {"budget": 55000})
        decision = classify_impact(
            target_id="screen-spec",
            target_type="evidence",
            dependencies=["display_resolution"],
            context_diff=diff,
        )

        self.assertEqual(decision.action, "preserve")
        self.assertEqual(decision.score, 0)
        self.assertIn("no material dependency", decision.reasons[0])

    def test_running_affected_step_is_cancelled_not_merely_invalidated(self):
        diff = ContextDiff.between({"destination": "Delhi"}, {"destination": "Jaipur"})
        decision = classify_impact(
            target_id="travel-call",
            target_type="plan_step",
            dependencies=["destination"],
            context_diff=diff,
            active=True,
        )

        self.assertEqual(decision.action, "cancel")
        self.assertEqual(decision.score, 1)


if __name__ == "__main__":
    unittest.main()
