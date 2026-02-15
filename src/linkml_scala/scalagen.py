"""Scala 3 code generator for LinkML schemas."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

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

from linkml_scala.scala_metamodel import ScalaClassAnnotation

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

# Scala types that need custom circe codecs (no built-in support)
CUSTOM_CODEC_TYPES = {
    "java.time.LocalDate",
    "java.time.Instant",
    "java.net.URI",
}

MAPPING_CATEGORIES = [
    ("exact_mappings", "Exact mapping"),
    ("close_mappings", "Close mapping"),
    ("broad_mappings", "Broad mapping"),
    ("narrow_mappings", "Narrow mapping"),
    ("related_mappings", "Related mapping"),
]


@dataclass
class ScalaField:
    name: str
    scala_type: str
    default: str = ""
    description: str = ""
    identifier: bool = False
    pattern: str = ""
    minimum_value: Optional[float] = None
    maximum_value: Optional[float] = None
    minimum_cardinality: Optional[int] = None
    maximum_cardinality: Optional[int] = None
    equals_string: str = ""
    equals_string_in: list[str] = field(default_factory=list)
    equals_number: Optional[float] = None
    exact_cardinality: Optional[int] = None
    value_presence: str = ""  # "PRESENT", "ABSENT", or ""


@dataclass
class ScalaOperation:
    name: str
    params_str: str
    return_type: str
    body: Optional[str] = None


@dataclass
class RuleCondition:
    field: str
    op: str
    value: str
    is_optional: bool = True
    error_value: str = ""  # escaped version of value for error messages

    def __iter__(self):
        """Support tuple unpacking: field, op, value = condition."""
        return iter((self.field, self.op, self.value))


@dataclass
class RuleCheck:
    name: str
    description: str
    preconditions: list[RuleCondition] = field(default_factory=list)
    postconditions: list[RuleCondition] = field(default_factory=list)
    elseconditions: list[RuleCondition] = field(default_factory=list)
    deactivated: bool = False
    bidirectional: bool = False
    open_world: bool = False


@dataclass
class EnumValue:
    name: str
    description: str = ""
    meaning: str = ""
    linkml_name: str = ""


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
        self.codecs = kwargs.pop("codecs", "none")  # "none", "inline", or "separate"
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

    def _normalize_value_presence(self, vp) -> str:
        """Extract a PRESENT/ABSENT string from a value_presence attribute."""
        if not vp:
            return ""
        # Could be a PermissibleValue, enum, or string
        if hasattr(vp, "text"):
            return str(vp.text).upper()
        s = str(vp).upper()
        if "PRESENT" in s:
            return "PRESENT"
        if "ABSENT" in s:
            return "ABSENT"
        return s

    def _slot_to_field(self, slot: SlotDefinition, cls: ClassDefinition | None = None) -> ScalaField:
        """Convert a LinkML slot to a Scala field descriptor."""
        base_type = self.map_type(str(slot.range) if slot.range else "string")

        # Apply slot_usage overrides
        effective_required = slot.required
        effective_pattern = getattr(slot, "pattern", None) or ""
        effective_min_val = getattr(slot, "minimum_value", None)
        effective_max_val = getattr(slot, "maximum_value", None)
        effective_min_card = getattr(slot, "minimum_cardinality", None)
        effective_max_card = getattr(slot, "maximum_cardinality", None)
        effective_equals_string = getattr(slot, "equals_string", None) or ""
        effective_equals_string_in = list(getattr(slot, "equals_string_in", None) or [])
        effective_equals_number = getattr(slot, "equals_number", None)
        effective_exact_cardinality = getattr(slot, "exact_cardinality", None)
        effective_value_presence = self._normalize_value_presence(getattr(slot, "value_presence", None))
        effective_identifier = getattr(slot, "identifier", False) or getattr(slot, "key", False)
        effective_description = getattr(slot, "description", None) or ""

        if cls and cls.slot_usage:
            usage = cls.slot_usage.get(slot.name)
            if usage:
                if usage.required is not None:
                    effective_required = usage.required
                if getattr(usage, "pattern", None):
                    effective_pattern = usage.pattern
                if getattr(usage, "minimum_value", None) is not None:
                    effective_min_val = usage.minimum_value
                if getattr(usage, "maximum_value", None) is not None:
                    effective_max_val = usage.maximum_value
                if getattr(usage, "minimum_cardinality", None) is not None:
                    effective_min_card = usage.minimum_cardinality
                if getattr(usage, "maximum_cardinality", None) is not None:
                    effective_max_card = usage.maximum_cardinality
                if getattr(usage, "equals_string", None):
                    effective_equals_string = usage.equals_string
                if getattr(usage, "equals_string_in", None):
                    effective_equals_string_in = list(usage.equals_string_in)
                if getattr(usage, "equals_number", None) is not None:
                    effective_equals_number = usage.equals_number
                if getattr(usage, "exact_cardinality", None) is not None:
                    effective_exact_cardinality = usage.exact_cardinality
                vp = getattr(usage, "value_presence", None)
                if vp:
                    effective_value_presence = self._normalize_value_presence(vp)

        if slot.multivalued:
            scala_type = f"List[{base_type}]"
            default = " = List.empty"
        elif not effective_required:
            scala_type = f"Option[{base_type}]"
            default = " = None"
        else:
            scala_type = base_type
            default = ""
        name = self._to_camel_case(slot.name)
        return ScalaField(
            name=name,
            scala_type=scala_type,
            default=default,
            description=effective_description,
            identifier=bool(effective_identifier),
            pattern=effective_pattern.replace("\\", "\\\\"),
            minimum_value=float(effective_min_val) if effective_min_val is not None else None,
            maximum_value=float(effective_max_val) if effective_max_val is not None else None,
            minimum_cardinality=int(effective_min_card) if effective_min_card is not None else None,
            maximum_cardinality=int(effective_max_card) if effective_max_card is not None else None,
            equals_string=effective_equals_string,
            equals_string_in=effective_equals_string_in,
            equals_number=float(effective_equals_number) if effective_equals_number is not None else None,
            exact_cardinality=int(effective_exact_cardinality) if effective_exact_cardinality is not None else None,
            value_presence=effective_value_presence,
        )

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
            # Resolve return type using the same logic as slot ranges
            if op.range:
                base_type = self.map_type(op.range)
                if op.multivalued:
                    return_type = f"List[{base_type}]"
                elif not op.required:
                    return_type = f"Option[{base_type}]"
                else:
                    return_type = base_type
            else:
                return_type = "Unit"
            ops.append(ScalaOperation(
                name=op.name,
                params_str=params,
                return_type=return_type,
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
        # union_of classes become sealed traits
        if getattr(cls, "union_of", None):
            return True
        return False

    def _is_sealed(self, cls: ClassDefinition) -> bool:
        """Determine if a trait should be sealed."""
        if getattr(cls, "children_are_mutually_disjoint", False):
            return True
        if getattr(cls, "union_of", None):
            return True
        return False

    def _get_fields(self, cls: ClassDefinition) -> list[ScalaField]:
        """Get fields for a class from its slots."""
        sv = self._get_schemaview()
        fields = []
        for slot_name in sv.class_induced_slots(cls.name):
            slot = sv.get_slot(slot_name.name if hasattr(slot_name, "name") else slot_name)
            if slot:
                fields.append(self._slot_to_field(slot, cls))
        return fields

    def _get_parent(self, cls: ClassDefinition) -> Optional[str]:
        if cls.is_a:
            return self._to_pascal_case(cls.is_a)
        return None

    def _get_mixins(self, cls: ClassDefinition) -> list[str]:
        return [self._to_pascal_case(m) for m in (cls.mixins or [])]

    def _get_mappings(self, element) -> list[str]:
        """Extract @see lines from mappings on a class/enum/slot."""
        see_lines = []
        for attr, label in MAPPING_CATEGORIES:
            mappings = getattr(element, attr, None) or []
            for m in mappings:
                see_lines.append(f"{label}: {m}")
        return see_lines

    def _get_unique_keys(self, cls: ClassDefinition) -> list[str]:
        """Get unique key documentation lines."""
        keys = []
        if getattr(cls, "unique_keys", None):
            for uk_name, uk in cls.unique_keys.items():
                slots = list(getattr(uk, "unique_key_slots", []))
                if slots:
                    keys.append(f"Unique key: ({', '.join(slots)})")
        return keys

    def _get_enum_type_for_field(self, field_info: ScalaField) -> str | None:
        """Return the enum type name if the field's Scala type is an enum, else None."""
        sv = self._get_schemaview()
        enum_names = {self._to_pascal_case(e) for e in sv.all_enums()}
        # Extract base type from Option[T], List[T], or plain T
        base = field_info.scala_type
        for wrapper in ("Option[", "List["):
            if base.startswith(wrapper) and base.endswith("]"):
                base = base[len(wrapper):-1]
        return base if base in enum_names else None

    def _extract_slot_conditions(self, class_expr, fields_by_name: dict[str, ScalaField] | None = None) -> list[RuleCondition]:
        """Extract slot conditions from a class expression (pre/post/else conditions).

        Returns list of RuleCondition objects with type-aware field info.
        """
        conditions: list[RuleCondition] = []
        if class_expr is None:
            return conditions
        if getattr(class_expr, "slot_conditions", None):
            for slot_name, cond in class_expr.slot_conditions.items():
                field_name = self._to_camel_case(slot_name)
                field_info = fields_by_name.get(field_name) if fields_by_name else None
                is_optional = field_info is None or "Option[" in field_info.scala_type
                if getattr(cond, "minimum_value", None) is not None:
                    conditions.append(RuleCondition(
                        field=field_name, op=">=", value=str(cond.minimum_value),
                        is_optional=is_optional, error_value=str(cond.minimum_value),
                    ))
                if getattr(cond, "maximum_value", None) is not None:
                    conditions.append(RuleCondition(
                        field=field_name, op="<=", value=str(cond.maximum_value),
                        is_optional=is_optional, error_value=str(cond.maximum_value),
                    ))
                if getattr(cond, "equals_string", None):
                    raw = cond.equals_string
                    # Check if field type is an enum — use enum value reference instead of string
                    enum_type = self._get_enum_type_for_field(field_info) if field_info else None
                    if enum_type:
                        value = f"{enum_type}.{self._to_pascal_case(raw)}"
                    else:
                        value = f'"{raw}"'
                    conditions.append(RuleCondition(
                        field=field_name, op="==", value=value,
                        is_optional=is_optional, error_value=raw,
                    ))
                if getattr(cond, "equals_number", None) is not None:
                    conditions.append(RuleCondition(
                        field=field_name, op="==", value=str(cond.equals_number),
                        is_optional=is_optional, error_value=str(cond.equals_number),
                    ))
        # Recurse into combinators on the class expression
        for combinator in ("any_of", "all_of", "exactly_one_of", "none_of"):
            sub_exprs = getattr(class_expr, combinator, None)
            if sub_exprs:
                for sub_expr in sub_exprs:
                    conditions.extend(self._extract_slot_conditions(sub_expr, fields_by_name))
        return conditions

    def _get_rules(self, cls: ClassDefinition) -> list[RuleCheck]:
        """Extract rules from a class definition."""
        rules = []
        if not getattr(cls, "rules", None):
            return rules
        fields = self._get_fields(cls)
        fields_by_name = {f.name: f for f in fields}
        for i, rule in enumerate(cls.rules):
            # Skip deactivated rules
            if getattr(rule, "deactivated", False):
                continue
            desc = getattr(rule, "description", None) or f"rule_{i}"
            name = self._to_camel_case(desc.replace(" ", "_").lower())
            bidirectional = bool(getattr(rule, "bidirectional", False))
            open_world = bool(getattr(rule, "open_world", False))
            rc = RuleCheck(
                name=name,
                description=desc,
                bidirectional=bidirectional,
                open_world=open_world,
            )
            rc.preconditions = self._extract_slot_conditions(getattr(rule, "preconditions", None), fields_by_name)
            rc.postconditions = self._extract_slot_conditions(getattr(rule, "postconditions", None), fields_by_name)
            rc.elseconditions = self._extract_slot_conditions(getattr(rule, "elseconditions", None), fields_by_name)
            rules.append(rc)
        return rules

    def _has_constraints(self, fields: list[ScalaField]) -> bool:
        """Check if any field has constraints that need validation."""
        for f in fields:
            if f.pattern or f.minimum_value is not None or f.maximum_value is not None:
                return True
            if f.minimum_cardinality is not None or f.maximum_cardinality is not None:
                return True
            if f.equals_string or f.equals_string_in:
                return True
            if f.equals_number is not None or f.exact_cardinality is not None:
                return True
            if f.value_presence:
                return True
        return False

    def generate_scaladoc(self, element, indent: str = "") -> str:
        """Generate a ScalaDoc comment block."""
        lines = []
        desc = getattr(element, "description", None)
        if desc:
            lines.append(desc)

        see_lines = self._get_mappings(element)
        unique_keys = []
        if isinstance(element, ClassDefinition):
            unique_keys = self._get_unique_keys(element)
            if getattr(element, "tree_root", False):
                lines.append("")
                lines.append("This is the tree root.")

        if not lines and not see_lines and not unique_keys:
            return ""

        parts = [f"{indent}/**"]
        for line in lines:
            parts.append(f"{indent} * {line}" if line else f"{indent} *")
        if see_lines:
            if lines:
                parts.append(f"{indent} *")
            for s in see_lines:
                parts.append(f"{indent} * @see {s}")
        if unique_keys:
            if lines or see_lines:
                parts.append(f"{indent} *")
            for k in unique_keys:
                parts.append(f"{indent} * @note {k}")
        parts.append(f"{indent} */")
        return "\n".join(parts)

    def generate_class(self, cls: ClassDefinition) -> str:
        """Generate Scala code for a class (dispatches to case class or trait)."""
        if self._is_trait(cls):
            return self.generate_trait(cls)
        return self.generate_case_class(cls)

    def generate_case_class(self, cls: ClassDefinition) -> str:
        """Render a case class from a ClassDefinition."""
        template = self.jinja_env.get_template("scala_class.scala.jinja2")
        fields = self._get_fields(cls)
        scaladoc = self.generate_scaladoc(cls)
        deprecated = bool(getattr(cls, "deprecated", None))
        name = self._to_pascal_case(cls.name)

        result = template.render(
            name=name,
            fields=fields,
            parent=self._get_parent(cls),
            mixins=self._get_mixins(cls),
            scaladoc=scaladoc,
            deprecated=deprecated,
        )

        # Generate companion object if there are constraints, rules, or codecs
        rules = self._get_rules(cls)
        needs_companion = self._has_constraints(fields) or rules or self.codecs == "inline"
        if needs_companion:
            companion = self.generate_companion(name, fields, rules)
            result = result.rstrip() + "\n\n" + companion

        return result

    def generate_trait(self, cls: ClassDefinition) -> str:
        """Render a trait from a ClassDefinition."""
        template = self.jinja_env.get_template("scala_trait.scala.jinja2")
        scaladoc = self.generate_scaladoc(cls)
        sealed = self._is_sealed(cls)
        return template.render(
            name=self._to_pascal_case(cls.name),
            fields=self._get_fields(cls),
            parent=self._get_parent(cls),
            mixins=self._get_mixins(cls),
            operations=self.get_operations(cls),
            scaladoc=scaladoc,
            sealed=sealed,
        )

    def generate_companion(self, class_name: str, fields: list[ScalaField], rules: list[RuleCheck]) -> str:
        """Generate a companion object with validate method and optional codecs."""
        template = self.jinja_env.get_template("scala_companion.scala.jinja2")
        has_validation = self._has_constraints(fields) or rules
        return template.render(
            name=class_name,
            fields=fields,
            rules=rules,
            codecs=self.codecs,
            has_validation=has_validation,
        )

    def generate_enum(self, enum: EnumDefinition) -> str:
        """Render a Scala 3 enum."""
        template = self.jinja_env.get_template("scala_enum.scala.jinja2")
        values = []
        for pv in enum.permissible_values.values():
            values.append(EnumValue(
                name=self._to_pascal_case(pv.text),
                description=getattr(pv, "description", None) or "",
                meaning=getattr(pv, "meaning", None) or "",
                linkml_name=pv.text,
            ))
        scaladoc = self.generate_scaladoc(enum)
        enum_name = self._to_pascal_case(enum.name)
        return template.render(
            name=enum_name,
            values=values,
            scaladoc=scaladoc,
            codecs=self.codecs,
        )

    def generate_type_alias(self, typedef: TypeDefinition) -> str:
        """Generate a type alias."""
        scala_type = self.map_type(str(typedef.typeof) if typedef.typeof else "string")
        return f"type {self._to_pascal_case(typedef.name)} = {scala_type}"

    def _get_union_parents(self, cls: ClassDefinition) -> list[str]:
        """Get any sealed trait names this class should extend via union_of."""
        sv = self._get_schemaview()
        parents = []
        for class_name in sv.all_classes():
            other = sv.get_class(class_name)
            union_of = getattr(other, "union_of", None)
            if union_of and cls.name in union_of:
                parents.append(self._to_pascal_case(other.name))
        return parents

    @staticmethod
    def _inject_parent_type(code: str, parent: str) -> str:
        """Inject a parent type into a case class's extends clause."""
        if "extends" in code:
            # Add as a mixin after existing extends
            if "\n\n" in code:
                return code.replace("\n\n", f" with {parent}\n\n", 1)
            # Single-line case class (no companion)
            idx = code.find(")")
            return code[:idx + 1] + f" with {parent}" + code[idx + 1:]
        return code.replace(")", f") extends {parent}", 1)

    def _get_custom_codec_types(self) -> set[str]:
        """Return the set of Scala types used in the schema that need custom circe codecs."""
        sv = self._get_schemaview()
        used = set()
        for slot_name in sv.all_slots():
            slot = sv.get_slot(slot_name)
            if slot and slot.range:
                scala_type = self.map_type(str(slot.range))
                if scala_type in CUSTOM_CODEC_TYPES:
                    used.add(scala_type)
        return used

    def serialize(self, **kwargs) -> str:
        """Generate complete Scala source from the schema."""
        sv = self._get_schemaview()
        schema = sv.schema
        parts: list[str] = []

        # Package declaration
        pkg = self.package_name or schema.name.replace("-", ".").replace("_", ".")
        parts.append(f"package {pkg}\n")

        # Circe imports when codecs enabled
        if self.codecs == "inline":
            parts.append(
                "import io.circe.{Decoder, Encoder}\n"
                "import io.circe.generic.semiauto.{deriveDecoder, deriveEncoder}"
            )
            custom_types = self._get_custom_codec_types()
            if custom_types:
                template = self.jinja_env.get_template("scala_codec_implicits.scala.jinja2")
                parts.append(template.render(types=sorted(custom_types)))

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
            union_parents = self._get_union_parents(cls)
            result = self.generate_case_class(cls)

            # Inject union_of parent types into the extends clause
            for up in union_parents:
                if f"extends {up}" not in result and f"with {up}" not in result:
                    result = self._inject_parent_type(result, up)

            parts.append(result)

        return "\n\n".join(parts) + "\n"

    def serialize_codecs(self, **kwargs) -> str:
        """Generate a separate Codecs.scala file with all circe codecs."""
        sv = self._get_schemaview()
        schema = sv.schema
        pkg = self.package_name or schema.name.replace("-", ".").replace("_", ".")

        # Collect enum info
        enums = []
        for enum_name, enum_def in (schema.enums or {}).items():
            name = self._to_pascal_case(enum_def.name)
            values = []
            for pv in enum_def.permissible_values.values():
                values.append(EnumValue(
                    name=self._to_pascal_case(pv.text),
                    linkml_name=pv.text,
                ))
            enums.append({"name": name, "enum_values": values})

        # Collect case class info
        case_classes = []
        for class_name in sv.all_classes():
            cls = sv.get_class(class_name)
            if not self._is_trait(cls):
                name = self._to_pascal_case(cls.name)
                fields = self._get_fields(cls)
                rules = self._get_rules(cls)
                has_validation = self._has_constraints(fields) or bool(rules)
                case_classes.append({
                    "name": name,
                    "has_validation": has_validation,
                })

        custom_types = sorted(self._get_custom_codec_types())

        template = self.jinja_env.get_template("scala_codecs.scala.jinja2")
        return template.render(
            package=pkg,
            enums=enums,
            case_classes=case_classes,
            custom_types=custom_types,
        )


@click.command(name="gen-scala")
@click.argument("schema", type=click.Path(exists=True))
@click.option("-o", "--output", type=click.Path(), default=None, help="Output file path")
@click.option("--package", "package_name", default=None, help="Scala package name")
@click.option("--codecs", type=click.Choice(["none", "inline", "separate"]), default="none", help="Generate circe JSON codecs")
def cli(schema: str, output: str | None, package_name: str | None, codecs: str):
    """Generate Scala 3 code from a LinkML schema."""
    gen = ScalaGenerator(schema, package_name=package_name, codecs=codecs)
    result = gen.serialize()
    if output:
        out_path = Path(output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(result)
        click.echo(f"Generated {out_path}")
    else:
        click.echo(result)
    if codecs == "separate":
        codecs_result = gen.serialize_codecs()
        if output:
            codecs_path = out_path.parent / "Codecs.scala"
            codecs_path.write_text(codecs_result)
            click.echo(f"Generated {codecs_path}")
        else:
            click.echo(codecs_result)


if __name__ == "__main__":
    cli()
