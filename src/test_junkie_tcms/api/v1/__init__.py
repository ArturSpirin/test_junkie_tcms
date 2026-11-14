from fastapi import APIRouter

from test_junkie_tcms.api.v1 import (
    attachments,
    audit,
    auth,
    cases,
    consumers,
    cycles,
    features,
    invites,
    jobs,
    orgs,
    pairing,
    plans,
    products,
    releases,
    results,
    tokens,
)

router = APIRouter(prefix="/api/v1")
router.include_router(auth.router)
router.include_router(orgs.router)
router.include_router(tokens.router)
router.include_router(invites.router)
router.include_router(audit.router)
router.include_router(products.router)
router.include_router(features.router)
router.include_router(releases.router)
router.include_router(plans.router)
router.include_router(cases.router)
router.include_router(cycles.router)
router.include_router(results.router)
router.include_router(attachments.router)
router.include_router(pairing.router)
router.include_router(consumers.router)
router.include_router(jobs.router)
