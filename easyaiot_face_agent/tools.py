"""Compatibility exports; implementation lives in tools/service and demo/repository."""
from .demo.repository import SyntheticFaceRepository
from .tools.service import FaceAnalysisTools, TOOL_CATALOG, normalize_uploaded_image

__all__ = ["FaceAnalysisTools", "SyntheticFaceRepository", "TOOL_CATALOG", "normalize_uploaded_image"]
