# agents.py

import os
from dotenv import load_dotenv
from typing import TypedDict
from langgraph.graph import StateGraph, END
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.pydantic_v1 import BaseModel, Field

# --- 1. SETUP ---
load_dotenv()

# Using Gemini 1.5 Flash as it is fast and cost-effective for this type of task.
llm = ChatGoogleGenerativeAI(model="gemini-2.5-pro",
                             google_api_key=os.getenv("GOOGLE_API_KEY"),
                             temperature=0.2,
                             convert_system_message_to_human=True)

# --- 2. AGENT STATE (The Workflow's Memory) ---
class TicketState(TypedDict):
    """Represents the state of a ticket as it moves through the AI workflow."""
    alert_type: str
    device_name: str
    issue_description: str
    conversation_history: str  # Holds device history initially, then the ongoing chat
    
    assigned_agent: str
    assignment_reason: str
    
    llm_questions: str | None
    llm_solution: str | None

# --- 3. OUTPUT MODELS (For Structured LLM Responses) ---

class SupervisorOutput(BaseModel):
    """Structured output for the Supervisor Agent's decision."""
    agent: str = Field(description="The agent to assign. Options: [HighCpuAgent, HighMemoryAgent, ConnectivityAgent]")
    reason: str = Field(description="A short reason for the assignment.")

class SpecialistOutput(BaseModel):
    """Structured output for any Specialist Agent's analysis."""
    information_needed: bool = Field(description="True if you need more info from the user, false otherwise.")
    questions_for_user: str | None = Field(description="Specific questions for the user if more info is needed.")
    solution: str | None = Field(description="A detailed, step-by-step solution if you have enough info.")

# --- 4. AGENT NODES (The "Workers" in the Graph) ---

# -- SUPERVISOR NODE --
def supervisor_node(state: TicketState):
    """Analyzes the initial ticket and assigns it to a specialist."""
    print("---SUPERVISOR---")
    prompt = ChatPromptTemplate.from_template(
        """
        You are an intelligent Network Supervisor Agent. Assign new tickets to the correct specialist.
        Available specialists:
        - HighCpuAgent: For high CPU utilization, process-related performance issues.
        - HighMemoryAgent: For high memory usage, memory leaks.
        - ConnectivityAgent: For packet loss, latency, routing issues, ping failures, or any 'Down' status alerts.

        New ticket:
        - Alert Type: {alert_type}
        - Device Name: {device_name}
        - Issue Description: {issue_description}
        - Historical context for this device: {conversation_history} 
        
        Task: Analyze the alert and assign the most appropriate specialist. Respond with a JSON object.
        """
    )
    chain = prompt | llm.with_structured_output(SupervisorOutput)
    response = chain.invoke(state) # Pass the full state
    print(f"Supervisor decided: Assign to {response.agent}. Reason: {response.reason}")
    state["assigned_agent"] = response.agent
    state["assignment_reason"] = response.reason
    return state

# -- SPECIALIST NODE 1: HIGH CPU AGENT --
def high_cpu_agent_node(state: TicketState):
    """Specialist for high CPU. Considers the full conversation."""
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
        2.  Based on the latest user reply, decide if you have enough info to propose a solution.
        3.  If you still need more info, ask NEW, follow-up questions (e.g., 'show tech-support', specific process details).
        4.  If you have enough info, provide a final, detailed resolution plan.

        Respond with a JSON object.
        """
    )
    chain = prompt | llm.with_structured_output(SpecialistOutput)
    response = chain.invoke(state)
    if response.information_needed:
        state["llm_questions"] = response.questions_for_user
        state["llm_solution"] = None
    else:
        state["llm_questions"] = None
        state["llm_solution"] = response.solution
    return state

# -- SPECIALIST NODE 2: CONNECTIVITY AGENT (NEW!) --
def connectivity_agent_node(state: TicketState):
    """Specialist for connectivity issues. Considers the full conversation."""
    print("---CONNECTIVITY AGENT (CONVERSATIONAL)---")
    prompt = ChatPromptTemplate.from_template(
        """
        You are a senior network troubleshooting AI agent specialized in connectivity problems (e.g., 'Ping Down', packet loss, latency).
        You are in an ongoing diagnostic conversation. Analyze the entire conversation and decide the next step.

        Initial Ticket Details:
        - Alert Type: {alert_type}
        - Device Name: {device_name}
        - Issue Description: {issue_description}

        --- CONVERSATION HISTORY ---
        {conversation_history}
        --- END OF HISTORY ---

        Your Task:
        1.  Review the ENTIRE conversation. The issue is related to connectivity.
        2.  Based on the latest user reply, decide if you have enough info to propose a solution.
        3.  If you still need more info, ask NEW, follow-up questions. Good questions would be: "Can you check the physical interface status ('show ip interface brief')?", "Is there a firewall between the source and destination?", "Can you provide a traceroute?".
        4.  If you have enough info, provide a final, detailed resolution plan.

        Respond with a JSON object.
        """
    )
    chain = prompt | llm.with_structured_output(SpecialistOutput)
    response = chain.invoke(state)
    if response.information_needed:
        state["llm_questions"] = response.questions_for_user
        state["llm_solution"] = None
    else:
        state["llm_questions"] = None
        state["llm_solution"] = response.solution
    return state


# --- 5. ROUTER & GRAPH ASSEMBLY ---

def router(state: TicketState):
    """This function routes the workflow to the correct specialist based on the supervisor's decision."""
    print("---ROUTER---")
    assigned_agent = state.get("assigned_agent")
    print(f"Routing based on assigned agent: {assigned_agent}")
    if assigned_agent == "HighCpuAgent":
        return "HighCpuAgent"
    if assigned_agent == "ConnectivityAgent":
        return "ConnectivityAgent"
    # If no specific agent is matched (or for future agents not yet implemented), end the workflow.
    return "end"

# Create the StateGraph
workflow = StateGraph(TicketState)

# Add the nodes
workflow.add_node("Supervisor", supervisor_node)
workflow.add_node("HighCpuAgent", high_cpu_agent_node)
workflow.add_node("ConnectivityAgent", connectivity_agent_node) # Add the new agent node

# Set the entry point
workflow.set_entry_point("Supervisor")

# Add the conditional router
workflow.add_conditional_edges(
    "Supervisor",
    router,
    {
        "HighCpuAgent": "HighCpuAgent",
        "ConnectivityAgent": "ConnectivityAgent", # Add the new routing path
        "end": END
    }
)

# Add the final edges from specialists to the end
workflow.add_edge("HighCpuAgent", END)
workflow.add_edge("ConnectivityAgent", END) # Add the edge for the new agent

# Compile the final workflow
agentic_workflow = workflow.compile()
print("✅ Full conversational agentic workflow compiled successfully with all agents!")

# --- 6. HELPER FUNCTION ---
def run_initial_workflow(ticket_data: dict):
    """Runs the initial workflow (Supervisor -> Specialist) for a new ticket."""
    initial_state = TicketState(
        alert_type=ticket_data.get("alert_type"),
        device_name=ticket_data.get("device_name"),
        issue_description=ticket_data.get("issue_description"),
        conversation_history=ticket_data.get("history_text", "No history available."),
        assigned_agent="",
        assignment_reason="",
        llm_questions=None,
        llm_solution=None
    )
    final_state = agentic_workflow.invoke(initial_state)
    return final_state