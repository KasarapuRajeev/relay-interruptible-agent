import unittest

from relay.plans import ContextDiff, PlanBranch
from relay.tasks import TaskManager, TaskRecord


class ContextDiffTests(unittest.TestCase):
    def test_classifies_changed_added_removed_and_preserved_values(self):
        diff = ContextDiff.between(
            {"budget": 70000, "priority": "editing", "country": "India", "os": "Windows"},
            {"budget": 55000, "priority": "battery", "country": "India", "ram": "16GB"},
        )

        self.assertEqual(diff.changed["budget"], {"old": 70000, "new": 55000})
        self.assertEqual(diff.changed["priority"], {"old": "editing", "new": "battery"})
        self.assertEqual(diff.preserved, {"country": "India"})
        self.assertEqual(diff.added, {"ram": "16GB"})
        self.assertEqual(diff.removed, {"os": "Windows"})


class PlanBranchTests(unittest.TestCase):
    def test_fork_preserves_only_completed_steps_unaffected_by_context_change(self):
        parent = PlanBranch.initial(
            "Find a laptop under 70000",
            {"budget": 70000, "country": "India"},
        )
        product_step = parent.add_tool_step(
            "fetch_specs", "spec-call", {"country": "India"}
        )
        product_step.status = "completed"
        price_step = parent.add_tool_step(
            "search_prices", "price-call", {"budget": 70000}
        )
        price_step.status = "completed"

        child = parent.fork(
            "Keep it under 55000",
            {"budget": 55000, "country": "India"},
        )

        self.assertEqual(parent.status, "superseded")
        self.assertEqual(child.number, 2)
        self.assertEqual(child.parent_branch_id, parent.branch_id)
        self.assertEqual(child.context_diff.changed["budget"]["new"], 55000)
        self.assertEqual(
            child.context_diff.changed["goal"],
            {"old": "Find a laptop under 70000", "new": "Keep it under 55000"},
        )
        self.assertEqual([step.tool_name for step in child.steps], ["fetch_specs"])
        self.assertEqual(child.steps[0].status, "preserved")


class EvidenceDependencyTests(unittest.TestCase):
    def test_goal_only_change_invalidates_prior_generic_evidence(self):
        task = TaskRecord(
            task_id="task-general",
            intent="general_assistance",
            slots={},
        )
        task.start_branch("What is the weather in Delhi?")
        weather = task.add_evidence(
            call_id="weather-call",
            source="get_current_weather",
            content={"summary": "Delhi weather"},
            depends_on=["location"],
        )

        task.start_branch("What is the weather in Mumbai?")
        invalidated = task.reconcile_evidence()

        self.assertEqual(invalidated, 1)
        self.assertEqual(weather.status, "invalidated")
        self.assertEqual(task.active_grounded_results(), [])

    def test_replan_preserves_unaffected_evidence_and_invalidates_affected_evidence(self):
        task = TaskRecord(
            task_id="task-1",
            intent="product_research",
            slots={"budget": 70000, "country": "India"},
        )
        first = task.start_branch("Find a laptop under 70000")
        specs = task.add_evidence(
            call_id="spec-call",
            source="fetch_specs",
            content={"summary": "16 GB RAM"},
            depends_on=["country"],
        )
        price = task.add_evidence(
            call_id="price-call",
            source="search_prices",
            content={"summary": "Price is 68000"},
            depends_on=["budget"],
        )

        task.slots["budget"] = 55000
        second = task.start_branch("Keep it under 55000")
        invalidated = task.reconcile_evidence()

        self.assertEqual(invalidated, 1)
        self.assertEqual(specs.status, "preserved")
        self.assertIn(second.branch_id, specs.valid_branch_ids)
        self.assertEqual(price.status, "invalidated")
        self.assertEqual(price.invalidated_in_branch_id, second.branch_id)
        grounded = task.active_grounded_results()
        self.assertEqual([item["summary"] for item in grounded], ["16 GB RAM"])
        self.assertEqual(first.status, "superseded")

    def test_paused_task_evidence_is_isolated_and_restored_on_resume(self):
        manager = TaskManager()
        travel, _ = manager.activate(
            "travel_planning",
            {"destination": "Delhi"},
            request_text="Plan Delhi",
        )
        travel.add_evidence(
            call_id="travel-call",
            source="search_travel",
            content={"summary": "Delhi evidence"},
            depends_on=["destination"],
        )
        manager.pause_active()

        study, _ = manager.activate(
            "study_planning",
            {"subject": "databases"},
            request_text="Study databases",
        )
        self.assertEqual(study.active_grounded_results(), [])
        self.assertEqual(travel.active_grounded_results()[0]["summary"], "Delhi evidence")
        manager.pause_active()

        resumed, was_resumed = manager.activate(
            "travel_planning",
            {},
            request_text="Resume trip",
        )
        self.assertTrue(was_resumed)
        self.assertEqual(resumed.task_id, travel.task_id)
        self.assertEqual(resumed.active_grounded_results()[0]["summary"], "Delhi evidence")
