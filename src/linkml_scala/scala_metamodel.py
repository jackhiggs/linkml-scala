"""Python dataclasses for the Scala metamodel extensions.

These hand-written dataclasses mirror scala_metamodel.yaml.
The generated pydantic models live in scala_metamodel_gen.py;
CI validates that the two stay in sync (see ``make check-metamodel``).
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ParameterDefinition:
    name: str
    range: str
    default_value: Optional[str] = None


@dataclass
class OperationDefinition:
    name: str
    parameters: list["ParameterDefinition"] = field(default_factory=list)
    range: Optional[str] = None  # LinkML type name (string, integer, MyClass, etc.)
    multivalued: bool = False
    required: bool = True
    is_abstract: bool = True
    body: Optional[str] = None


@dataclass
class ScalaClassAnnotation:
    operations: list[OperationDefinition] = field(default_factory=list)
    is_interface: bool = False
    companion_object: bool = False

    @classmethod
    def from_annotation(cls, ann_value) -> "ScalaClassAnnotation":
        """Parse a ScalaClassAnnotation from a LinkML annotation value."""
        if not isinstance(ann_value, dict):
            return cls()
        ops = []
        for op_dict in ann_value.get("operations", []):
            params = []
            for p in op_dict.get("parameters", []):
                params.append(ParameterDefinition(
                    name=p["name"],
                    range=p["range"],
                    default_value=p.get("default_value"),
                ))
            ops.append(OperationDefinition(
                name=op_dict["name"],
                parameters=params,
                range=op_dict.get("range"),
                multivalued=op_dict.get("multivalued", False),
                required=op_dict.get("required", True),
                is_abstract=op_dict.get("is_abstract", True),
                body=op_dict.get("body"),
            ))
        return cls(
            operations=ops,
            is_interface=ann_value.get("is_interface", False),
            companion_object=ann_value.get("companion_object", False),
        )
