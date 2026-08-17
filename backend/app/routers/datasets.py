import json
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session
from ..config import get_settings
from ..database import get_db
from ..models import Dataset
from ..schemas import DatasetOut
from ..services import dataset_store
from ..services.csv_loader import CSVValidationError, load_csv
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
                      profile=json.loads(dataset.profile_json),
                      sheets=json.loads(dataset.sheets_json) if dataset.sheets_json else [],
                      created_at=dataset.created_at)


@router.get("", response_model=list[DatasetOut])
def list_datasets(project_id: str, db: Session = Depends(get_db)):
    project_or_404(project_id, db)
    return [serialize(item) for item in db.query(Dataset).filter_by(project_id=project_id).order_by(Dataset.created_at.desc())]


def _store_upload(raw_file, filename: str) -> dataset_store.StoredDataset:
    """Stream the upload to disk and ingest it (runs off the event loop)."""
    settings = get_settings()
    chunks = iter(lambda: raw_file.read(dataset_store.CHUNK_BYTES), b"")
    path = dataset_store.save_stream(chunks, filename, settings)
    try:
        return dataset_store.ingest_upload(path, filename, settings)
    except dataset_store.DatasetError:
        dataset_store.delete_stored_file(str(path))
        raise


@router.post("", response_model=DatasetOut, status_code=status.HTTP_201_CREATED)
async def upload_dataset(project_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    project_or_404(project_id, db)
    filename = file.filename or "dataset.csv"
    try:
        stored = await run_in_threadpool(_store_upload, file.file, filename)
    except dataset_store.DatasetError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    dataset = Dataset(project_id=project_id, filename=filename, content=None,
                      row_count=stored.row_count, columns_json=json.dumps(stored.columns),
                      profile_json=json.dumps(stored.profile), file_hash=stored.file_hash,
                      storage_path=stored.storage_path, sheets_json=json.dumps(stored.sheets))
    db.add(dataset)
    db.commit()
    db.refresh(dataset)
    return serialize(dataset)


@router.get("/{dataset_id}", response_model=DatasetOut)
def get_dataset(project_id: str, dataset_id: str, db: Session = Depends(get_db)):
    return serialize(dataset_or_404(project_id, dataset_id, db))


@router.get("/{dataset_id}/profile")
def get_dataset_profile(project_id: str, dataset_id: str, db: Session = Depends(get_db)):
    dataset = dataset_or_404(project_id, dataset_id, db)
    return json.loads(dataset.profile_json)


@router.get("/{dataset_id}/schema")
async def get_dataset_schema(project_id: str, dataset_id: str, db: Session = Depends(get_db)):
    """The compact schema card - the same description the LLM sees."""
    dataset = dataset_or_404(project_id, dataset_id, db)
    if not dataset.storage_path:
        raise HTTPException(status_code=404, detail="Schema card is only available for stored datasets")
    try:
        return await run_in_threadpool(dataset_store.schema_card_markdown, dataset.storage_path)
    except dataset_store.DatasetError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{dataset_id}/preview")
async def get_dataset_preview(project_id: str, dataset_id: str,
                              limit: int = Query(default=50, ge=1, le=500),
                              sheet: str | None = Query(default=None),
                              db: Session = Depends(get_db)):
    dataset = dataset_or_404(project_id, dataset_id, db)
    if dataset.storage_path:
        try:
            return await run_in_threadpool(dataset_store.preview, dataset.storage_path, limit, sheet)
        except dataset_store.DatasetError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    stored_bytes = (dataset.content or "").encode("utf-8")
    try:
        loaded = load_csv(stored_bytes, dataset.filename, len(stored_bytes) + 1, dataset.row_count + 1)
    except CSVValidationError as exc:
        raise HTTPException(status_code=422, detail="Stored dataset is invalid") from exc
    return {"columns": loaded.headers, "rows": loaded.rows[:limit], "row_count": dataset.row_count}


@router.delete("/{dataset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_dataset(project_id: str, dataset_id: str, db: Session = Depends(get_db)):
    dataset = dataset_or_404(project_id, dataset_id, db)
    storage_path = dataset.storage_path
    db.delete(dataset)
    db.commit()
    dataset_store.delete_stored_file(storage_path)
