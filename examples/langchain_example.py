"""LangChain governance example."""

from sidclaw import SidClaw
from sidclaw.middleware.langchain import govern_tools

client = SidClaw(
    api_key="ai_your_key_here",
    agent_id="agent-customer-support",
)

# Assuming you have LangChain tools defined:
# from langchain_community.tools import DuckDuckGoSearchRun
# search = DuckDuckGoSearchRun()
# governed = govern_tools([search], client=client)
# agent = create_react_agent(llm, governed)

print("LangChain governance example — install langchain-core to run")
