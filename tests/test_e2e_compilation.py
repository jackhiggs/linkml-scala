"""End-to-end roundtrip tests: generate Scala from LinkML and compile with scalac.

These tests generate Scala 3 source code from LinkML schemas using the
ScalaGenerator, write the output to temporary files, and compile with
scalac. They verify that the generator produces syntactically valid
Scala 3 for each major feature: basic classes, inheritance, enums,
mixins, operations, sealed traits, and companion object validation.

Known generator limitations documented inline:
- The Jinja2 companion template emits unescaped double-quotes inside
  string literals for rule methods that compare against string values.
- The class template emits `with Mixin` without a preceding `extends`
  when there is no is_a parent, which is invalid Scala 3 syntax.
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from linkml_scala.scalagen import ScalaGenerator

# Locate scalac: check PATH first, then coursier install location.
SCALAC_PATH = shutil.which("scalac")
if SCALAC_PATH is None:
    _coursier_bin = Path.home() / "Library" / "Application Support" / "Coursier" / "bin" / "scalac"
    if _coursier_bin.exists():
        SCALAC_PATH = str(_coursier_bin)

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(SCALAC_PATH is None, reason="scalac not available"),
]


def compile_scala(code: str, tmpdir: Path) -> subprocess.CompletedProcess:
    """Write Scala code to a file and compile it with scalac."""
    scala_file = tmpdir / "Generated.scala"
    scala_file.write_text(code)
    return subprocess.run(
        [SCALAC_PATH, str(scala_file)],
        capture_output=True,
        text=True,
        cwd=str(tmpdir),
        timeout=120,
    )


def generate_and_compile(yaml_schema: str, tmpdir: Path) -> tuple[str, subprocess.CompletedProcess]:
    """Write a YAML schema to disk, generate Scala, and compile."""
    schema_file = tmpdir / "schema.yaml"
    schema_file.write_text(yaml_schema)
    gen = ScalaGenerator(str(schema_file))
    code = gen.serialize()
    result = compile_scala(code, tmpdir)
    return code, result


class TestBasicClasses:
    """Simple classes with string/integer/boolean fields, required and optional."""

    SCHEMA = """\
id: https://example.org/basic
name: basic
prefixes:
  linkml: https://w3id.org/linkml/
imports:
  - linkml:types
default_range: string

classes:
  Address:
    slots:
      - street
      - city
      - zip_code

  Item:
    slots:
      - item_name
      - quantity
      - in_stock

  Metric:
    slots:
      - label
      - value

slots:
  street:
    range: string
    required: true
  city:
    range: string
    required: true
  zip_code:
    range: string
  item_name:
    range: string
    required: true
  quantity:
    range: integer
    required: true
  in_stock:
    range: boolean
  label:
    range: string
    required: true
  value:
    range: float
"""

    def test_compiles(self, tmp_path):
        code, result = generate_and_compile(self.SCHEMA, tmp_path)
        assert result.returncode == 0, f"Compilation failed:\n{result.stderr}\n\nGenerated code:\n{code}"

    def test_contains_case_classes(self, tmp_path):
        code, _ = generate_and_compile(self.SCHEMA, tmp_path)
        assert "case class Address(" in code
        assert "case class Item(" in code
        assert "case class Metric(" in code

    def test_field_types(self, tmp_path):
        code, _ = generate_and_compile(self.SCHEMA, tmp_path)
        assert "street: String" in code
        assert "quantity: Int" in code
        assert "inStock: Option[Boolean]" in code
        assert "value: Option[Double]" in code


class TestInheritance:
    """Classes with is_a relationships producing extends."""

    SCHEMA = """\
id: https://example.org/inheritance
name: inheritance
prefixes:
  linkml: https://w3id.org/linkml/
imports:
  - linkml:types
default_range: string

classes:
  Vehicle:
    abstract: true
    slots:
      - make
      - year

  Car:
    is_a: Vehicle
    slots:
      - num_doors

  Truck:
    is_a: Vehicle
    slots:
      - payload_capacity

slots:
  make:
    range: string
    required: true
  year:
    range: integer
    required: true
  num_doors:
    range: integer
  payload_capacity:
    range: float
"""

    def test_compiles(self, tmp_path):
        code, result = generate_and_compile(self.SCHEMA, tmp_path)
        assert result.returncode == 0, f"Compilation failed:\n{result.stderr}\n\nGenerated code:\n{code}"

    def test_trait_and_extends(self, tmp_path):
        code, _ = generate_and_compile(self.SCHEMA, tmp_path)
        assert "trait Vehicle" in code
        assert "extends Vehicle" in code
        assert "case class Car(" in code
        assert "case class Truck(" in code


class TestEnums:
    """Enumerations used as slot ranges."""

    SCHEMA = """\
id: https://example.org/enums
name: enums
prefixes:
  linkml: https://w3id.org/linkml/
imports:
  - linkml:types
default_range: string

enums:
  Priority:
    permissible_values:
      low:
      medium:
      high:
      critical:

  TaskState:
    permissible_values:
      open:
      in_progress:
      closed:

classes:
  Task:
    slots:
      - title
      - priority
      - state

slots:
  title:
    range: string
    required: true
  priority:
    range: Priority
  state:
    range: TaskState
"""

    def test_compiles(self, tmp_path):
        code, result = generate_and_compile(self.SCHEMA, tmp_path)
        assert result.returncode == 0, f"Compilation failed:\n{result.stderr}\n\nGenerated code:\n{code}"

    def test_enum_content(self, tmp_path):
        code, _ = generate_and_compile(self.SCHEMA, tmp_path)
        assert "enum Priority" in code
        assert "case Low" in code
        assert "case Critical" in code
        assert "enum TaskState" in code
        assert "case InProgress" in code


class TestMixins:
    """Classes with mixin traits, using is_a for the first parent to
    produce valid 'extends Parent with Mixin' syntax."""

    SCHEMA = """\
id: https://example.org/mixins
name: mixins
prefixes:
  linkml: https://w3id.org/linkml/
imports:
  - linkml:types
default_range: string

classes:
  Identifiable:
    mixin: true
    slots:
      - identifier

  Timestamped:
    mixin: true
    slots:
      - created_at

  BaseEntity:
    abstract: true
    slots:
      - entity_type

  Record:
    is_a: BaseEntity
    mixins:
      - Identifiable
      - Timestamped
    slots:
      - content

slots:
  identifier:
    range: string
    required: true
  created_at:
    range: string
  entity_type:
    range: string
    required: true
  content:
    range: string
    required: true
"""

    def test_compiles(self, tmp_path):
        code, result = generate_and_compile(self.SCHEMA, tmp_path)
        assert result.returncode == 0, f"Compilation failed:\n{result.stderr}\n\nGenerated code:\n{code}"

    def test_trait_generation(self, tmp_path):
        code, _ = generate_and_compile(self.SCHEMA, tmp_path)
        assert "trait Identifiable" in code
        assert "trait Timestamped" in code
        assert "extends BaseEntity" in code
        assert "with Identifiable" in code
        assert "with Timestamped" in code


class TestMixinsWithoutIsA:
    """Classes with mixins but no is_a parent — first mixin uses extends."""

    SCHEMA = """\
id: https://example.org/mixins_no_isa
name: mixins.no.isa
prefixes:
  linkml: https://w3id.org/linkml/
imports:
  - linkml:types
default_range: string

classes:
  Auditable:
    mixin: true
    slots:
      - created_by

  Taggable:
    mixin: true
    slots:
      - tags

  Document:
    mixins:
      - Auditable
      - Taggable
    slots:
      - title

slots:
  created_by:
    range: string
    required: true
  tags:
    range: string
    multivalued: true
  title:
    range: string
    required: true
"""

    def test_compiles(self, tmp_path):
        code, result = generate_and_compile(self.SCHEMA, tmp_path)
        assert result.returncode == 0, f"Compilation failed:\n{result.stderr}\n\nGenerated code:\n{code}"

    def test_extends_first_mixin(self, tmp_path):
        code, _ = generate_and_compile(self.SCHEMA, tmp_path)
        assert "extends Auditable with Taggable" in code
        assert ") with Auditable" not in code


class TestRulesWithRequiredFields:
    """Rules on required (non-Option) fields compile correctly."""

    SCHEMA = """\
id: https://example.org/rules_required
name: rules.required
prefixes:
  linkml: https://w3id.org/linkml/
imports:
  - linkml:types
default_range: string

classes:
  Account:
    slots:
      - username
      - role
      - level
    rules:
      - preconditions:
          slot_conditions:
            role:
              equals_string: admin
        postconditions:
          slot_conditions:
            level:
              minimum_value: 10
        description: Admins need high level

slots:
  username:
    range: string
    required: true
  role:
    range: string
    required: true
  level:
    range: integer
    required: true
"""

    def test_compiles(self, tmp_path):
        code, result = generate_and_compile(self.SCHEMA, tmp_path)
        assert result.returncode == 0, f"Compilation failed:\n{result.stderr}\n\nGenerated code:\n{code}"

    def test_no_option_pattern_match(self, tmp_path):
        code, _ = generate_and_compile(self.SCHEMA, tmp_path)
        # Required fields should use direct comparison, not Some/None matching
        assert "case Some" not in code
        assert '(instance.role == "admin")' in code


class TestOperationsOnInterfaces:
    """Operations defined via scala annotations on interface classes.

    The annotation value must be a JSON string (not a nested YAML mapping)
    for the current parser to handle it correctly.
    """

    SCHEMA = """\
id: https://example.org/operations
name: operations
prefixes:
  linkml: https://w3id.org/linkml/
imports:
  - linkml:types
default_range: string

classes:
  Searchable:
    mixin: true
    annotations:
      scala:
        tag: scala
        value: '{"is_interface": true, "operations": [{"name": "search", "parameters": [{"name": "query", "range": "string"}], "range": "string", "multivalued": true, "required": true, "body": "List.empty"}, {"name": "count", "parameters": [], "range": "integer", "required": true, "body": "0"}]}'

  BaseDoc:
    abstract: true
    slots:
      - doc_id

  Document:
    is_a: BaseDoc
    mixins:
      - Searchable
    slots:
      - title

slots:
  doc_id:
    range: string
    required: true
  title:
    range: string
    required: true
"""

    def test_compiles(self, tmp_path):
        code, result = generate_and_compile(self.SCHEMA, tmp_path)
        assert result.returncode == 0, f"Compilation failed:\n{result.stderr}\n\nGenerated code:\n{code}"

    def test_operations_in_trait(self, tmp_path):
        code, _ = generate_and_compile(self.SCHEMA, tmp_path)
        assert "def search(query: String): List[String]" in code
        assert "def count(): Int" in code


class TestSealedTraits:
    """children_are_mutually_disjoint and union_of patterns producing sealed traits."""

    SCHEMA = """\
id: https://example.org/sealed
name: sealedtest
prefixes:
  linkml: https://w3id.org/linkml/
imports:
  - linkml:types
default_range: string

classes:
  Geometry:
    abstract: true
    children_are_mutually_disjoint: true

  Point:
    is_a: Geometry
    slots:
      - x
      - y

  Line:
    is_a: Geometry
    slots:
      - length

  Result:
    union_of:
      - SuccessResult
      - ErrorResult

  SuccessResult:
    slots:
      - payload

  ErrorResult:
    slots:
      - message

slots:
  x:
    range: float
    required: true
  y:
    range: float
    required: true
  length:
    range: float
    required: true
  payload:
    range: string
    required: true
  message:
    range: string
    required: true
"""

    def test_compiles(self, tmp_path):
        code, result = generate_and_compile(self.SCHEMA, tmp_path)
        assert result.returncode == 0, f"Compilation failed:\n{result.stderr}\n\nGenerated code:\n{code}"

    def test_sealed_traits(self, tmp_path):
        code, _ = generate_and_compile(self.SCHEMA, tmp_path)
        assert "sealed trait Geometry" in code
        assert "sealed trait Result" in code
        assert "extends Geometry" in code


class TestCompanionObjectValidation:
    """Classes with slot_usage constraints that produce companion objects with validate."""

    SCHEMA = """\
id: https://example.org/validation
name: validation
prefixes:
  linkml: https://w3id.org/linkml/
imports:
  - linkml:types
default_range: string

classes:
  Product:
    slots:
      - sku
      - price
      - tags
    slot_usage:
      price:
        minimum_value: 0
        maximum_value: 99999
      tags:
        minimum_cardinality: 1
        maximum_cardinality: 5

slots:
  sku:
    range: string
    required: true
  price:
    range: integer
    required: true
  tags:
    range: string
    multivalued: true
"""

    def test_compiles(self, tmp_path):
        code, result = generate_and_compile(self.SCHEMA, tmp_path)
        assert result.returncode == 0, f"Compilation failed:\n{result.stderr}\n\nGenerated code:\n{code}"

    def test_companion_object(self, tmp_path):
        code, _ = generate_and_compile(self.SCHEMA, tmp_path)
        assert "object Product {" in code
        assert "def validate(instance: Product): List[String]" in code
        assert "price must be between 0 and 99999" in code
        assert "tags must have at most 5 elements" in code


class TestFullSchemaRoundtrip:
    """Compile the project's own example_schema.yaml end-to-end with no patching."""

    def test_example_schema_compiles(self, tmp_path):
        schema_path = Path(__file__).parent / "input" / "example_schema.yaml"
        gen = ScalaGenerator(str(schema_path))
        code = gen.serialize()
        result = compile_scala(code, tmp_path)
        assert result.returncode == 0, f"Compilation failed:\n{result.stderr}\n\nGenerated code:\n{code}"

    def test_example_schema_with_inline_codecs_compiles(self, tmp_path):
        schema_path = Path(__file__).parent / "input" / "example_schema.yaml"
        gen = ScalaGenerator(str(schema_path), codecs="inline")
        code = gen.serialize()
        cp = _get_circe_classpath()
        if cp is None:
            pytest.skip("coursier not available to fetch circe jars")
        result = compile_scala_with_circe(code, tmp_path)
        assert result.returncode == 0, f"Compilation failed:\n{result.stderr}\n\nGenerated code:\n{code}"

    def test_example_schema_with_separate_codecs_compiles(self, tmp_path):
        schema_path = Path(__file__).parent / "input" / "example_schema.yaml"
        gen = ScalaGenerator(str(schema_path), codecs="separate")
        main_code = gen.serialize()
        codecs_code = gen.serialize_codecs()
        cp = _get_circe_classpath()
        if cp is None:
            pytest.skip("coursier not available to fetch circe jars")
        (tmp_path / "Model.scala").write_text(main_code)
        (tmp_path / "Codecs.scala").write_text(codecs_code)
        result = subprocess.run(
            [SCALAC_PATH, "-classpath", cp, str(tmp_path / "Model.scala"), str(tmp_path / "Codecs.scala")],
            capture_output=True, text=True, cwd=str(tmp_path), timeout=120,
        )
        assert result.returncode == 0, (
            f"Compilation failed:\n{result.stderr}\n\n"
            f"Model.scala:\n{main_code}\n\nCodecs.scala:\n{codecs_code}"
        )


# --- Codec compilation tests (require circe jars) ---

COURSIER_PATH = shutil.which("coursier") or shutil.which("cs")

_CIRCE_CLASSPATH: str | None = None


def _get_circe_classpath() -> str | None:
    """Fetch circe jars via coursier and return classpath string."""
    global _CIRCE_CLASSPATH
    if _CIRCE_CLASSPATH is not None:
        return _CIRCE_CLASSPATH
    if COURSIER_PATH is None:
        return None
    try:
        result = subprocess.run(
            [
                COURSIER_PATH, "fetch", "--classpath",
                "io.circe::circe-core:0.14.7",
                "io.circe::circe-generic:0.14.7",
                "io.circe::circe-parser:0.14.7",
                "io.circe::circe-yaml:0.15.1",
            ],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0:
            # Filter out scala-library jars to avoid version conflicts with scalac's own
            jars = result.stdout.strip().split(":")
            jars = [j for j in jars if "scala-library" not in j and "scala3-library" not in j]
            _CIRCE_CLASSPATH = ":".join(jars)
            return _CIRCE_CLASSPATH
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def compile_scala_with_circe(code: str, tmpdir: Path, filename: str = "Generated.scala") -> subprocess.CompletedProcess:
    """Compile Scala code with circe jars on the classpath."""
    cp = _get_circe_classpath()
    scala_file = tmpdir / filename
    scala_file.write_text(code)
    cmd = [SCALAC_PATH, "-classpath", cp, str(scala_file)]
    return subprocess.run(cmd, capture_output=True, text=True, cwd=str(tmpdir), timeout=120)


def _skip_no_circe():
    return pytest.mark.skipif(
        COURSIER_PATH is None,
        reason="coursier not available to fetch circe jars",
    )


CODEC_SCHEMA = """\
id: https://example.org/codectest
name: codectest
prefixes:
  linkml: https://w3id.org/linkml/
imports:
  - linkml:types
default_range: string

enums:
  Color:
    permissible_values:
      red: {}
      green: {}
      blue: {}

classes:
  Widget:
    slots:
      - id
      - name
      - color
      - tags

slots:
  id:
    range: string
    required: true
  name:
    range: string
    required: true
  color:
    range: Color
  tags:
    range: string
    multivalued: true
"""

CODEC_SCHEMA_WITH_VALIDATION = """\
id: https://example.org/validated
name: validatedtest
prefixes:
  linkml: https://w3id.org/linkml/
imports:
  - linkml:types
default_range: string

classes:
  Measurement:
    slots:
      - label
      - value
    slot_usage:
      value:
        minimum_value: 0
        maximum_value: 1000

slots:
  label:
    range: string
    required: true
  value:
    range: integer
    required: true
"""


@_skip_no_circe()
class TestCodecsInlineCompilation:
    """Verify that --codecs inline output compiles with circe on the classpath."""

    def test_basic_codecs_compile(self, tmp_path):
        schema_file = tmp_path / "schema.yaml"
        schema_file.write_text(CODEC_SCHEMA)
        gen = ScalaGenerator(str(schema_file), codecs="inline")
        code = gen.serialize()
        result = compile_scala_with_circe(code, tmp_path)
        assert result.returncode == 0, f"Compilation failed:\n{result.stderr}\n\nGenerated code:\n{code}"

    def test_codecs_contain_expected_symbols(self, tmp_path):
        schema_file = tmp_path / "schema.yaml"
        schema_file.write_text(CODEC_SCHEMA)
        gen = ScalaGenerator(str(schema_file), codecs="inline")
        code = gen.serialize()
        assert "implicit val decoder: Decoder[Widget]" in code
        assert "implicit val encoder: Encoder[Widget]" in code
        assert "implicit val decoder: Decoder[Color]" in code
        assert "implicit val encoder: Encoder[Color]" in code
        assert "def fromJson" in code
        assert "def toJson" in code
        assert "def fromYaml" in code
        assert "def toYaml" in code

    def test_validated_codecs_compile(self, tmp_path):
        schema_file = tmp_path / "schema.yaml"
        schema_file.write_text(CODEC_SCHEMA_WITH_VALIDATION)
        gen = ScalaGenerator(str(schema_file), codecs="inline")
        code = gen.serialize()
        assert "rawDecoder" in code
        assert "emap" in code
        result = compile_scala_with_circe(code, tmp_path)
        assert result.returncode == 0, f"Compilation failed:\n{result.stderr}\n\nGenerated code:\n{code}"


@_skip_no_circe()
class TestCodecsSeparateCompilation:
    """Verify that --codecs separate output compiles with circe on the classpath."""

    def test_separate_codecs_compile(self, tmp_path):
        schema_file = tmp_path / "schema.yaml"
        schema_file.write_text(CODEC_SCHEMA)
        gen = ScalaGenerator(str(schema_file), codecs="separate")
        main_code = gen.serialize()
        codecs_code = gen.serialize_codecs()

        # Write both files and compile together
        (tmp_path / "Model.scala").write_text(main_code)
        (tmp_path / "Codecs.scala").write_text(codecs_code)
        cp = _get_circe_classpath()
        result = subprocess.run(
            [SCALAC_PATH, "-classpath", cp, str(tmp_path / "Model.scala"), str(tmp_path / "Codecs.scala")],
            capture_output=True, text=True, cwd=str(tmp_path), timeout=120,
        )
        assert result.returncode == 0, (
            f"Compilation failed:\n{result.stderr}\n\n"
            f"Model.scala:\n{main_code}\n\nCodecs.scala:\n{codecs_code}"
        )

    def test_separate_codecs_main_file_clean(self, tmp_path):
        schema_file = tmp_path / "schema.yaml"
        schema_file.write_text(CODEC_SCHEMA)
        gen = ScalaGenerator(str(schema_file), codecs="separate")
        main_code = gen.serialize()
        assert "io.circe" not in main_code
        assert "Decoder" not in main_code

    def test_separate_validated_codecs_compile(self, tmp_path):
        schema_file = tmp_path / "schema.yaml"
        schema_file.write_text(CODEC_SCHEMA_WITH_VALIDATION)
        gen = ScalaGenerator(str(schema_file), codecs="separate")
        main_code = gen.serialize()
        codecs_code = gen.serialize_codecs()
        assert "rawMeasurementDecoder" in codecs_code
        assert "Measurement.validate" in codecs_code

        (tmp_path / "Model.scala").write_text(main_code)
        (tmp_path / "Codecs.scala").write_text(codecs_code)
        cp = _get_circe_classpath()
        result = subprocess.run(
            [SCALAC_PATH, "-classpath", cp, str(tmp_path / "Model.scala"), str(tmp_path / "Codecs.scala")],
            capture_output=True, text=True, cwd=str(tmp_path), timeout=120,
        )
        assert result.returncode == 0, (
            f"Compilation failed:\n{result.stderr}\n\n"
            f"Model.scala:\n{main_code}\n\nCodecs.scala:\n{codecs_code}"
        )


CODEC_SCHEMA_CUSTOM_TYPES = """\
id: https://example.org/customtypes
name: customtypes
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


@_skip_no_circe()
class TestCustomTypeCodecsCompilation:
    """Verify that custom type codecs (URI, LocalDate, Instant) compile."""

    def test_inline_custom_types_compile(self, tmp_path):
        schema_file = tmp_path / "schema.yaml"
        schema_file.write_text(CODEC_SCHEMA_CUSTOM_TYPES)
        gen = ScalaGenerator(str(schema_file), codecs="inline")
        code = gen.serialize()
        assert "object CodecImplicits" in code
        assert "uriDecoder" in code
        assert "localDateDecoder" in code
        assert "instantDecoder" in code
        result = compile_scala_with_circe(code, tmp_path)
        assert result.returncode == 0, f"Compilation failed:\n{result.stderr}\n\nGenerated code:\n{code}"

    def test_separate_custom_types_compile(self, tmp_path):
        schema_file = tmp_path / "schema.yaml"
        schema_file.write_text(CODEC_SCHEMA_CUSTOM_TYPES)
        gen = ScalaGenerator(str(schema_file), codecs="separate")
        main_code = gen.serialize()
        codecs_code = gen.serialize_codecs()
        assert "uriDecoder" in codecs_code
        assert "localDateDecoder" in codecs_code
        assert "instantDecoder" in codecs_code

        (tmp_path / "Model.scala").write_text(main_code)
        (tmp_path / "Codecs.scala").write_text(codecs_code)
        cp = _get_circe_classpath()
        result = subprocess.run(
            [SCALAC_PATH, "-classpath", cp, str(tmp_path / "Model.scala"), str(tmp_path / "Codecs.scala")],
            capture_output=True, text=True, cwd=str(tmp_path), timeout=120,
        )
        assert result.returncode == 0, (
            f"Compilation failed:\n{result.stderr}\n\n"
            f"Model.scala:\n{main_code}\n\nCodecs.scala:\n{codecs_code}"
        )


KITCHEN_SINK_SCHEMA = """\
id: https://example.org/kitchensink
name: kitchensink
prefixes:
  linkml: https://w3id.org/linkml/
imports:
  - linkml:types
default_range: string

enums:
  Priority:
    permissible_values:
      low: {}
      medium: {}
      high: {}

classes:
  Auditable:
    mixin: true
    slots:
      - created_at
      - created_by

  BaseEntity:
    abstract: true
    slots:
      - id
      - name

  Task:
    is_a: BaseEntity
    mixins:
      - Auditable
    slots:
      - priority
      - due_date
      - url
      - score
    slot_usage:
      score:
        minimum_value: 0
        maximum_value: 100
    rules:
      - preconditions:
          slot_conditions:
            score:
              minimum_value: 80
        postconditions:
          slot_conditions:
            name:
              equals_string: excellent
        description: High scorers are excellent

  Standalone:
    mixins:
      - Auditable
    slots:
      - label

slots:
  id:
    range: string
    required: true
    identifier: true
  name:
    range: string
    required: true
  created_at:
    range: datetime
  created_by:
    range: string
  priority:
    range: Priority
  due_date:
    range: date
  url:
    range: uri
  score:
    range: integer
  label:
    range: string
    required: true
"""


@_skip_no_circe()
class TestKitchenSinkCompilation:
    """Combined test: codecs + inheritance + mixins + enums + validation + rules + custom types."""

    def test_inline_compiles(self, tmp_path):
        schema_file = tmp_path / "schema.yaml"
        schema_file.write_text(KITCHEN_SINK_SCHEMA)
        gen = ScalaGenerator(str(schema_file), codecs="inline")
        code = gen.serialize()
        result = compile_scala_with_circe(code, tmp_path)
        assert result.returncode == 0, f"Compilation failed:\n{result.stderr}\n\nGenerated code:\n{code}"

    def test_separate_compiles(self, tmp_path):
        schema_file = tmp_path / "schema.yaml"
        schema_file.write_text(KITCHEN_SINK_SCHEMA)
        gen = ScalaGenerator(str(schema_file), codecs="separate")
        main_code = gen.serialize()
        codecs_code = gen.serialize_codecs()
        (tmp_path / "Model.scala").write_text(main_code)
        (tmp_path / "Codecs.scala").write_text(codecs_code)
        cp = _get_circe_classpath()
        result = subprocess.run(
            [SCALAC_PATH, "-classpath", cp, str(tmp_path / "Model.scala"), str(tmp_path / "Codecs.scala")],
            capture_output=True, text=True, cwd=str(tmp_path), timeout=120,
        )
        assert result.returncode == 0, (
            f"Compilation failed:\n{result.stderr}\n\n"
            f"Model.scala:\n{main_code}\n\nCodecs.scala:\n{codecs_code}"
        )

    def test_standalone_extends_mixin(self, tmp_path):
        """Class with mixins but no is_a should use extends for first mixin."""
        schema_file = tmp_path / "schema.yaml"
        schema_file.write_text(KITCHEN_SINK_SCHEMA)
        gen = ScalaGenerator(str(schema_file))
        code = gen.serialize()
        assert ") with Auditable\n" not in code
