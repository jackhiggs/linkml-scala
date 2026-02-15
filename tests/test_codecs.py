"""Tests for Phase 1 circe codec generation (--codecs inline)."""

import tempfile
from pathlib import Path

from linkml_scala.scalagen import ScalaGenerator

BASIC_SCHEMA = """\
id: https://example.org/basic
name: basic
prefixes:
  linkml: https://w3id.org/linkml/
imports:
  - linkml:types
default_range: string

enums:
  Status:
    description: The status of an entity
    permissible_values:
      active:
        description: Currently active
      inactive: {}
      pending_review: {}

classes:
  Person:
    slots:
      - id
      - name
      - age
      - status

slots:
  id:
    range: string
    required: true
    identifier: true
  name:
    range: string
    required: true
  age:
    range: integer
  status:
    range: Status
"""

SCHEMA_WITH_VALIDATION = """\
id: https://example.org/validated
name: validated
prefixes:
  linkml: https://w3id.org/linkml/
imports:
  - linkml:types
default_range: string

classes:
  Record:
    slots:
      - id
      - score
    slot_usage:
      score:
        minimum_value: 0
        maximum_value: 100

slots:
  id:
    range: string
    required: true
  score:
    range: integer
"""


def _make_gen(schema_text: str, codecs: str = "inline") -> ScalaGenerator:
    tmpdir = tempfile.mkdtemp()
    schema_file = Path(tmpdir) / "schema.yaml"
    schema_file.write_text(schema_text)
    return ScalaGenerator(str(schema_file), codecs=codecs)


class TestCodecsDisabledByDefault:
    def test_no_codecs_without_flag(self):
        gen = _make_gen(BASIC_SCHEMA, codecs="none")
        result = gen.serialize()
        assert "Decoder" not in result
        assert "Encoder" not in result
        assert "deriveDecoder" not in result
        assert "import io.circe" not in result


class TestCirceImports:
    def test_circe_imports_present(self):
        gen = _make_gen(BASIC_SCHEMA, codecs="inline")
        result = gen.serialize()
        assert "import io.circe.{Decoder, Encoder}" in result
        assert "import io.circe.generic.semiauto.{deriveDecoder, deriveEncoder}" in result

    def test_circe_imports_absent_when_none(self):
        gen = _make_gen(BASIC_SCHEMA, codecs="none")
        result = gen.serialize()
        assert "io.circe" not in result


class TestCaseClassCodecs:
    def test_companion_has_codecs(self):
        gen = _make_gen(BASIC_SCHEMA, codecs="inline")
        result = gen.serialize()
        assert "object Person" in result
        assert "implicit val decoder: Decoder[Person] = deriveDecoder[Person]" in result
        assert "implicit val encoder: Encoder[Person] = deriveEncoder[Person]" in result

    def test_no_validate_without_constraints(self):
        """Case class without slot_usage should get codecs but no validate."""
        gen = _make_gen(BASIC_SCHEMA, codecs="inline")
        result = gen.serialize()
        assert "object Person" in result
        assert "def validate" not in result

    def test_codecs_with_validation_uses_emap(self):
        """Case class with slot_usage should get validated decoder via .emap."""
        gen = _make_gen(SCHEMA_WITH_VALIDATION, codecs="inline")
        result = gen.serialize()
        assert "object Record" in result
        # Should use rawDecoder + emap pattern, not plain deriveDecoder
        assert "private val rawDecoder: Decoder[Record] = deriveDecoder[Record]" in result
        assert "rawDecoder.emap" in result
        assert "validate(instance)" in result
        assert 'case Nil    => Right(instance)' in result
        assert 'Left(errors.mkString("; "))' in result
        assert "implicit val encoder: Encoder[Record] = deriveEncoder[Record]" in result
        assert "def validate(instance: Record)" in result

    def test_no_emap_without_constraints(self):
        """Case class without constraints should use plain deriveDecoder."""
        gen = _make_gen(BASIC_SCHEMA, codecs="inline")
        result = gen.serialize()
        assert "implicit val decoder: Decoder[Person] = deriveDecoder[Person]" in result
        # Person companion should not have rawDecoder/emap
        person_obj = result[result.index("object Person"):]
        person_obj = person_obj[:person_obj.index("}") + 1]
        assert "rawDecoder" not in person_obj
        assert "emap" not in person_obj


class TestEnumCodecs:
    def test_enum_companion_object(self):
        gen = _make_gen(BASIC_SCHEMA, codecs="inline")
        result = gen.serialize()
        assert "object Status" in result

    def test_enum_decoder(self):
        gen = _make_gen(BASIC_SCHEMA, codecs="inline")
        result = gen.serialize()
        assert "implicit val decoder: Decoder[Status]" in result
        assert 'case "active" => Right(Status.Active)' in result
        assert 'case "inactive" => Right(Status.Inactive)' in result
        assert 'case "pending_review" => Right(Status.PendingReview)' in result
        assert 'case other => Left(s"Unknown Status: $other")' in result

    def test_enum_encoder(self):
        gen = _make_gen(BASIC_SCHEMA, codecs="inline")
        result = gen.serialize()
        assert "implicit val encoder: Encoder[Status]" in result
        assert 'case Status.Active => "active"' in result
        assert 'case Status.Inactive => "inactive"' in result
        assert 'case Status.PendingReview => "pending_review"' in result

    def test_no_enum_codecs_when_none(self):
        gen = _make_gen(BASIC_SCHEMA, codecs="none")
        result = gen.serialize()
        assert "object Status" not in result


class TestMultipleClasses:
    def test_each_class_gets_codecs(self):
        schema = """\
id: https://example.org/multi
name: multi
prefixes:
  linkml: https://w3id.org/linkml/
imports:
  - linkml:types
default_range: string

classes:
  Foo:
    slots:
      - id
  Bar:
    slots:
      - name

slots:
  id:
    range: string
    required: true
  name:
    range: string
    required: true
"""
        gen = _make_gen(schema, codecs="inline")
        result = gen.serialize()
        assert "implicit val decoder: Decoder[Foo] = deriveDecoder[Foo]" in result
        assert "implicit val encoder: Encoder[Foo] = deriveEncoder[Foo]" in result
        assert "implicit val decoder: Decoder[Bar] = deriveDecoder[Bar]" in result
        assert "implicit val encoder: Encoder[Bar] = deriveEncoder[Bar]" in result
