"""File uploads: signed upload form, then the api checks the file."""

import logging
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import RedirectResponse
from pydantic import AfterValidator, BaseModel, ConfigDict, Field
from sqlalchemy import text

from api import files, ratelimit, safety_client
from api.attachments import AttachmentOut
from api.auth import CurrentUser, current_user, optional_user
from api.config import get_settings
from api.visibility import VISIBLE_TO_VIEWER

router = APIRouter()
log = logging.getLogger("api.uploads")

UPLOAD_LIMIT = 30
UPLOAD_WINDOW_SECONDS = 3600
FORM_SECONDS = 300
LINK_SECONDS = 600


def _allowed_type(content_type: str) -> str:
    """Check that the file type is allowed."""
    if content_type not in files.TYPES:
        raise ValueError("file type not allowed: images, PDF, plain text, MP4/WebM video")
    return content_type


class UploadIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str = Field(min_length=1, max_length=255)
    content_type: Annotated[str, AfterValidator(_allowed_type)]
    size_bytes: int = Field(gt=0)


class UploadOut(BaseModel):
    id: uuid.UUID
    url: str
    fields: dict[str, str]


def _bucket() -> str:
    """The bucket for attachments."""
    bucket = get_settings().attachments_bucket
    if not bucket:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Attachments are not available")
    return bucket


def _human(user: CurrentUser) -> None:
    """Only the person, not an AI app, may upload."""
    if user.actor != "human":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only you can attach files")


@router.post("/uploads", status_code=status.HTTP_201_CREATED)
async def start_upload(
    body: UploadIn, request: Request, user: Annotated[CurrentUser, Depends(current_user)]
) -> UploadOut:
    """Give the browser a signed form to upload a file."""
    _human(user)
    bucket = _bucket()
    file_type = files.TYPES[body.content_type]
    if body.size_bytes > file_type.max_bytes:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Files of this type can be at most {file_type.max_bytes // files.MB} MB",
        )
    await ratelimit.enforce(
        request, f"ratelimit:uploads:{user.id}", UPLOAD_LIMIT, UPLOAD_WINDOW_SECONDS
    )
    async with request.app.state.db.begin() as conn:
        attachment_id = await conn.scalar(
            text(
                "INSERT INTO attachments (owner_id, kind, content_type, size_bytes, filename)"
                " VALUES (:u, :kind, :ct, :size, :name) RETURNING id"
            ),
            {
                "u": user.id,
                "kind": file_type.kind,
                "ct": body.content_type,
                "size": body.size_bytes,
                "name": files.safe_filename(body.filename),
            },
        )
    form: dict[str, Any] = await run_in_threadpool(
        request.app.state.s3.generate_presigned_post,
        Bucket=bucket,
        Key=f"pending/{attachment_id}",
        Fields={"Content-Type": body.content_type},
        Conditions=[
            {"Content-Type": body.content_type},
            ["content-length-range", 1, body.size_bytes],
        ],
        ExpiresIn=FORM_SECONDS,
    )
    return UploadOut(id=attachment_id, url=form["url"], fields=form["fields"])


@router.post("/uploads/{attachment_id}/complete")
async def complete_upload(
    attachment_id: uuid.UUID, request: Request, user: Annotated[CurrentUser, Depends(current_user)]
) -> AttachmentOut:
    """Check an uploaded file and keep the clean copy."""
    _human(user)
    bucket = _bucket()
    s3 = request.app.state.s3
    async with request.app.state.db.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT id, kind, filename, content_type, size_bytes FROM attachments"
                    " WHERE id = :id AND owner_id = :u AND status = 'pending'"
                ),
                {"id": attachment_id, "u": user.id},
            )
        ).one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Upload not found")
    pending_key = f"pending/{attachment_id}"
    try:
        obj = await run_in_threadpool(s3.get_object, Bucket=bucket, Key=pending_key)
        data: bytes = await run_in_threadpool(
            obj["Body"].read, files.TYPES[row.content_type].max_bytes + 1
        )
    except Exception:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "The file has not been uploaded yet"
        ) from None

    try:
        checked = await run_in_threadpool(files.check, data, row.content_type)
        if row.content_type == "text/plain":
            await safety_client.check_file_text(request, checked.decode("utf-8"))
    except (files.Rejected, HTTPException) as problem:
        await _reject(request, attachment_id, pending_key)
        if isinstance(problem, HTTPException):
            raise
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(problem)) from None

    inline = files.TYPES[row.content_type].inline
    await run_in_threadpool(
        s3.put_object,
        Bucket=bucket,
        Key=f"files/{attachment_id}",
        Body=checked,
        ContentType=row.content_type,
        ContentDisposition="inline" if inline else f'attachment; filename="{row.filename}"',
    )
    await run_in_threadpool(s3.delete_object, Bucket=bucket, Key=pending_key)
    async with request.app.state.db.begin() as conn:
        await conn.execute(
            text("UPDATE attachments SET status = 'ready' WHERE id = :id"), {"id": attachment_id}
        )
    return AttachmentOut(
        id=row.id,
        kind=row.kind,
        filename=row.filename,
        content_type=row.content_type,
        size_bytes=len(checked),
    )


async def _reject(request: Request, attachment_id: uuid.UUID, key: str) -> None:
    """Mark an upload rejected and delete it."""
    async with request.app.state.db.begin() as conn:
        await conn.execute(
            text("UPDATE attachments SET status = 'rejected' WHERE id = :id"), {"id": attachment_id}
        )
    try:
        await run_in_threadpool(request.app.state.s3.delete_object, Bucket=_bucket(), Key=key)
    except Exception as exc:
        log.warning("could not delete rejected upload: %s", type(exc).__name__)


_ATTACHMENT_SQL = (
    "SELECT a.content_type, a.filename FROM attachments a"  # noqa: S608
    " LEFT JOIN replies r ON r.id = a.reply_id"
    " LEFT JOIN threads t ON t.id = COALESCE(a.thread_id, r.thread_id)"
    " JOIN topic_groups g ON g.id = t.group_id"
    " WHERE a.id = :id AND a.status = 'ready' AND t.deleted_at IS NULL"
    f" AND t.id IS NOT NULL AND {VISIBLE_TO_VIEWER}"
)


@router.get("/attachments/{attachment_id}", status_code=status.HTTP_307_TEMPORARY_REDIRECT)
async def get_attachment(
    attachment_id: uuid.UUID,
    request: Request,
    user: Annotated[CurrentUser | None, Depends(optional_user)] = None,
) -> RedirectResponse:
    """Public only when the file is on a visible post (in a hidden cluster: members only)."""
    bucket = _bucket()
    async with request.app.state.db.connect() as conn:
        row = (
            await conn.execute(
                text(_ATTACHMENT_SQL),
                {"id": attachment_id, "viewer": user.id if user else None},
            )
        ).one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    inline = files.TYPES[row.content_type].inline
    url: str = await run_in_threadpool(
        request.app.state.s3.generate_presigned_url,
        "get_object",
        Params={
            "Bucket": bucket,
            "Key": f"files/{attachment_id}",
            "ResponseContentType": row.content_type,
            "ResponseContentDisposition": "inline"
            if inline
            else f'attachment; filename="{row.filename}"',
        },
        ExpiresIn=LINK_SECONDS,
    )
    return RedirectResponse(url, status_code=307, headers={"Cache-Control": "private, max-age=300"})
