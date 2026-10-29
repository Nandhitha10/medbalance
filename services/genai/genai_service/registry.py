"""Prompt registry for MedBalance GenAI gateway."""

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import jinja2
import jsonschema
import yaml

logger = logging.getLogger(__name__)


@dataclass
class PromptDefinition:
    id: str
    version: str
    model: str = "fast"
    temperature: float = 0.0
    max_tokens: int = 1024
    system: str = ""
    user_template: str = ""
    json_schema: Dict[str, Any] = field(default_factory=dict)
    tools: Optional[List[Dict[str, Any]]] = None
    file_path: Optional[Path] = None
    mtime: float = 0.0

    def render(self, input_vars: Dict[str, Any]) -> str:
        """Render user_template using Jinja2 with input variables."""
        env = jinja2.Environment(
            autoescape=False,
            undefined=jinja2.ChainableUndefined,
        )
        template = env.from_string(self.user_template)
        return template.render(**input_vars)

    def validate_schema(self, data: Any) -> Tuple[bool, Optional[str]]:
        """Validate output dictionary against json_schema."""
        if not self.json_schema:
            return True, None
        try:
            jsonschema.validate(instance=data, schema=self.json_schema)
            return True, None
        except jsonschema.ValidationError as err:
            return False, err.message
        except Exception as e:
            return False, str(e)


def normalize_version(version: Union[str, int]) -> str:
    """Normalize version string/int (e.g., 1 -> '1', 'v1' -> '1')."""
    v_str = str(version).strip().lower()
    if v_str.startswith("v") and len(v_str) > 1 and v_str[1:].isdigit():
        return v_str[1:]
    return v_str


class PromptRegistry:
    """Registry that loads, caches, and hot-reloads YAML prompt definitions."""

    def __init__(self, prompts_dir: Optional[Union[str, Path]] = None) -> None:
        self.prompts_dir = Path(prompts_dir) if prompts_dir else self._find_prompts_dir()
        self._prompts: Dict[str, PromptDefinition] = {}
        self.load_all()

    @staticmethod
    def _find_prompts_dir() -> Path:
        candidates = [
            Path.cwd() / "prompts",
            Path(__file__).resolve().parent.parent.parent.parent / "prompts",
            Path("/app/prompts"),
        ]
        for c in candidates:
            if c.exists() and c.is_dir():
                return c
        return Path.cwd() / "prompts"

    def _make_key(self, prompt_id: str, version: Union[str, int]) -> str:
        norm_v = normalize_version(version)
        return f"{prompt_id.strip()}@{norm_v}"

    def load_all(self) -> None:
        """Scan directory and load all YAML prompt files."""
        if not self.prompts_dir.exists():
            logger.warning(f"Prompts directory does not exist: {self.prompts_dir}")
            return

        count = 0
        for file in self.prompts_dir.glob("*.yaml"):
            try:
                self.load_file(file)
                count += 1
            except Exception as e:
                logger.error(f"Failed to load prompt file {file}: {e}")

        for file in self.prompts_dir.glob("*.yml"):
            try:
                self.load_file(file)
                count += 1
            except Exception as e:
                logger.error(f"Failed to load prompt file {file}: {e}")

        logger.info(f"Loaded {count} prompts from {self.prompts_dir}")

    def load_file(self, path: Path) -> Optional[PromptDefinition]:
        """Load single YAML prompt definition."""
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not isinstance(data, dict):
            return None

        prompt_id = str(data.get("id", path.stem.split("_v")[0]))
        raw_version = data.get("version", 1)
        norm_version = normalize_version(raw_version)

        pdef = PromptDefinition(
            id=prompt_id,
            version=norm_version,
            model=data.get("model", "fast"),
            temperature=float(data.get("temperature", 0.0)),
            max_tokens=int(data.get("max_tokens", 1024)),
            system=str(data.get("system", "")),
            user_template=str(data.get("user_template", "")),
            json_schema=data.get("json_schema", {}),
            tools=data.get("tools"),
            file_path=path,
            mtime=path.stat().st_mtime,
        )

        key = self._make_key(prompt_id, norm_version)
        self._prompts[key] = pdef
        # Also map raw version if different
        raw_key = f"{prompt_id.strip()}@{raw_version}"
        self._prompts[raw_key] = pdef

        return pdef

    def get(self, prompt_id: str, version: Union[str, int]) -> Optional[PromptDefinition]:
        """Retrieve a prompt definition, hot-reloading if modified."""
        self.reload_if_modified()
        key = self._make_key(prompt_id, version)
        if key in self._prompts:
            return self._prompts[key]
        raw_key = f"{prompt_id.strip()}@{version}"
        return self._prompts.get(raw_key)

    def reload_if_modified(self) -> None:
        """Check file mtimes and reload any modified prompts."""
        if not self.prompts_dir.exists():
            return

        for file in list(self.prompts_dir.glob("*.yaml")) + list(self.prompts_dir.glob("*.yml")):
            try:
                mtime = file.stat().st_mtime
                # Check if new file or modified
                existing = None
                for p in self._prompts.values():
                    if p.file_path == file:
                        existing = p
                        break
                if existing is None or mtime > existing.mtime:
                    self.load_file(file)
            except Exception as e:
                logger.debug(f"Error checking {file}: {e}")

    def list_prompts(self) -> List[Dict[str, Any]]:
        """List summary of all loaded prompts."""
        return [
            {
                "id": p.id,
                "version": p.version,
                "model": p.model,
                "file": str(p.file_path) if p.file_path else None,
            }
            for p in self._prompts.values()
        ]
