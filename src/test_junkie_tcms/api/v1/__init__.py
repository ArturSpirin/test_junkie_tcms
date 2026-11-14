from fastapi import APIRouter

from test_junkie_tcms.api.v1 import audit, auth, orgs, tokens

router = APIRouter(prefix="/api/v1")
router.include_router(auth.router)
router.include_router(orgs.router)
router.include_router(tokens.router)
router.include_router(audit.router)
