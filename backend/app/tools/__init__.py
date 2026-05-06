"""Tools package — registry of all 7 tools."""
from app.tools.escalate import escalate_to_human
from app.tools.get_ticket import get_ticket_details
from app.tools.search_kb import search_kb
from app.tools.send_email import send_email
from app.tools.translate import translate_text
from app.tools.update_status import update_ticket_status


def get_all_tools() -> dict:
    return {
        "get_ticket_details": get_ticket_details,
        "update_ticket_status": update_ticket_status,
        "search_kb": search_kb,
        "send_email": send_email,
        "escalate_to_human": escalate_to_human,
        "translate_text": translate_text,
    }
