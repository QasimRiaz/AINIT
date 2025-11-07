# agents.py

import os
from dotenv import load_dotenv
from typing import TypedDict
from langgraph.graph import StateGraph, END
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.pydantic_v1 import BaseModel, Field

# --- 1. SETUP (No changes) ---
load_dotenv()
llm = ChatGoogleGenerativeAI(model="gemini-2.5-pro",
                             google_api_key=os.getenv("GOOGLE_API_KEY"),
                             temperature=0.2,
                             convert_system_message_to_human=True)

# --- 2. AGENT STATE ---
# *** CHANGE: Renamed 'history_text' to 'conversation_history' for clarity ***
class TicketState(TypedDict):
    alert_type: str
    device_name: str
    issue_description: str
    conversation_history: str  # This will hold the device history OR the ongoing chat
    
    assigned_agent: str
    assignment_reason: str
    
    llm_questions: str | None
    llm_solution: str | None

# --- 3. AGENT NODES ---

# -- SUPERVISOR NODE (No changes to logic) --
class SupervisorOutput(BaseModel):
    agent: str = Field(description="The agent to assign. Options: [HighCpuAgent, HighMemoryAgent, ConnectivityAgent]")
    reason: str = Field(description="A short reason for the assignment.")

def supervisor_node(state: TicketState):
    """Analyzes the initial ticket and assigns a specialist."""
    print("---SUPERVISOR---")
    prompt = ChatPromptTemplate.from_template(
        """
        You are an intelligent Network Supervisor Agent. Assign new tickets to the correct specialist.
        Available specialists:
        - HighCpuAgent: For high CPU utilization.
        - HighMemoryAgent: For high memory usage.
        - ConnectivityAgent: For packet loss, latency, or routing issues.

        New ticket:
        - Alert Type: {alert_type}
        - Device Name: {device_name}
        - Issue Description: {issue_description}
        - Historical context: {conversation_history} 
        
        Task: Assign the most appropriate specialist. Respond with a JSON object.
        """
    )
    chain = prompt | llm.with_structured_output(SupervisorOutput)
    # The initial 'conversation_history' is the device's past ticket history
    response = chain.invoke({"alert_type": state["alert_type"], "device_name": state["device_name"], "issue_description": state["issue_description"], "conversation_history": state["conversation_history"]})
    print(f"Supervisor decided: Assign to {response.agent}. Reason: {response.reason}")
    state["assigned_agent"] = response.agent
    state["assignment_reason"] = response.reason
    return state

# -- SPECIALIST NODE (HIGH CPU AGENT) --
class SpecialistOutput(BaseModel):
    information_needed: bool = Field(description="True if you need more info from the user, false otherwise.")
    questions_for_user: str | None = Field(description="Specific questions for the user if more info is needed.")
    solution: str | None = Field(description="A detailed, step-by-step solution if you have enough info.")

# *** CHANGE: The prompt is now updated to handle ongoing conversations ***
def high_cpu_agent_node(state: TicketState):
    """Specialist for high CPU. Now considers the full conversation."""
    print("---HIGH CPU AGENT (CONVERSATIONAL)---")
    prompt = ChatPromptTemplate.from_template(
        """
        You are a senior network troubleshooting AI agent specialized in "High CPU Usage" issues.
        You are in an ongoing diagnostic conversation. Analyze the entire conversation and decide the next step.

        Initial Ticket Details:
        - Alert Type: {alert_type}
        - Device Name: {device_name}
        - Issue Description: {issue_description}

        --- CONVERSATION HISTORY ---
        {conversation_history}
        --- END OF HISTORY ---

        Your Task:
        1.  Review the ENTIRE conversation.
        2.  Based on the latest user reply, decide if you have enough information to propose a solution.
        3.  If you STILL need more information, set `information_needed` to true and ask NEW, follow-up questions. Do not repeat answered questions.
        4.  If you have enough information, set `information_needed` to false and provide a final, detailed resolution plan in the `solution` field.

        Respond with a JSON object.
        """
    )
    chain = prompt | llm.with_structured_output(SpecialistOutput)
    response = chain.invoke(state) # Pass the whole state, which includes the conversation
    if response.information_needed:
        print(f"HighCpuAgent: Needs more info. Asking: {response.questions_for_user}")
        state["llm_questions"] = response.questions_for_user
        state["llm_solution"] = None
    else:
        print(f"HighCpuAgent: Solution proposed: {response.solution}")
        state["llm_questions"] = None
        state["llm_solution"] = response.solution
    return state

# --- 4. ROUTER & GRAPH ASSEMBLY (No changes) ---
def router(state: TicketState):
    """This function is part of the initial workflow only."""
    print("---ROUTER---")
    assigned_agent = state.get("assigned_agent")
    if assigned_agent == "HighCpuAgent":
        return "HighCpuAgent"
    return "end"

workflow = StateGraph(TicketState)
workflow.add_node("Supervisor", supervisor_node)
workflow.add_node("HighCpuAgent", high_cpu_agent_node)
workflow.set_entry_point("Supervisor")
workflow.add_conditional_edges("Supervisor", router, {"HighCpuAgent": "HighCpuAgent", "end": END})
workflow.add_edge("HighCpuAgent", END)
agentic_workflow = workflow.compile()
print("✅ Conversational agentic workflow compiled successfully!")

# --- 5. WORKFLOW RUNNER HELPER FUNCTION ---
# *** CHANGE: Renamed function and updated state key for clarity ***
def run_initial_workflow(ticket_data: dict):
    """
    Takes the initial ticket data, runs the supervisor and first specialist pass.
    """
    initial_state = TicketState(
        alert_type=ticket_data.get("alert_type"),
        device_name=ticket_data.get("device_name"),
        issue_description=ticket_data.get("issue_description"),
        # For the first run, the 'conversation_history' IS the device's past ticket history
        conversation_history=ticket_data.get("history_text", "No history available."),
        assigned_agent="",
        assignment_reason="",
        llm_questions=None,
        llm_solution=None
    )
    final_state = agentic_workflow.invoke(initial_state)
    return final_state