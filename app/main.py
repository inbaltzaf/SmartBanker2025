from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import json
import os

app = FastAPI(title="Smart Banker AI Assistant")

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
CUSTOMERS_DIR = os.path.abspath(os.path.join(DATA_DIR, "customers"))
CONVERSATIONS_DIR = os.path.abspath(os.path.join(DATA_DIR, "conversations"))

app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    customerId: Optional[str] = None
    messages: List[ChatMessage]

class Suggestion(BaseModel):
    title: str
    reason: str
    action: str

class ChatResponse(BaseModel):
    reply: str
    suggestions: List[Suggestion] = []
    customerSummary: Optional[Dict[str, Any]] = None


def _load_json_file(path: str) -> Any:
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_customer(customer_id: str) -> Optional[Dict[str, Any]]:
    path = os.path.join(CUSTOMERS_DIR, f"{customer_id}.json")
    return _load_json_file(path)


def list_customers() -> List[Dict[str, Any]]:
    customers = []
    if not os.path.isdir(CUSTOMERS_DIR):
        return customers
    for fname in os.listdir(CUSTOMERS_DIR):
        if not fname.endswith(".json"):
            continue
        customer = _load_json_file(os.path.join(CUSTOMERS_DIR, fname))
        if customer:
            customers.append(customer)
    return customers


def last_messages_for_customer(customer_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    conv_path = os.path.join(CONVERSATIONS_DIR, f"{customer_id}.json")
    conv = _load_json_file(conv_path)
    if not conv:
        return []
    messages = conv.get("messages", [])
    return messages[-limit:]


def build_customer_summary(customer: Dict[str, Any]) -> Dict[str, Any]:
    last_events = customer.get("recentEvents", [])[:5]
    products = customer.get("products", [])
    risk = customer.get("riskScore")
    return {
        "name": customer.get("name"),
        "segment": customer.get("segment"),
        "balance": customer.get("balance"),
        "products": products,
        "riskScore": risk,
        "lastEvents": last_events,
    }


def rule_based_assistant(customer: Optional[Dict[str, Any]], history: List[Dict[str, Any]], user_input: str) -> ChatResponse:
    lower = user_input.lower()
    suggestions: List[Suggestion] = []
    reply_parts: List[str] = []

    if customer:
        summary = build_customer_summary(customer)
        reply_parts.append(f"שלום {summary['name']}, אשמח לעזור. ")
        if summary.get("riskScore") and summary["riskScore"] >= 80:
            suggestions.append(Suggestion(
                title="בדיקת אירועי הונאה/חסימה",
                reason="ציון סיכון גבוה מהרגיל",
                action="פתח קריאת שירות לבדיקת הונאה והצע החלפת כרטיס/הקשחת אימות"
            ))
        if "משיכת" in lower or "מזומן" in lower:
            suggestions.append(Suggestion(
                title="הכוונה למשיכת מזומן ללא כרטיס",
                reason="הלקוח מתעניין במשיכה",
                action="הצע קוד משיכה באפליקציה או מיקום כספומט קרוב"
            ))
        if summary.get("balance") is not None and summary["balance"] < 0:
            suggestions.append(Suggestion(
                title="הצעת מסגרת אשראי או הלוואת גישור",
                reason="יתרה שלילית",
                action="בדוק זכאות להגדלת מסגרת או הצע הלוואה קצרת מועד"
            ))
        if "הלווא" in lower:
            suggestions.append(Suggestion(
                title="סימולציית הלוואה מותאמת",
                reason="הלקוח מבקש הלוואה",
                action="בצע סימולציה לפי שכר, התחייבויות ויחס החזר"
            ))
    else:
        summary = None
        reply_parts.append("שלום, אשמח לעזור. ")

    if any(k in lower for k in ["שלום", "היי", "הי"]):
        reply_parts.append("איך אני יכול לסייע היום? ")

    if "עמלות" in lower:
        reply_parts.append("לגבי עמלות: אוכל לבדוק את סוג החשבון וההטבות הפעילות. ")
        suggestions.append(Suggestion(
            title="בדיקת חבילת עמלות",
            reason="שאלת עמלות",
            action="בדוק הטבות פעילות ושקול הטבות שימור"
        ))

    if "כרטיס" in lower or "חיוב" in lower:
        reply_parts.append("ראיתי לאחרונה אירועים הקשורים לכרטיס. נבדוק אם יש חיובים חריגים. ")

    if not reply_parts:
        reply_parts.append("קיבלתי, מבצע בדיקה ומציע אפשרויות מתאימות. ")

    reply = "".join(reply_parts)
    return ChatResponse(reply=reply, suggestions=suggestions, customerSummary=summary)


@app.get("/api/customers")
async def api_list_customers():
    return JSONResponse(list_customers())


@app.get("/api/customers/{customer_id}")
async def api_get_customer(customer_id: str):
    customer = load_customer(customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    return JSONResponse(customer)


@app.get("/api/conversations/{customer_id}")
async def api_get_conversation(customer_id: str):
    return JSONResponse({"messages": last_messages_for_customer(customer_id)})


@app.post("/api/chat", response_model=ChatResponse)
async def api_chat(req: ChatRequest):
    customer = load_customer(req.customerId) if req.customerId else None
    history = [m.model_dump() for m in req.messages]
    user_input = history[-1]["content"] if history else ""
    return rule_based_assistant(customer, history, user_input)


@app.get("/", response_class=HTMLResponse)
async def index():
    with open(os.path.join(os.path.dirname(__file__), "static", "index.html"), "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())
