#!/usr/bin/env python3
"""Check that scala_metamodel.py dataclasses stay in sync with scala_metamodel.yaml."""
import dataclasses
import sys
from pathlib import Path

from linkml_runtime.utils.schemaview import SchemaView

from linkml_scala.scala_metamodel import (
    OperationDefinition,
    ParameterDefinition,
    ScalaClassAnnotation,
)

YAML_PATH = Path(__file__).resolve().parent.parent / "src" / "linkml_scala" / "scala_metamodel.yaml"

CLASS_MAP = {
    "ParameterDefinition": ParameterDefinition,
    "OperationDefinition": OperationDefinition,
    "ScalaClassAnnotation": ScalaClassAnnotation,
}


def main() -> int:
    sv = SchemaView(str(YAML_PATH))
    errors: list[str] = []

    # Check that every YAML class has a corresponding Python class
    yaml_classes = set(sv.all_classes().keys())
    py_classes = set(CLASS_MAP.keys())
    for name in yaml_classes - py_classes:
        errors.append(f"Class {name} in YAML but not in Python")
    for name in py_classes - yaml_classes:
        errors.append(f"Class {name} in Python but not in YAML")

    # Check field-level sync for matching classes
    for cls_name in yaml_classes & py_classes:
        yaml_cls = sv.get_class(cls_name)
        yaml_attrs = set(yaml_cls.attributes.keys())
        py_fields = {f.name for f in dataclasses.fields(CLASS_MAP[cls_name])}
        missing = yaml_attrs - py_fields
        extra = py_fields - yaml_attrs
        if missing:
            errors.append(f"{cls_name}: fields in YAML but not in Python: {missing}")
        if extra:
            errors.append(f"{cls_name}: fields in Python but not in YAML: {extra}")

    if errors:
        print("SYNC ERRORS:")
        for e in errors:
            print(f"  - {e}")
        return 1

    print("Metamodel sync OK: all classes and fields match")
    return 0


if __name__ == "__main__":
    sys.exit(main())
