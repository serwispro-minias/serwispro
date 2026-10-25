from __future__ import annotations

import logging
from pathlib import Path

import click
from flask import Flask, current_app

from .retention import cleanup_expired_order_photos

logger = logging.getLogger(__name__)


def register_cli(app: Flask) -> None:
    @app.cli.command("cleanup-service-order-photos")
    @click.option("--retention-days", type=click.IntRange(min=1), default=60, show_default=True)
    def cleanup_service_order_photos(retention_days: int) -> None:
        """Remove private photos for orders terminal for at least RETENTION_DAYS."""
        configured = current_app.config.get("UPLOAD_FOLDER")
        upload_root = Path(configured).resolve() if configured else (Path(current_app.root_path).parent / "uploads").resolve()
        result = cleanup_expired_order_photos(upload_root=upload_root, retention_days=retention_days)
        click.echo(
            "Service-order photo cleanup: "
            f"lock_acquired={result['lock_acquired']} "
            f"orders_scanned={result['orders_scanned']} "
            f"photos_deleted={result['photos_deleted']} "
            f"errors={result['errors']}"
        )
        if int(result["errors"]):
            logger.warning("Service-order photo cleanup completed with errors: %s", result)
            raise click.ClickException("Część zdjęć nie została usunięta; aktywne metadane zachowano do ponowienia.")
