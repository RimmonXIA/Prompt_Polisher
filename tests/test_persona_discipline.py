from __future__ import annotations

import asyncio

from prompt_polisher.config import get_settings
from prompt_polisher.llm import FakeLLMClient
from prompt_polisher.nodes import node_red_team_critic


def test_critic_rejects_first_person_in_task_context(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    get_settings.cache_clear()
    settings = get_settings()
    
    # Mock LLM returning passed=True initially, but we are testing if the REAL critic
    # prompt logic (which we've updated) would lead a model to reject.
    # Since we are testing node_red_team_critic via FakeLLMClient,
    # we have to simulate the CRITIC'S OUTPUT.
    
    # Scenario: The artifact contains "I will analyze" in task_context.
    # We expect node_red_team_critic to reflect the auditor persona.
    
    # Case 1: First person leakage in task_context
    bad_draft = """
<task_context>
I am preparing to analyze this project so I can generate a resume for you.
</task_context>
<system_constraints>
1. You must be professional.
</system_constraints>
<user_input>
help me.
</user_input>
    """
    
    leak_msg = (
        '{"passed": false, "feedback": "Identity Loop violation: <task_context> contains '
        'first-person pronouns (I am...).", "verification_steps": []}'
    )
    llm = FakeLLMClient([leak_msg])

    state = {
        "raw_prompt": "help me.",
        "compiler_draft": bad_draft,
        "red_team_critic_iterations": 0,
    }
    out = asyncio.run(node_red_team_critic(state, llm, settings))
    
    assert out["red_team_critic_passed"] is False
    assert "Identity Loop" in out["red_team_critic_feedback"]

def test_critic_allows_first_person_in_user_input(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    get_settings.cache_clear()
    settings = get_settings()
    
    # Scenario: "I" is in user_input (quoted from author), but task_context is 3rd person.
    good_draft = """
<task_context>
The system analyzes the repository based on user requests.
</task_context>
<system_constraints>
You are an AI assistant.
</system_constraints>
<user_input>
I want you to fix my code.
</user_input>
    """
    
    # A disciplined critic should PASS this.
    llm = FakeLLMClient(['{"passed": true, "feedback": "", "verification_steps": []}'])
    
    state = {
        "raw_prompt": "I want you to fix my code.",
        "compiler_draft": good_draft,
        "red_team_critic_iterations": 0,
    }
    out = asyncio.run(node_red_team_critic(state, llm, settings))
    
    assert out["red_team_critic_passed"] is True

def test_critic_rejects_orchestrator_leakage_in_constraints(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    get_settings.cache_clear()
    settings = get_settings()
    
    # Scenario: Orchestrator leaks into constraints
    leaky_draft = """
<task_context>
The goal is to help the user.
</task_context>
<system_constraints>
1. As the Orchestrator, I have prepared these instructions for you.
2. You must follow them.
</system_constraints>
<user_input>
go.
</user_input>
    """
    
    leak_msg = (
        '{"passed": false, "feedback": "Leakage violation: Orchestrator-internal commentary '
        'found in constraints.", "verification_steps": []}'
    )
    llm = FakeLLMClient([leak_msg])

    state = {
        "raw_prompt": "go.",
        "compiler_draft": leaky_draft,
        "red_team_critic_iterations": 0,
    }
    out = asyncio.run(node_red_team_critic(state, llm, settings))
    
    assert out["red_team_critic_passed"] is False
    assert "Leakage" in out["red_team_critic_feedback"]
