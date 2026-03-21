"""
Reports API package — aggregates all report sub-routers into a single router.
"""
from fastapi import APIRouter

from .spending import router as spending_router
from .income import router as income_router
from .balance import router as balance_router
from .debt import router as debt_router
from .wealth import router as wealth_router

router = APIRouter()
router.include_router(spending_router)
router.include_router(income_router)
router.include_router(balance_router)
router.include_router(debt_router)
router.include_router(wealth_router)
