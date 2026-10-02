"""
AgentOS Procedural Memory.
Persists tool recipes, task runbooks, and failure postmortems as versioned files.
"""

from pathlib import Path
from typing import Dict, List, Optional
import yaml
from pydantic import BaseModel, Field


class ToolRecipe(BaseModel):
    name: str
    version: str
    description: str
    prerequisites: List[str] = Field(default_factory=list)
    steps: List[str] = Field(default_factory=list)
    failure_notes: List[str] = Field(default_factory=list)


class ProceduralStore:
    def __init__(self, storage_dir: str | Path = "data/recipes") -> None:
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def save_recipe(self, recipe: ToolRecipe) -> Path:
        target_path = self.storage_dir / f"{recipe.name}_v{recipe.version}.yaml"
        with open(target_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(recipe.model_dump(), f)
        return target_path

    def load_recipe(self, name: str, version: Optional[str] = None) -> Optional[ToolRecipe]:
        if version:
            candidate = self.storage_dir / f"{name}_v{version}.yaml"
            if candidate.exists():
                with open(candidate, "r", encoding="utf-8") as f:
                    return ToolRecipe.model_validate(yaml.safe_load(f))
            return None

        # Find latest version
        matches = sorted(self.storage_dir.glob(f"{name}_v*.yaml"))
        if not matches:
            return None
        with open(matches[-1], "r", encoding="utf-8") as f:
            return ToolRecipe.model_validate(yaml.safe_load(f))
