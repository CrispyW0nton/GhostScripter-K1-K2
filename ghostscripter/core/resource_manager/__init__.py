"""
GhostScripter-K1-K2 — Resource Manager Package
"""
from ghostscripter.core.resource_manager.resource_manager import (
    ResourceManager, KeyFile, BifFile, ErfReader, ResourceEntry,
    RESTYPE_EXT, EXT_RESTYPE,
)

__all__ = [
    "ResourceManager", "KeyFile", "BifFile", "ErfReader",
    "ResourceEntry", "RESTYPE_EXT", "EXT_RESTYPE",
]
