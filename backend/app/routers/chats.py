from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Chat, Message
from ..schemas import ChatIn, ChatOut, MessageIn, MessageOut
from .projects import project_or_404

router = APIRouter(prefix="/api/projects/{project_id}/chats", tags=["chats"])


def chat_or_404(project_id: str, chat_id: str, db: Session) -> Chat:
    chat = db.get(Chat, chat_id)
    if not chat or chat.project_id != project_id:
        raise HTTPException(status_code=404, detail="Chat not found")
    return chat


@router.get("", response_model=list[ChatOut])
def list_chats(project_id: str, db: Session = Depends(get_db)):
    project_or_404(project_id, db)
    return db.query(Chat).filter_by(project_id=project_id).order_by(Chat.updated_at.desc()).all()


@router.post("", response_model=ChatOut, status_code=status.HTTP_201_CREATED)
def create_chat(project_id: str, payload: ChatIn, db: Session = Depends(get_db)):
    project_or_404(project_id, db)
    chat = Chat(project_id=project_id, **payload.model_dump())
    db.add(chat)
    db.commit()
    db.refresh(chat)
    return chat


@router.get("/{chat_id}/messages", response_model=list[MessageOut])
def list_messages(project_id: str, chat_id: str, db: Session = Depends(get_db)):
    chat_or_404(project_id, chat_id, db)
    return db.query(Message).filter_by(chat_id=chat_id).order_by(Message.created_at).all()


@router.post("/{chat_id}/messages", response_model=MessageOut, status_code=status.HTTP_201_CREATED)
def create_message(project_id: str, chat_id: str, payload: MessageIn, db: Session = Depends(get_db)):
    chat_or_404(project_id, chat_id, db)
    message = Message(chat_id=chat_id, **payload.model_dump())
    db.add(message)
    db.commit()
    db.refresh(message)
    return message
