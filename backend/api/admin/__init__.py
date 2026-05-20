from fastapi import APIRouter, Depends

from api.admin.dependencies import rate_limit
from api.admin.dashboard import router as dashboard_router
from api.admin.aigc import router as aigc_router
from api.admin.persona import router as persona_router
from api.admin.memory import router as memory_router
from api.admin.users import router as users_router
from api.admin.commerce import router as commerce_router
from api.admin.devops import router as devops_router
from api.admin.assets import router as assets_router
from api.admin.outfits import router as outfits_router
from api.admin.scenes import router as scenes_router
from api.admin.subscriptions import router as subscriptions_router
from api.admin.launches import router as launches_router
from api.admin.world_events import router as world_events_router

admin_router = APIRouter(
    prefix="/api/admin",
    tags=["admin"],
    dependencies=[Depends(rate_limit)],
)

admin_router.include_router(dashboard_router)
admin_router.include_router(aigc_router)
admin_router.include_router(persona_router)
admin_router.include_router(memory_router)
admin_router.include_router(users_router)
admin_router.include_router(commerce_router)
admin_router.include_router(devops_router)
admin_router.include_router(assets_router)
admin_router.include_router(outfits_router)
admin_router.include_router(scenes_router)
admin_router.include_router(subscriptions_router)
admin_router.include_router(launches_router)
admin_router.include_router(world_events_router)
