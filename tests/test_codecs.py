"""Tests for circe codec generation (--codecs inline and --codecs separate)."""

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


class TestYamlHelpers:
    def test_case_class_has_yaml_helpers(self):
        gen = _make_gen(BASIC_SCHEMA, codecs="inline")
        result = gen.serialize()
        person_obj = result[result.index("object Person"):]
        assert "def fromYaml(yaml: String): Either[io.circe.Error, Person]" in person_obj
        assert "io.circe.yaml.parser.parse(yaml).flatMap(_.as[Person])" in person_obj
        assert "def toYaml(instance: Person): String" in person_obj
        assert "io.circe.yaml.Printer().pretty(encoder(instance))" in person_obj

    def test_case_class_has_json_helpers(self):
        gen = _make_gen(BASIC_SCHEMA, codecs="inline")
        result = gen.serialize()
        person_obj = result[result.index("object Person"):]
        assert "def fromJson(json: String): Either[io.circe.Error, Person]" in person_obj
        assert "io.circe.parser.decode[Person](json)" in person_obj
        assert "def toJson(instance: Person): String" in person_obj
        assert "encoder(instance).noSpaces" in person_obj

    def test_validated_class_has_yaml_helpers(self):
        gen = _make_gen(SCHEMA_WITH_VALIDATION, codecs="inline")
        result = gen.serialize()
        assert "def fromYaml(yaml: String): Either[io.circe.Error, Record]" in result
        assert "def toYaml(instance: Record): String" in result

    def test_enum_has_json_helpers(self):
        gen = _make_gen(BASIC_SCHEMA, codecs="inline")
        result = gen.serialize()
        status_obj = result[result.index("object Status"):]
        assert "def fromJson(json: String): Either[io.circe.Error, Status]" in status_obj
        assert "def toJson(instance: Status): String" in status_obj

    def test_no_helpers_when_codecs_none(self):
        gen = _make_gen(BASIC_SCHEMA, codecs="none")
        result = gen.serialize()
        assert "fromJson" not in result
        assert "toJson" not in result
        assert "fromYaml" not in result
        assert "toYaml" not in result


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


class TestSeparateCodecs:
    def test_main_file_has_no_circe(self):
        """With --codecs separate, main file should have no circe imports or codecs."""
        gen = _make_gen(BASIC_SCHEMA, codecs="separate")
        result = gen.serialize()
        assert "io.circe" not in result
        assert "Decoder" not in result
        assert "Encoder" not in result
        assert "deriveDecoder" not in result

    def test_codecs_file_has_package(self):
        gen = _make_gen(BASIC_SCHEMA, codecs="separate")
        codecs = gen.serialize_codecs()
        assert "package basic" in codecs

    def test_codecs_file_has_imports(self):
        gen = _make_gen(BASIC_SCHEMA, codecs="separate")
        codecs = gen.serialize_codecs()
        assert "import io.circe.{Decoder, Encoder}" in codecs
        assert "import io.circe.generic.semiauto.{deriveDecoder, deriveEncoder}" in codecs

    def test_codecs_file_has_object(self):
        gen = _make_gen(BASIC_SCHEMA, codecs="separate")
        codecs = gen.serialize_codecs()
        assert "object Codecs" in codecs

    def test_codecs_file_has_case_class_codecs(self):
        gen = _make_gen(BASIC_SCHEMA, codecs="separate")
        codecs = gen.serialize_codecs()
        assert "personDecoder: Decoder[Person]" in codecs
        assert "personEncoder: Encoder[Person]" in codecs
        assert "deriveDecoder[Person]" in codecs
        assert "deriveEncoder[Person]" in codecs

    def test_codecs_file_has_enum_codecs(self):
        gen = _make_gen(BASIC_SCHEMA, codecs="separate")
        codecs = gen.serialize_codecs()
        assert "statusDecoder: Decoder[Status]" in codecs
        assert "statusEncoder: Encoder[Status]" in codecs
        assert 'case "active" => Right(Status.Active)' in codecs
        assert 'case Status.Active => "active"' in codecs

    def test_codecs_file_has_json_yaml_helpers(self):
        gen = _make_gen(BASIC_SCHEMA, codecs="separate")
        codecs = gen.serialize_codecs()
        assert "personFromJson" in codecs
        assert "personToJson" in codecs
        assert "personFromYaml" in codecs
        assert "personToYaml" in codecs
        assert "statusFromJson" in codecs
        assert "statusToJson" in codecs

    def test_codecs_file_validated_decoder(self):
        gen = _make_gen(SCHEMA_WITH_VALIDATION, codecs="separate")
        codecs = gen.serialize_codecs()
        assert "rawRecordDecoder" in codecs
        assert "Record.validate(instance)" in codecs
        assert "emap" in codecs

    def test_codecs_file_no_validation_no_emap(self):
        gen = _make_gen(BASIC_SCHEMA, codecs="separate")
        codecs = gen.serialize_codecs()
        # Person has no constraints, should use plain deriveDecoder
        assert "rawPersonDecoder" not in codecs
        assert "personDecoder: Decoder[Person] = deriveDecoder[Person]" in codecs


SCHEMA_WITH_CUSTOM_TYPES = """\
id: https://example.org/custom
name: custom
prefixes:
  linkml: https://w3id.org/linkml/
imports:
  - linkml:types
default_range: string

classes:
  Event:
    slots:
      - id
      - start_date
      - created_at
      - homepage

slots:
  id:
    range: string
    required: true
  start_date:
    range: date
  created_at:
    range: datetime
  homepage:
    range: uri
"""

SCHEMA_NO_CUSTOM_TYPES = """\
id: https://example.org/plain
name: plain
prefixes:
  linkml: https://w3id.org/linkml/
imports:
  - linkml:types
default_range: string

classes:
  Item:
    slots:
      - name
      - count

slots:
  name:
    range: string
    required: true
  count:
    range: integer
"""


class TestCustomTypeCodecsInline:
    def test_uri_codec(self):
        gen = _make_gen(SCHEMA_WITH_CUSTOM_TYPES, codecs="inline")
        result = gen.serialize()
        assert "uriDecoder: Decoder[java.net.URI]" in result
        assert "uriEncoder: Encoder[java.net.URI]" in result
        assert "java.net.URI.create" in result

    def test_local_date_codec(self):
        gen = _make_gen(SCHEMA_WITH_CUSTOM_TYPES, codecs="inline")
        result = gen.serialize()
        assert "localDateDecoder: Decoder[java.time.LocalDate]" in result
        assert "localDateEncoder: Encoder[java.time.LocalDate]" in result
        assert "java.time.LocalDate.parse" in result

    def test_instant_codec(self):
        gen = _make_gen(SCHEMA_WITH_CUSTOM_TYPES, codecs="inline")
        result = gen.serialize()
        assert "instantDecoder: Decoder[java.time.Instant]" in result
        assert "instantEncoder: Encoder[java.time.Instant]" in result
        assert "java.time.Instant.parse" in result

    def test_codec_implicits_object(self):
        gen = _make_gen(SCHEMA_WITH_CUSTOM_TYPES, codecs="inline")
        result = gen.serialize()
        assert "object CodecImplicits" in result

    def test_no_custom_codecs_when_not_needed(self):
        gen = _make_gen(SCHEMA_NO_CUSTOM_TYPES, codecs="inline")
        result = gen.serialize()
        assert "CodecImplicits" not in result
        assert "uriDecoder" not in result

    def test_no_custom_codecs_when_codecs_none(self):
        gen = _make_gen(SCHEMA_WITH_CUSTOM_TYPES, codecs="none")
        result = gen.serialize()
        assert "CodecImplicits" not in result


class TestCustomTypeCodecsSeparate:
    def test_custom_types_in_codecs_object(self):
        gen = _make_gen(SCHEMA_WITH_CUSTOM_TYPES, codecs="separate")
        codecs = gen.serialize_codecs()
        assert "uriDecoder: Decoder[java.net.URI]" in codecs
        assert "localDateDecoder: Decoder[java.time.LocalDate]" in codecs
        assert "instantDecoder: Decoder[java.time.Instant]" in codecs

    def test_no_custom_types_when_not_needed(self):
        gen = _make_gen(SCHEMA_NO_CUSTOM_TYPES, codecs="separate")
        codecs = gen.serialize_codecs()
        assert "uriDecoder" not in codecs
        assert "localDateDecoder" not in codecs
        assert "instantDecoder" not in codecs
