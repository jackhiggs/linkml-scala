"""Scala 3 code generator for LinkML schemas."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Union

import click
from jinja2 import Environment, PackageLoader
from linkml.utils.generator import Generator
from linkml_runtime.linkml_model.meta import (
    ClassDefinition,
    EnumDefinition,
    SchemaDefinition,
    SlotDefinition,
    TypeDefinition,
)
from linkml_runtime.utils.schemaview import SchemaView

from linkml_scala.scala_metamodel import OperationDefinition, ScalaClassAnnotation

TEMPLATES_DIR = Path(__file__).parent / "templates"

TYPE_MAP = {
    "string": "String",
    "integer": "Int",
    "float": "Double",
    "boolean": "Boolean",
    "double": "Double",
    "decimal": "BigDecimal",
    "date": "java.time.LocalDate",
    "datetime": "java.time.Instant",
    "uri": "java.net.URI",
    "uriorcurie": "java.net.URI",
    "ncname": "String",
    "nodeidentifier": "String",
    "objectidentifier": "java.net.URI",
}


@dataclass
class ScalaField:
    name: str
    scala_type: str
    default: str = ""


@dataclass
class ScalaOperation:
    name: str
    params_str: str
    return_type: str
    body: Optional[str] = None


class ScalaGenerator(Generator):
    """Generates Scala 3 case classes, traits, and enums from a LinkML schema."""

    generatorname = "ScalaGenerator"
    generatorversion = "0.1.0"
    valid_formats = ["scala"]

    def __init__(self, schema: str | SchemaDefinition, **kwargs):
        self.source_schema = schema
        self.schemaview: Optional[SchemaView] = None
        self.jinja_env = Environment(
            loader=PackageLoader("linkml_scala", "templates"),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.package_name = kwargs.pop("package_name", None)
        # Store but don't pass to super
        kwargs.pop("format", None)
        super().__init__(schema, **kwargs)

    def _get_schemaview(self) -> SchemaView:
        if self.schemaview is None:
            self.schemaview = SchemaView(self.source_schema)
        return self.schemaview

    def map_type(self, linkml_type: str) -> str:
        """Map a LinkML type name to a Scala type."""
        if linkml_type is None:
            return "Any"
        lower = linkml_type.lower()
        if lower in TYPE_MAP:
            return TYPE_MAP[lower]
        # Could be a class reference - use PascalCase
        return linkml_type

    def _slot_to_field(self, slot: SlotDefinition) -> ScalaField:
        """Convert a LinkML slot to a Scala field descriptor."""
        base_type = self.map_type(str(slot.range) if slot.range else "string")
        if slot.multivalued:
            scala_type = f"List[{base_type}]"
            default = " = List.empty"
        elif not slot.required:
            scala_type = f"Option[{base_type}]"
            default = " = None"
        else:
            scala_type = base_type
            default = ""
        name = self._to_camel_case(slot.name)
        return ScalaField(name=name, scala_type=scala_type, default=default)

    def _to_camel_case(self, name: str) -> str:
        """Convert snake_case to camelCase."""
        parts = name.split("_")
        return parts[0] + "".join(p.capitalize() for p in parts[1:])

    def _to_pascal_case(self, name: str) -> str:
        """Convert snake_case to PascalCase."""
        return "".join(p[0].upper() + p[1:] if p else "" for p in name.split("_"))

    def get_operations(self, cls: ClassDefinition) -> list[ScalaOperation]:
        """Extract operations from class annotations."""
        ann = self._get_scala_annotation(cls)
        if ann is None:
            return []
        ops = []
        for op in ann.operations:
            params = ", ".join(
                f"{p.name}: {self.map_type(p.range)}" for p in op.parameters
            )
            ops.append(ScalaOperation(
                name=op.name,
                params_str=params,
                return_type=op.return_type or "Unit",
                body=op.body,
            ))
        return ops

    def _get_scala_annotation(self, cls: ClassDefinition) -> Optional[ScalaClassAnnotation]:
        """Get ScalaClassAnnotation from a class's annotations."""
        if not cls.annotations:
            return None
        for ann_name, ann in cls.annotations.items():
            if ann_name == "scala" or (hasattr(ann, "tag") and ann.tag == "scala"):
                value = ann.value if hasattr(ann, "value") else ann
                # Convert to dict: could be JsonObj, JSON string, or dict
                if isinstance(value, str):
                    try:
                        value = json.loads(value)
                    except (json.JSONDecodeError, TypeError):
                        continue
                elif hasattr(value, "_as_dict"):
                    value = value._as_dict()
                elif hasattr(value, "__dict__") and not isinstance(value, dict):
                    value = {k: v for k, v in value.__dict__.items() if not k.startswith("_")}
                if isinstance(value, dict):
                    return ScalaClassAnnotation.from_annotation(value)
        return None

    def _is_trait(self, cls: ClassDefinition) -> bool:
        """Determine if a class should be generated as a trait."""
        if cls.mixin:
            return True
        if cls.abstract:
            return True
        ann = self._get_scala_annotation(cls)
        if ann and ann.is_interface:
            return True
        return False

    def _get_fields(self, cls: ClassDefinition) -> list[ScalaField]:
        """Get fields for a class from its slots."""
        sv = self._get_schemaview()
        fields = []
        for slot_name in sv.class_induced_slots(cls.name):
            slot = sv.get_slot(slot_name.name if hasattr(slot_name, "name") else slot_name)
            if slot:
                fields.append(self._slot_to_field(slot))
        return fields

    def _get_parent(self, cls: ClassDefinition) -> Optional[str]:
        if cls.is_a:
            return self._to_pascal_case(cls.is_a)
        return None

    def _get_mixins(self, cls: ClassDefinition) -> list[str]:
        return [self._to_pascal_case(m) for m in (cls.mixins or [])]

    def generate_class(self, cls: ClassDefinition) -> str:
        """Generate Scala code for a class (dispatches to case class or trait)."""
        if self._is_trait(cls):
            return self.generate_trait(cls)
        return self.generate_case_class(cls)

    def generate_case_class(self, cls: ClassDefinition) -> str:
        """Render a case class from a ClassDefinition."""
        template = self.jinja_env.get_template("scala_class.scala.jinja2")
        return template.render(
            name=self._to_pascal_case(cls.name),
            fields=self._get_fields(cls),
            parent=self._get_parent(cls),
            mixins=self._get_mixins(cls),
        )

    def generate_trait(self, cls: ClassDefinition) -> str:
        """Render a trait from a ClassDefinition."""
        template = self.jinja_env.get_template("scala_trait.scala.jinja2")
        return template.render(
            name=self._to_pascal_case(cls.name),
            fields=self._get_fields(cls),
            parent=self._get_parent(cls),
            mixins=self._get_mixins(cls),
            operations=self.get_operations(cls),
        )

    def generate_enum(self, enum: EnumDefinition) -> str:
        """Render a Scala 3 enum."""
        template = self.jinja_env.get_template("scala_enum.scala.jinja2")
        values = [self._to_pascal_case(pv.text) for pv in enum.permissible_values.values()]
        return template.render(
            name=self._to_pascal_case(enum.name),
            values=values,
        )

    def generate_type_alias(self, typedef: TypeDefinition) -> str:
        """Generate a type alias."""
        scala_type = self.map_type(str(typedef.typeof) if typedef.typeof else "string")
        return f"type {self._to_pascal_case(typedef.name)} = {scala_type}"

    def serialize(self, **kwargs) -> str:
        """Generate complete Scala source from the schema."""
        sv = self._get_schemaview()
        schema = sv.schema
        parts: list[str] = []

        # Package declaration
        pkg = self.package_name or schema.name.replace("-", ".").replace("_", ".")
        parts.append(f"package {pkg}\n")

        # Type aliases
        for type_name, typedef in (schema.types or {}).items():
            if typedef.typeof:
                parts.append(self.generate_type_alias(typedef))

        # Enums
        for enum_name, enum_def in (schema.enums or {}).items():
            parts.append(self.generate_enum(enum_def))

        # Classes (traits first, then case classes)
        traits = []
        case_classes = []
        for class_name in sv.all_classes():
            cls = sv.get_class(class_name)
            if self._is_trait(cls):
                traits.append(cls)
            else:
                case_classes.append(cls)

        for cls in traits:
            parts.append(self.generate_trait(cls))

        for cls in case_classes:
            parts.append(self.generate_case_class(cls))

        return "\n\n".join(parts) + "\n"


@click.command(name="gen-scala")
@click.argument("schema", type=click.Path(exists=True))
@click.option("-o", "--output", type=click.Path(), default=None, help="Output file path")
@click.option("--package", "package_name", default=None, help="Scala package name")
def cli(schema: str, output: str | None, package_name: str | None):
    """Generate Scala 3 code from a LinkML schema."""
    gen = ScalaGenerator(schema, package_name=package_name)
    result = gen.serialize()
    if output:
        out_path = Path(output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(result)
        click.echo(f"Generated {out_path}")
    else:
        click.echo(result)


if __name__ == "__main__":
    cli()
