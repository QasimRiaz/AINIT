# main.py

import json
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional

from database import get_db_connection
# We now need both the initial runner and the individual agent node
from agents import run_initial_workflow, high_cpu_agent_node, TicketState

# --- Pydantic Models ---
class TicketHistory(BaseModel):
    date: str
    solution: str

class IncomingAlert(BaseModel):
    alert_type: str = Field(..., example="High CPU Usage")
    device_name: str = Field(..., example="Router-01")
    issue_description: str = Field(..., example="CPU load exceeded 90% threshold")
    history: Optional[List[TicketHistory]] = []

class UserReply(BaseModel):
    message: str

# --- FastAPI App ---
app = FastAPI(title="AINIT - Conversational AI API", version="1.1.0")

@app.get("/")
def read_root():
    return {"status": "AINIT API is running"}

@app.post("/api/v1/alert", status_code=201)
def process_initial_alert(alert: IncomingAlert):
    """Receives an alert, runs the initial AI workflow, and saves the first AI message."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # 1. Create Initial Ticket
        print("✅ New alert received. Saving initial ticket...")
        history_json = json.dumps([h.dict() for h in alert.history]) if alert.history else None
        sql_insert = "INSERT INTO tickets (alert_type, device_name, issue_description, history, status) VALUES (%s, %s, %s, %s, %s) RETURNING id;"
        cursor.execute(sql_insert, (alert.alert_type, alert.device_name, alert.issue_description, history_json, 'Processing'))
        new_ticket_id = cursor.fetchone()[0]
        conn.commit()

        # 2. Fetch Historical Context
        print(f"🔎 Fetching history for device: {alert.device_name}...")
        sql_history = "SELECT created_at, issue_description, llm_solution FROM tickets WHERE device_name = %s AND id != %s AND status = 'Closed' ORDER BY created_at DESC LIMIT 5;"
        cursor.execute(sql_history, (alert.device_name, new_ticket_id))
        past_tickets = cursor.fetchall()
        history_text = "No previous closed tickets found."
        if past_tickets:
            history_text = "Previously closed tickets:\n" + "\n".join([f"- On {t[0].strftime('%Y-%m-%d')}, issue '{t[1]}' was resolved with: '{t[2]}'" for t in past_tickets])
        
        # 3. Run Initial AI Workflow
        print("🤖 Handing ticket to AI workflow for first analysis...")
        ticket_data_for_ai = alert.dict()
        ticket_data_for_ai['history_text'] = history_text
        ai_result = run_initial_workflow(ticket_data_for_ai)

        # 4. Save the first AI message to the conversation history
        new_status = 'Processing'
        ai_message_to_save = ""
        if ai_result.get("llm_questions"):
            new_status = 'Attention Needed'
            ai_message_to_save = ai_result["llm_questions"]
        elif ai_result.get("llm_solution"):
            new_status = 'Solution Proposed'
            # For the first message, we can just say a solution was found.
            ai_message_to_save = "Based on the initial information, I have a proposed solution."

        if ai_message_to_save:
            sql_insert_ai_msg = "INSERT INTO ticket_messages (ticket_id, sender, message) VALUES (%s, %s, %s);"
            cursor.execute(sql_insert_ai_msg, (new_ticket_id, 'ai', ai_message_to_save))

        # 5. Update the main ticket with the AI's findings
        sql_update = "UPDATE tickets SET assigned_agent = %s, llm_solution = %s, status = %s WHERE id = %s;"
        cursor.execute(sql_update, (ai_result.get("assigned_agent"), ai_result.get("llm_solution"), new_status, new_ticket_id))
        conn.commit()
        
        print(f"✅ Ticket {new_ticket_id} created and initial analysis complete.")
        return {"status": "Alert processed, AI analysis initiated", "ticket_id": new_ticket_id, "ai_analysis": ai_result}

    except Exception as e:
        print(f"❌ Error in initial alert processing: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn: conn.close()


@app.post("/api/v1/ticket/{ticket_id}/continue")
def continue_conversation(ticket_id: int, reply: UserReply):
    """
    Handles a user's reply, continues the AI workflow, and updates the ticket.
    """
    # *** ADD THIS LINE ***
    print(f"\n---FASTAPI ENDPOINT HIT--- \n✅ /continue endpoint called for ticket_id: {ticket_id} \n✅ Received message: '{reply.message}'")
    
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # 1. Save User's Message
        print(f"✅ Received reply for ticket {ticket_id}")
        sql_insert_user_msg = "INSERT INTO ticket_messages (ticket_id, sender, message) VALUES (%s, %s, %s);"
        cursor.execute(sql_insert_user_msg, (ticket_id, 'user', reply.message))
        conn.commit()

        # 2. Fetch Full Conversation History
        sql_get_convo = "SELECT sender, message FROM ticket_messages WHERE ticket_id = %s ORDER BY created_at ASC;"
        cursor.execute(sql_get_convo, (ticket_id,))
        conversation_history = "\n".join([f"{sender.upper()}: {msg}" for sender, msg in cursor.fetchall()])
        
        # 3. Get Initial Ticket Details
        cursor.execute("SELECT alert_type, device_name, issue_description, assigned_agent FROM tickets WHERE id = %s;", (ticket_id,))
        ticket_details = cursor.fetchone()
        if not ticket_details:
            raise HTTPException(status_code=404, detail="Ticket not found")

        # 4. Re-run the Specialist Agent
        print("🤖 Handing conversation back to specialist agent...")
        current_state = TicketState(
            alert_type=ticket_details[0], device_name=ticket_details[1],
            issue_description=ticket_details[2], conversation_history=conversation_history,
            assigned_agent=ticket_details[3], assignment_reason="", # Reason not needed for continuation
            llm_questions=None, llm_solution=None
        )

        # This part could be a router in the future, for now we hardcode HighCpuAgent
        if ticket_details[3] == 'HighCpuAgent':
            ai_result = high_cpu_agent_node(current_state)
        else:
            raise HTTPException(status_code=501, detail="Conversational logic for this agent is not implemented.")
        
        # 5. Save AI's New Response and Update Ticket
        new_status = 'Attention Needed'
        ai_message_to_save = ""
        if ai_result.get("llm_questions"):
            ai_message_to_save = ai_result["llm_questions"]
        elif ai_result.get("llm_solution"):
            new_status = 'Solution Proposed'
            ai_message_to_save = "I have a final solution based on your input."

        if ai_message_to_save:
            sql_insert_ai_msg = "INSERT INTO ticket_messages (ticket_id, sender, message) VALUES (%s, %s, %s);"
            cursor.execute(sql_insert_ai_msg, (ticket_id, 'ai', ai_message_to_save))

        sql_update_ticket = "UPDATE tickets SET llm_solution = %s, status = %s WHERE id = %s;"
        cursor.execute(sql_update_ticket, (ai_result.get("llm_solution"), new_status, ticket_id))
        conn.commit()
        
        print("✅ Conversation continued successfully.")
        return {"status": "Conversation continued successfully", "ai_response": ai_result}

    except Exception as e:
        print(f"❌ Error in conversation continuation: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn: conn.close()