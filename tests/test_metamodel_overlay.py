"""Tests for metamodel overlay / operations support."""

from pathlib import Path

import pytest

from linkml_scala.scala_metamodel import (
    OperationDefinition,
    ParameterDefinition,
    ScalaClassAnnotation,
)
from linkml_scala.scalagen import ScalaGenerator

INPUT_DIR = Path(__file__).parent / "input"

SCHEMA_WITH_OPS_YAML = """\
id: https://example.org/ops-test
name: ops_test
prefixes:
  linkml: https://w3id.org/linkml/

imports:
  - linkml:types

default_range: string

classes:
  Repository:
    mixin: true
    slots:
      - name

  Entity:
    slots:
      - id
      - name

slots:
  id:
    range: string
    required: true
  name:
    range: string
    required: true
"""

# We inject annotations programmatically since LinkML's Annotation class
# doesn't support nested dicts in YAML directly.


class TestScalaClassAnnotation:
    def test_from_annotation_empty(self):
        ann = ScalaClassAnnotation.from_annotation({})
        assert ann.operations == []
        assert ann.is_interface is False

    def test_from_annotation_with_ops(self):
        data = {
            "is_interface": True,
            "operations": [
                {
                    "name": "findById",
                    "parameters": [{"name": "id", "range": "string"}],
                    "return_type": "Option[Self]",
                    "is_abstract": True,
                },
            ],
        }
        ann = ScalaClassAnnotation.from_annotation(data)
        assert ann.is_interface is True
        assert len(ann.operations) == 1
        assert ann.operations[0].name == "findById"
        assert len(ann.operations[0].parameters) == 1

    def test_from_non_dict(self):
        ann = ScalaClassAnnotation.from_annotation("not a dict")
        assert ann.operations == []


class TestOperationsGeneration:
    def setup_method(self):
        import json
        import tempfile
        self._tmpdir = tempfile.mkdtemp()
        self._schema_file = Path(self._tmpdir) / "schema.yaml"
        self._schema_file.write_text(SCHEMA_WITH_OPS_YAML)
        self.gen = ScalaGenerator(str(self._schema_file))
        # Inject scala annotation programmatically
        sv = self.gen._get_schemaview()
        cls = sv.get_class("Repository")
        from linkml_runtime.linkml_model.meta import Annotation
        scala_data = {
            "is_interface": True,
            "operations": [
                {
                    "name": "findById",
                    "parameters": [{"name": "id", "range": "string"}],
                    "return_type": "Option[Self]",
                    "is_abstract": True,
                },
                {
                    "name": "count",
                    "return_type": "Int",
                    "is_abstract": False,
                    "body": "0",
                },
            ],
        }
        ann = Annotation(tag="scala", value=json.dumps(scala_data))
        cls.annotations["scala"] = ann

    def test_trait_with_operations(self):
        sv = self.gen._get_schemaview()
        cls = sv.get_class("Repository")
        ops = self.gen.get_operations(cls)
        assert len(ops) == 2
        assert ops[0].name == "findById"
        assert ops[0].return_type == "Option[Self]"

    def test_trait_renders_operations(self):
        sv = self.gen._get_schemaview()
        cls = sv.get_class("Repository")
        result = self.gen.generate_trait(cls)
        assert "trait Repository" in result
        assert "def findById(id: String): Option[Self]" in result
        assert "def count(): Int" in result

    def test_operation_with_body(self):
        sv = self.gen._get_schemaview()
        cls = sv.get_class("Repository")
        result = self.gen.generate_trait(cls)
        assert "0" in result

    def test_is_interface_annotation(self):
        sv = self.gen._get_schemaview()
        cls = sv.get_class("Repository")
        assert self.gen._is_trait(cls)
