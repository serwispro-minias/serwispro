from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class ImportPayload:
    file_path: Path
    format_name: str


class InventoryImportAdapter:
    """Base adapter interface for future CSV/XML imports."""

    format_name: str = ""

    def can_handle(self, payload: ImportPayload) -> bool:
        return payload.format_name.lower() == self.format_name.lower()

    def parse(self, payload: ImportPayload) -> list[dict[str, object]]:
        raise NotImplementedError("Import adapter parsing is not implemented yet.")


class InventoryImportRegistry:
    """Registry architecture prepared for future CSV/XML import implementations."""

    def __init__(self) -> None:
        self._adapters: list[InventoryImportAdapter] = []

    def register(self, adapter: InventoryImportAdapter) -> None:
        self._adapters.append(adapter)

    def get_adapter(self, payload: ImportPayload) -> InventoryImportAdapter | None:
        for adapter in self._adapters:
            if adapter.can_handle(payload):
                return adapter
        return None
