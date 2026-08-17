import json
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session
from ..config import get_settings
from ..database import get_db
from ..models import Dataset
from ..schemas import DatasetOut
from ..services.csv_loader import CSVValidationError, load_csv
from ..services.profiler import profile_csv
from .projects import project_or_404

router = APIRouter(prefix="/api/projects/{project_id}/datasets", tags=["datasets"])


def dataset_or_404(project_id: str, dataset_id: str, db: Session) -> Dataset:
    dataset = db.get(Dataset, dataset_id)
    if not dataset or dataset.project_id != project_id:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return dataset


def serialize(dataset: Dataset) -> DatasetOut:
    return DatasetOut(id=dataset.id, project_id=dataset.project_id, filename=dataset.filename,
                      row_count=dataset.row_count, columns=json.loads(dataset.columns_json),
                      profile=json.loads(dataset.profile_json), created_at=dataset.created_at)


@router.get("", response_model=list[DatasetOut])
def list_datasets(project_id: str, db: Session = Depends(get_db)):
    project_or_404(project_id, db)
    return [serialize(item) for item in db.query(Dataset).filter_by(project_id=project_id).order_by(Dataset.created_at.desc())]


@router.post("", response_model=DatasetOut, status_code=status.HTTP_201_CREATED)
async def upload_dataset(project_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    project_or_404(project_id, db)
    settings = get_settings()
    content = await file.read(settings.max_upload_bytes + 1)
    try:
        loaded = load_csv(content, file.filename or "", settings.max_upload_bytes, settings.max_csv_rows)
    except CSVValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    profile = profile_csv(loaded.headers, loaded.rows)
    dataset = Dataset(project_id=project_id, filename=file.filename or "dataset.csv", content=loaded.text,
                      row_count=len(loaded.rows), columns_json=json.dumps(loaded.headers),
                      profile_json=json.dumps(profile))
    db.add(dataset)
    db.commit()
    db.refresh(dataset)
    return serialize(dataset)


@router.get("/{dataset_id}", response_model=DatasetOut)
def get_dataset(project_id: str, dataset_id: str, db: Session = Depends(get_db)):
    return serialize(dataset_or_404(project_id, dataset_id, db))


@router.delete("/{dataset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_dataset(project_id: str, dataset_id: str, db: Session = Depends(get_db)):
    db.delete(dataset_or_404(project_id, dataset_id, db))
    db.commit()
