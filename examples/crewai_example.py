"""CrewAI governance example."""

from sidclaw import SidClaw
from sidclaw.middleware.crewai import govern_crewai_tool

client = SidClaw(
    api_key="ai_your_key_here",
    agent_id="agent-devops",
)

# Assuming you have a CrewAI tool:
# governed = govern_crewai_tool(my_tool, client=client)

print("CrewAI governance example — install crewai to run")
