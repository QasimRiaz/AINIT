# main.py

import os
import json
import traceback
import random
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
import google.generativeai as genai
from pgvector.psycopg2 import register_vector

from database import get_db_connection
from agents import run_initial_workflow, high_cpu_agent_node, connectivity_agent_node, TicketState

# --- Pydantic Models ---
class PrtgAlert(BaseModel):
    device: str
    sensor: str
    status: str
    message: str

class UserReply(BaseModel):
    message: str

class ResolveTicket(BaseModel):
    rating: int

# --- Configure Embedding Model ---
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

# --- FastAPI App ---
app = FastAPI(title="NexusAI - Self-Improving AI API", version="4.0.1")

# --- Helper Functions ---
def translate_prtg_to_description(alert: PrtgAlert) -> tuple[str, str]:
    alert_type = f"{alert.sensor} on {alert.device}"
    if alert.status.lower() == 'down':
        description = (f"The '{alert.sensor}' sensor on device '{alert.device}' has reported a 'Down' status. PRTG message: '{alert.message}'.")
    else:
        description = (f"The '{alert.sensor}' sensor on '{alert.device}' has a '{alert.status}' status. PRTG message: '{alert.message}'.")
    return alert_type, description

def generate_unique_ticket_uid(cursor) -> int:
    while True:
        ticket_uid = random.randint(10000000, 99999999)
        cursor.execute("SELECT id FROM tickets WHERE ticket_uid = %s", (ticket_uid,))
        if cursor.fetchone() is None:
            return ticket_uid

# --- Background Task Function ---
def process_ai_conversation_in_background(ticket_id: int, current_state: TicketState):
    print(f"---BACKGROUND TASK STARTED for ticket {ticket_id}---")
    conn = None
    try:
        assigned_agent_name = current_state["assigned_agent"]
        ai_result_state = None

        if assigned_agent_name == 'HighCpuAgent':
            print("...calling HighCpuAgent in background.")
            ai_result_state = high_cpu_agent_node(current_state)
        elif assigned_agent_name == 'ConnectivityAgent':
            print("...calling ConnectivityAgent in background.")
            ai_result_state = connectivity_agent_node(current_state)
        else:
            print(f"Background task: No valid conversational agent found for '{assigned_agent_name}'.")
            return

        new_status = 'Attention Needed'
        ai_message_to_save = ""
        if llm_questions := ai_result_state.get("llm_questions"):
            ai_message_to_save = llm_questions
        elif llm_solution := ai_result_state.get("llm_solution"):
            new_status = 'Solution Proposed'
            ai_message_to_save = "I have a final solution based on your input. Please see the 'AI Final Solution' section."

        conn = get_db_connection()
        cursor = conn.cursor()
        if ai_message_to_save:
            sql_insert_ai_msg = "INSERT INTO ticket_messages (ticket_id, sender, message) VALUES (%s, %s, %s);"
            cursor.execute(sql_insert_ai_msg, (ticket_id, 'ai', ai_message_to_save))

        sql_update_ticket = "UPDATE tickets SET llm_solution = %s, status = %s WHERE id = %s;"
        cursor.execute(sql_update_ticket, (ai_result_state.get("llm_solution"), new_status, ticket_id))
        conn.commit()
        
        print(f"---BACKGROUND TASK FINISHED for ticket {ticket_id}---")
    except Exception as e:
        print(f"❌❌❌ ERROR in background task for ticket {ticket_id}: {e} ❌❌❌")
        traceback.print_exc()
    finally:
        if conn:
            conn.close()

# --- API Endpoints ---
@app.get("/")
def read_root():
    return {"status": "NexusAI API is running"}

@app.post("/api/v1/prtg-alert", status_code=201)
def process_prtg_alert(alert: PrtgAlert):
    conn = None
    try:
        alert_type, issue_description = translate_prtg_to_description(alert)
        conn = get_db_connection()
        register_vector(conn)
        cursor = conn.cursor()

        print("🔎 Performing semantic search for similar past tickets...")
        new_embedding = genai.embed_content(model="models/text-embedding-004", content=issue_description)["embedding"]
        
        sql_search = "SELECT ticket_uid, llm_solution FROM tickets WHERE status = 'Closed' AND embedding IS NOT NULL AND embedding <=> %s < 0.2 ORDER BY embedding <=> %s LIMIT 1;"
        
        # FIX: Convert the embedding list to a string for pgvector
        cursor.execute(sql_search, (str(new_embedding), str(new_embedding)))
        
        similar_ticket = cursor.fetchone()

        if similar_ticket:
            similar_ticket_uid, similar_solution = similar_ticket
            print(f"✅ Found a similar past solution in ticket UID {similar_ticket_uid}.")
            
            new_ticket_uid = generate_unique_ticket_uid(cursor)
            solution_text = (f"**Knowledge Base Match Found:**\n\nA similar issue was resolved in the past. "
                           f"Please review the solution from **Ticket #{similar_ticket_uid}** below.\n\n---\n\n"
                           f"**Past Solution:**\n{similar_solution}\n\n---\n\n"
                           f"If this does not resolve your issue, please use the feedback options to reopen this ticket for AI analysis.")
            
            sql_insert = "INSERT INTO tickets (ticket_uid, device_name, alert_type, issue_description, sensor, prtg_status, prtg_message, status, llm_solution) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id;"
            cursor.execute(sql_insert, (new_ticket_uid, alert.device, alert_type, issue_description, alert.sensor, alert.status, alert.message, 'Solution Proposed', solution_text))
            new_internal_id = cursor.fetchone()[0]
            conn.commit()

            return {"status": "Found similar past solution", "ticket_uid": new_ticket_uid, "similar_ticket_uid": similar_ticket_uid}

        print("... No similar solution found. Proceeding with full AI workflow.")
        new_ticket_uid = generate_unique_ticket_uid(cursor)
        sql_insert = "INSERT INTO tickets (ticket_uid, device_name, alert_type, issue_description, sensor, prtg_status, prtg_message, status) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id;"
        cursor.execute(sql_insert, (new_ticket_uid, alert.device, alert_type, issue_description, alert.sensor, alert.status, alert.message, 'Processing'))
        new_internal_id = cursor.fetchone()[0]
        conn.commit()

        sql_history = "SELECT created_at, issue_description, llm_solution FROM tickets WHERE device_name = %s AND id != %s AND status = 'Closed' ORDER BY created_at DESC LIMIT 5;"
        cursor.execute(sql_history, (alert.device, new_internal_id))
        history_text = "No previous closed tickets found."
        if past_tickets := cursor.fetchall():
            history_text = "Previously closed tickets:\n" + "\n".join([f"- On {t[0].strftime('%Y-%m-%d')}, issue '{t[1]}' was resolved with: '{t[2]}'" for t in past_tickets])
        
        ticket_data_for_ai = {"alert_type": alert_type, "device_name": alert.device, "issue_description": issue_description, "history_text": history_text}
        ai_result = run_initial_workflow(ticket_data_for_ai)

        new_status = 'Processing'
        ai_message_to_save = ""
        if questions := ai_result.get("llm_questions"):
            new_status = 'Attention Needed'
            ai_message_to_save = questions
        elif ai_result.get("llm_solution"):
            new_status = 'Solution Proposed'
            ai_message_to_save = "Based on the initial information, I have a proposed solution."

        if ai_message_to_save:
            sql_insert_ai_msg = "INSERT INTO ticket_messages (ticket_id, sender, message) VALUES (%s, %s, %s);"
            cursor.execute(sql_insert_ai_msg, (new_internal_id, 'ai', ai_message_to_save))

        sql_update = "UPDATE tickets SET assigned_agent = %s, llm_solution = %s, status = %s WHERE id = %s;"
        cursor.execute(sql_update, (ai_result.get("assigned_agent"), ai_result.get("llm_solution"), new_status, new_internal_id))
        conn.commit()
        
        return {"status": "PRTG alert processed, AI analysis initiated", "ticket_uid": new_ticket_uid, "internal_id": new_internal_id}

    except Exception as e:
        print(f"❌ Error in PRTG alert processing: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()

@app.post("/api/v1/ticket/{ticket_id}/resolve")
def resolve_ticket(ticket_id: int, feedback: ResolveTicket):
    conn = None
    try:
        conn = get_db_connection()
        register_vector(conn)
        cursor = conn.cursor()

        cursor.execute("SELECT issue_description FROM tickets WHERE id = %s", (ticket_id,))
        ticket = cursor.fetchone()
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")
        issue_description = ticket[0]

        print(f"✅ Ticket {ticket_id} solved. Generating embedding to add to knowledge base...")
        embedding = genai.embed_content(model="models/text-embedding-004", content=issue_description)["embedding"]

        sql_update = "UPDATE tickets SET status = 'Closed', solution_rating = %s, embedding = %s WHERE id = %s;"
        
        # FIX: Convert the embedding list to a string for pgvector
        cursor.execute(sql_update, (feedback.rating, str(embedding), ticket_id))
        
        conn.commit()
        return {"status": "Ticket closed and added to knowledge base."}
    except Exception as e:
        print(f"❌ Error in resolve_ticket endpoint: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()

@app.post("/api/v1/ticket/{ticket_id}/continue")
def continue_conversation(ticket_id: int, reply: UserReply, background_tasks: BackgroundTasks):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        sql_insert_user_msg = "INSERT INTO ticket_messages (ticket_id, sender, message) VALUES (%s, %s, %s);"
        cursor.execute(sql_insert_user_msg, (ticket_id, 'user', reply.message))
        cursor.execute("UPDATE tickets SET status = 'AI Processing' WHERE id = %s;", (ticket_id,))
        conn.commit()
        print(f"✅ User reply saved, status set to 'AI Processing' for ticket {ticket_id}.")

        sql_get_convo = "SELECT sender, message FROM ticket_messages WHERE ticket_id = %s ORDER BY created_at ASC;"
        cursor.execute(sql_get_convo, (ticket_id,))
        conversation_history = "\n".join([f"{sender.upper()}: {msg}" for sender, msg in cursor.fetchall()])
        
        cursor.execute("SELECT alert_type, device_name, issue_description, assigned_agent FROM tickets WHERE id = %s;", (ticket_id,))
        ticket_details = cursor.fetchone()
        if not ticket_details:
            raise HTTPException(status_code=404, detail="Ticket not found")

        current_state = TicketState(
            alert_type=ticket_details[0], device_name=ticket_details[1],
            issue_description=ticket_details[2], conversation_history=conversation_history,
            assigned_agent=ticket_details[3], assignment_reason="",
            llm_questions=None, llm_solution=None
        )

        background_tasks.add_task(process_ai_conversation_in_background, ticket_id, current_state)
        
        print("✅ AI processing scheduled in the background. Returning immediate response.")
        
        return {"status": "Reply received. AI processing has started in the background."}
    except Exception as e:
        print(f"❌ Error in continue_conversation endpoint: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()