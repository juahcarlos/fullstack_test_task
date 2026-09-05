"""Сборка общего APIRouter из отдельных роутеров files и alerts."""

from fastapi import APIRouter

from app.api import alerts, files

api_router = APIRouter()
api_router.include_router(files.router)
api_router.include_router(alerts.router)