from fastapi import APIRouter

api_router = APIRouter()


@api_router.get("/health")
def health():
    return {"status": "ok"}


def _include_all() -> None:
    # импорт здесь, чтобы избежать циклов при старте
    from app.api import (
        admin,
        audit,
        auth,
        bookings,
        customers,
        dashboard,
        messages,
        onboarding,
        reports,
        settings,
    )

    api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
    api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
    api_router.include_router(bookings.router, prefix="/bookings", tags=["bookings"])
    api_router.include_router(customers.router, prefix="/customers", tags=["customers"])
    api_router.include_router(messages.router, prefix="/messages", tags=["messages"])
    api_router.include_router(reports.router, prefix="/reports", tags=["reports"])
    api_router.include_router(settings.router, prefix="/settings", tags=["settings"])
    api_router.include_router(onboarding.router, prefix="/onboarding", tags=["onboarding"])
    api_router.include_router(audit.router, prefix="/audit", tags=["audit"])
    api_router.include_router(admin.router, prefix="/admin", tags=["admin"])


_include_all()
