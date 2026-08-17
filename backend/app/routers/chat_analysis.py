import json
import time
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Analysis, Chat, Dataset, Message
from ..schemas import ChatAnalysisIn
from ..services.analyzer import analyze
from ..services.csv_loader import CSVValidationError, load_csv

router = APIRouter(prefix="/api/chats", tags=["chat analysis"])


@router.post("/{chat_id}/analyze")
def analyze_chat(chat_id: str, payload: ChatAnalysisIn, db: Session = Depends(get_db)):
    """Analyze a dataset in the chat's project and return the UI result contract."""
    chat = db.get(Chat, chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    dataset = db.get(Dataset, payload.dataset_id)
    if not dataset or dataset.project_id != chat.project_id:
        raise HTTPException(status_code=404, detail="Dataset not found in this chat's project")
    try:
        loaded = load_csv(dataset.content.encode("utf-8"), dataset.filename,
                          len(dataset.content.encode("utf-8")) + 1, dataset.row_count + 1)
    except CSVValidationError as exc:
        raise HTTPException(status_code=422, detail="Stored dataset is invalid") from exc
    started = time.perf_counter()
    result = analyze(payload.prompt, json.loads(dataset.profile_json), loaded.headers, loaded.rows)
    result["meta"]["duration_ms"] = int((time.perf_counter() - started) * 1000)
    chart_spec = result["charts"][0] if result["charts"] else None
    db.add(Message(chat_id=chat.id, role="user", content=payload.prompt))
    db.add(Message(chat_id=chat.id, role="assistant", content=result["summary"], metadata_json=json.dumps(result)))
    db.add(Analysis(project_id=chat.project_id, dataset_id=dataset.id, prompt=payload.prompt,
                    result_json=json.dumps(result), chart_spec_json=json.dumps(chart_spec) if chart_spec else None))
    db.commit()
    return result
