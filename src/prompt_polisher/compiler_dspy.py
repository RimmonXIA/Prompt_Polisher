from __future__ import annotations

try:
    import dspy
except ImportError:
    dspy = None


class DraftCompile(dspy.Signature):
    """Compiles a raw user prompt into a highly structured, hardened prompt draft."""

    raw_prompt = dspy.InputField(desc="The original string intent from the user")
    radar_analysis = dspy.InputField(desc="JSON string containing threat and routing analysis")

    draft = dspy.OutputField(
        desc=(
            "The final compiled prompt string using XML sandboxing, "
            "U-shape attention layout, and few-shot examples."
        )
    )


class DraftCritic(dspy.Signature):
    """Audits the compiled draft to ensure structural and linguistic integrity."""

    draft = dspy.InputField(desc="The compiled draft prompt")
    original_intent = dspy.InputField(desc="The original intent")

    passed = dspy.OutputField(
        desc="Boolean indicating if it passes structural constraints", prefix="Passed:"
    )
    feedback = dspy.OutputField(
        desc="Actionable feedback if it failed. Empty if it passed.", prefix="Feedback:"
    )


class DSPyCompilerModule(dspy.Module):
    def __init__(self):
        super().__init__()
        self.compile = dspy.Predict(DraftCompile)
        self.critic = dspy.Predict(DraftCritic)

    def forward(self, raw_prompt: str, radar_analysis: str):
        compile_out = self.compile(raw_prompt=raw_prompt, radar_analysis=radar_analysis)
        critic_out = self.critic(draft=compile_out.draft, original_intent=raw_prompt)

        return dspy.Prediction(
            draft=compile_out.draft, passed=critic_out.passed, feedback=critic_out.feedback
        )


def is_dspy_available() -> bool:
    return dspy is not None
