"""Devices module models.

This module re-exports the shared SQLAlchemy `Device` model from
`app.models.device` for convenience inside devices package.
"""

from app.models.device import Device

__all__ = ["Device"]
