import uuid
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import AdminUser, DBSession
from app.core.exceptions import ConflictError, NotFoundError
from app.models.distribution_list import DistributionList, DistributionListMember
from app.schemas.distribution_list import (
    DistributionListCreate,
    DistributionListMemberCreate,
    DistributionListMemberResponse,
    DistributionListResponse,
    DistributionListUpdate,
)
from app.services.audit_service import write_audit_log

router = APIRouter(prefix="/distribution-lists", tags=["Distribution Lists"])


@router.get(
    "",
    response_model=list[DistributionListResponse],
    summary="List all distribution lists with member count (admin)",
)
async def list_distribution_lists(
    db: DBSession,
    current_user: AdminUser,
) -> list[DistributionListResponse]:
    stmt = (
        select(DistributionList, func.count(DistributionListMember.id).label("member_count"))
        .outerjoin(DistributionListMember, DistributionListMember.list_id == DistributionList.id)
        .group_by(DistributionList.id)
        .order_by(DistributionList.name.asc())
    )
    res = await db.execute(stmt)
    items = []
    for dl, count in res.all():
        items.append(
            DistributionListResponse(
                id=dl.id,
                name=dl.name,
                description=dl.description,
                created_by=dl.created_by,
                created_at=dl.created_at,
                member_count=count,
            )
        )
    return items


@router.post(
    "",
    response_model=DistributionListResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new distribution list (admin)",
)
async def create_distribution_list(
    payload: DistributionListCreate,
    db: DBSession,
    current_user: AdminUser,
) -> DistributionListResponse:
    dl = DistributionList(
        name=payload.name,
        description=payload.description,
        created_by=current_user.id,
    )
    db.add(dl)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise ConflictError(f"Distribution list with name '{payload.name}' already exists.") from exc

    await write_audit_log(
        db,
        action="distribution_list.created",
        resource_type="distribution_list",
        actor_id=current_user.id,
        resource_id=dl.id,
        payload={"name": dl.name, "description": dl.description},
    )

    return DistributionListResponse(
        id=dl.id,
        name=dl.name,
        description=dl.description,
        created_by=dl.created_by,
        created_at=dl.created_at,
        member_count=0,
    )


@router.patch(
    "/{list_id}",
    response_model=DistributionListResponse,
    summary="Update distribution list details (admin)",
)
async def update_distribution_list(
    list_id: uuid.UUID,
    payload: DistributionListUpdate,
    db: DBSession,
    current_user: AdminUser,
) -> DistributionListResponse:
    dl = await db.get(DistributionList, list_id)
    if not dl:
        raise NotFoundError("DistributionList")

    if payload.name is not None:
        dl.name = payload.name
    if payload.description is not None:
        dl.description = payload.description

    try:
        await db.flush()
    except IntegrityError as exc:
        raise ConflictError(f"Distribution list with name '{payload.name}' already exists.") from exc

    # Count members
    cnt_stmt = select(func.count(DistributionListMember.id)).where(
        DistributionListMember.list_id == list_id
    )
    cnt_res = await db.execute(cnt_stmt)
    count = cnt_res.scalar_one()

    await write_audit_log(
        db,
        action="distribution_list.updated",
        resource_type="distribution_list",
        actor_id=current_user.id,
        resource_id=dl.id,
        payload={"name": dl.name, "description": dl.description},
    )

    return DistributionListResponse(
        id=dl.id,
        name=dl.name,
        description=dl.description,
        created_by=dl.created_by,
        created_at=dl.created_at,
        member_count=count,
    )


@router.delete(
    "/{list_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a distribution list (admin)",
)
async def delete_distribution_list(
    list_id: uuid.UUID,
    db: DBSession,
    current_user: AdminUser,
) -> None:
    dl = await db.get(DistributionList, list_id)
    if not dl:
        raise NotFoundError("DistributionList")

    await db.delete(dl)
    await db.flush()

    await write_audit_log(
        db,
        action="distribution_list.deleted",
        resource_type="distribution_list",
        actor_id=current_user.id,
        resource_id=list_id,
        payload={"name": dl.name},
    )


@router.get(
    "/{list_id}/members",
    response_model=list[DistributionListMemberResponse],
    summary="List members of a distribution list (admin)",
)
async def list_members(
    list_id: uuid.UUID,
    db: DBSession,
    current_user: AdminUser,
) -> list[DistributionListMemberResponse]:
    dl = await db.get(DistributionList, list_id)
    if not dl:
        raise NotFoundError("DistributionList")

    stmt = select(DistributionListMember).where(DistributionListMember.list_id == list_id).order_by(DistributionListMember.email.asc())
    res = await db.execute(stmt)
    return list(res.scalars().all())


@router.post(
    "/{list_id}/members",
    response_model=DistributionListMemberResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add email recipient to a distribution list (admin)",
)
async def add_member(
    list_id: uuid.UUID,
    payload: DistributionListMemberCreate,
    db: DBSession,
    current_user: AdminUser,
) -> DistributionListMemberResponse:
    dl = await db.get(DistributionList, list_id)
    if not dl:
        raise NotFoundError("DistributionList")

    member = DistributionListMember(
        list_id=list_id,
        email=payload.email.strip().lower(),
        name=payload.name,
        is_active=payload.is_active,
    )
    db.add(member)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise ConflictError(f"Email '{payload.email}' is already a member of this list.") from exc

    await write_audit_log(
        db,
        action="distribution_list.member_added",
        resource_type="distribution_list_member",
        actor_id=current_user.id,
        resource_id=member.id,
        payload={"list_id": str(list_id), "email": member.email, "name": member.name},
    )

    return member


@router.delete(
    "/{list_id}/members/{email}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove email recipient from a distribution list (admin)",
)
async def remove_member(
    list_id: uuid.UUID,
    email: str,
    db: DBSession,
    current_user: AdminUser,
) -> None:
    dl = await db.get(DistributionList, list_id)
    if not dl:
        raise NotFoundError("DistributionList")

    stmt = select(DistributionListMember).where(
        DistributionListMember.list_id == list_id,
        DistributionListMember.email == email.strip().lower(),
    )
    res = await db.execute(stmt)
    member = res.scalar_one_or_none()
    if not member:
        raise NotFoundError("DistributionListMember")

    await db.delete(member)
    await db.flush()

    await write_audit_log(
        db,
        action="distribution_list.member_removed",
        resource_type="distribution_list_member",
        actor_id=current_user.id,
        resource_id=member.id,
        payload={"list_id": str(list_id), "email": email},
    )
