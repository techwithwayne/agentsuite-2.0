# agentsuite/personal_mentor/tools.py
from typing import Dict, Any, List

def make_mini_plan(goal: str) -> Dict[str, Any]:
    """Return a tiny, momentum-first plan."""
    plan = [
        f"Clarify the goal: {goal}",
        "Break into 3 concrete tasks you can do in 25 minutes each.",
        "Ship a tiny version today; iterate tomorrow.",
    ]
    motivation = "You’ve got this. Small wins compound fast."
    return {"goal": goal, "plan": plan, "motivation": motivation}

TOOL_SPEC: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "make_mini_plan",
            "description": "Create a short, energized mini-plan that pushes the user into action.",
            "parameters": {
                "type": "object",
                "properties": {
                    "goal": {
                        "type": "string",
                        "description": "User goal in one line, e.g., 'Ship the MVP landing page.'"
                    },
                },
                "required": ["goal"],
                "additionalProperties": False,
            },
        },
    }
]

TOOL_FUNCTIONS = {
    "make_mini_plan": make_mini_plan,
}
