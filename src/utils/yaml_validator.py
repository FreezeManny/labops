from typing import Dict, Any, Optional
from pydantic import ValidationError
import os
from pathlib import Path

from models.inputConf.YamlRoot import YamlRoot


def validate_yaml(raw: Dict[str, Any], rootPath: str) -> Optional[YamlRoot]:
    base_dir: Path = Path(rootPath).parent.resolve()
    original_dir: str = os.getcwd()
    os.chdir(base_dir)

    model = None
    try:
        try:
            model = YamlRoot(**raw)
        except ValidationError as e:
            print("Validation error in YAML structure:")
            print(e)
    finally:
        os.chdir(original_dir)

    return model