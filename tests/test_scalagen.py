"""Tests for the Scala generator."""

import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from linkml_scala.scalagen import ScalaGenerator, cli

INPUT_DIR = Path(__file__).parent / "input"
EXAMPLE_SCHEMA = str(INPUT_DIR / "example_schema.yaml")


class TestTypeMapping:
    def setup_method(self):
        self.gen = ScalaGenerator(EXAMPLE_SCHEMA)

    def test_string(self):
        assert self.gen.map_type("string") == "String"

    def test_integer(self):
        assert self.gen.map_type("integer") == "Int"

    def test_float(self):
        assert self.gen.map_type("float") == "Double"

    def test_boolean(self):
        assert self.gen.map_type("boolean") == "Boolean"

    def test_date(self):
        assert self.gen.map_type("date") == "java.time.LocalDate"

    def test_datetime(self):
        assert self.gen.map_type("datetime") == "java.time.Instant"

    def test_uri(self):
        assert self.gen.map_type("uri") == "java.net.URI"

    def test_decimal(self):
        assert self.gen.map_type("decimal") == "BigDecimal"

    def test_unknown_type_passthrough(self):
        assert self.gen.map_type("Person") == "Person"

    def test_none_type(self):
        assert self.gen.map_type(None) == "Any"


class TestCaseClassGeneration:
    def setup_method(self):
        self.gen = ScalaGenerator(EXAMPLE_SCHEMA)

    def test_simple_class(self):
        sv = self.gen._get_schemaview()
        cls = sv.get_class("Organization")
        result = self.gen.generate_case_class(cls)
        assert "case class Organization(" in result
        assert "name: String" in result

    def test_class_with_optional_field(self):
        sv = self.gen._get_schemaview()
        cls = sv.get_class("Organization")
        result = self.gen.generate_case_class(cls)
        assert "Option[java.time.LocalDate]" in result
        assert "= None" in result

    def test_class_with_multivalued(self):
        sv = self.gen._get_schemaview()
        cls = sv.get_class("Person")
        result = self.gen.generate_case_class(cls)
        assert "List[Double]" in result
        assert "List.empty" in result


class TestTraitGeneration:
    def setup_method(self):
        self.gen = ScalaGenerator(EXAMPLE_SCHEMA)

    def test_mixin_generates_trait(self):
        sv = self.gen._get_schemaview()
        cls = sv.get_class("NamedThing")
        assert self.gen._is_trait(cls)
        result = self.gen.generate_trait(cls)
        assert "trait NamedThing" in result

    def test_trait_has_abstract_fields(self):
        sv = self.gen._get_schemaview()
        cls = sv.get_class("NamedThing")
        result = self.gen.generate_trait(cls)
        assert "def id: String" in result
        assert "def name: String" in result


class TestInheritance:
    def setup_method(self):
        self.gen = ScalaGenerator(EXAMPLE_SCHEMA)

    def test_is_a_extends(self):
        sv = self.gen._get_schemaview()
        cls = sv.get_class("Person")
        result = self.gen.generate_case_class(cls)
        assert "extends NamedThing" in result

    def test_mixins_with(self):
        sv = self.gen._get_schemaview()
        cls = sv.get_class("Person")
        result = self.gen.generate_case_class(cls)
        assert "with HasStatus" in result


class TestEnumGeneration:
    def setup_method(self):
        self.gen = ScalaGenerator(EXAMPLE_SCHEMA)

    def test_enum(self):
        sv = self.gen._get_schemaview()
        enum_def = sv.get_enum("Status")
        result = self.gen.generate_enum(enum_def)
        assert "enum Status {" in result
        assert "case Active" in result
        assert "case Inactive" in result
        assert "case Pending" in result


class TestFullSerialization:
    def test_serialize(self):
        gen = ScalaGenerator(EXAMPLE_SCHEMA)
        result = gen.serialize()
        assert "package test.schema" in result
        assert "case class" in result
        assert "trait" in result
        assert "enum Status" in result


class TestCli:
    def test_cli_stdout(self):
        runner = CliRunner()
        result = runner.invoke(cli, [EXAMPLE_SCHEMA])
        assert result.exit_code == 0
        assert "case class" in result.output

    def test_cli_output_file(self, tmp_path):
        out_file = tmp_path / "output.scala"
        runner = CliRunner()
        result = runner.invoke(cli, [EXAMPLE_SCHEMA, "-o", str(out_file)])
        assert result.exit_code == 0
        assert out_file.exists()
        content = out_file.read_text()
        assert "case class" in content

    def test_cli_custom_package(self):
        runner = CliRunner()
        result = runner.invoke(cli, [EXAMPLE_SCHEMA, "--package", "com.example.model"])
        assert result.exit_code == 0
        assert "package com.example.model" in result.output
