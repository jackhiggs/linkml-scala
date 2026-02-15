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


class TestScalaDocGeneration:
    def setup_method(self):
        self.gen = ScalaGenerator(EXAMPLE_SCHEMA)

    def test_class_description_scaladoc(self):
        sv = self.gen._get_schemaview()
        cls = sv.get_class("Person")
        result = self.gen.generate_case_class(cls)
        assert "/**" in result
        assert "A person" in result
        assert "*/" in result

    def test_class_mappings_see(self):
        sv = self.gen._get_schemaview()
        cls = sv.get_class("Person")
        result = self.gen.generate_case_class(cls)
        assert "@see Close mapping: schema:Person" in result

    def test_trait_mappings_see(self):
        sv = self.gen._get_schemaview()
        cls = sv.get_class("NamedThing")
        result = self.gen.generate_trait(cls)
        assert "@see Exact mapping: schema:Thing" in result

    def test_deprecated_annotation(self):
        sv = self.gen._get_schemaview()
        cls = sv.get_class("Person")
        result = self.gen.generate_case_class(cls)
        assert "@deprecated" in result

    def test_no_scaladoc_when_no_description(self):
        sv = self.gen._get_schemaview()
        cls = sv.get_class("Organization")
        doc = self.gen.generate_scaladoc(cls)
        assert doc == ""

    def test_enum_scaladoc(self):
        sv = self.gen._get_schemaview()
        enum_def = sv.get_enum("Status")
        result = self.gen.generate_enum(enum_def)
        assert "The status of an entity" in result

    def test_enum_value_description(self):
        sv = self.gen._get_schemaview()
        enum_def = sv.get_enum("Status")
        result = self.gen.generate_enum(enum_def)
        assert "Entity is currently active" in result

    def test_enum_value_meaning(self):
        sv = self.gen._get_schemaview()
        enum_def = sv.get_enum("Status")
        result = self.gen.generate_enum(enum_def)
        assert "@see schema:ActiveActionStatus" in result

    def test_unique_key_note(self):
        sv = self.gen._get_schemaview()
        cls = sv.get_class("Person")
        result = self.gen.generate_case_class(cls)
        assert "@note Unique key: (name, email)" in result

    def test_tree_root_doc(self):
        sv = self.gen._get_schemaview()
        cls = sv.get_class("LivingThing")
        result = self.gen.generate_trait(cls)
        assert "This is the tree root." in result


class TestSlotConstraints:
    def setup_method(self):
        self.gen = ScalaGenerator(EXAMPLE_SCHEMA)

    def test_slot_usage_pattern(self):
        sv = self.gen._get_schemaview()
        cls = sv.get_class("Person")
        fields = self.gen._get_fields(cls)
        email_field = next(f for f in fields if f.name == "email")
        assert email_field.pattern == "^\\\\S+@\\\\S+\\\\.\\\\S+$"

    def test_slot_usage_min_max(self):
        sv = self.gen._get_schemaview()
        cls = sv.get_class("Person")
        fields = self.gen._get_fields(cls)
        age_field = next(f for f in fields if f.name == "age")
        assert age_field.minimum_value == 0
        assert age_field.maximum_value == 200

    def test_slot_usage_cardinality(self):
        sv = self.gen._get_schemaview()
        cls = sv.get_class("Person")
        fields = self.gen._get_fields(cls)
        scores_field = next(f for f in fields if f.name == "scores")
        assert scores_field.maximum_cardinality == 10

    def test_identifier_flag(self):
        sv = self.gen._get_schemaview()
        slot = sv.get_slot("id")
        cls = sv.get_class("Person")
        field = self.gen._slot_to_field(slot, cls)
        assert field.identifier is True

    def test_slot_usage_required_override(self):
        sv = self.gen._get_schemaview()
        cls = sv.get_class("Person")
        fields = self.gen._get_fields(cls)
        email_field = next(f for f in fields if f.name == "email")
        # email is required via slot_usage, so no Option wrapper
        assert "Option[" not in email_field.scala_type


class TestCompanionObject:
    def setup_method(self):
        self.gen = ScalaGenerator(EXAMPLE_SCHEMA)

    def test_companion_generated_for_constrained_class(self):
        sv = self.gen._get_schemaview()
        cls = sv.get_class("Person")
        result = self.gen.generate_case_class(cls)
        assert "object Person {" in result
        assert "def validate(instance: Person): List[String]" in result

    def test_companion_pattern_validation(self):
        sv = self.gen._get_schemaview()
        cls = sv.get_class("Person")
        result = self.gen.generate_case_class(cls)
        assert 'matches(' in result
        assert "email must match" in result

    def test_companion_range_validation(self):
        sv = self.gen._get_schemaview()
        cls = sv.get_class("Person")
        result = self.gen.generate_case_class(cls)
        assert "age must be between 0 and 200" in result

    def test_companion_cardinality_validation(self):
        sv = self.gen._get_schemaview()
        cls = sv.get_class("Person")
        result = self.gen.generate_case_class(cls)
        assert "scores must have at most 10 elements" in result

    def test_no_companion_for_unconstrained_class(self):
        sv = self.gen._get_schemaview()
        cls = sv.get_class("Organization")
        result = self.gen.generate_case_class(cls)
        assert "object Organization" not in result


class TestSealedTraits:
    def setup_method(self):
        self.gen = ScalaGenerator(EXAMPLE_SCHEMA)

    def test_sealed_trait_disjoint(self):
        sv = self.gen._get_schemaview()
        cls = sv.get_class("LivingThing")
        assert self.gen._is_sealed(cls)
        result = self.gen.generate_trait(cls)
        assert "sealed trait LivingThing" in result

    def test_sealed_trait_union_of(self):
        sv = self.gen._get_schemaview()
        cls = sv.get_class("Shape")
        assert self.gen._is_sealed(cls)
        result = self.gen.generate_trait(cls)
        assert "sealed trait Shape" in result

    def test_non_sealed_trait(self):
        sv = self.gen._get_schemaview()
        cls = sv.get_class("NamedThing")
        assert not self.gen._is_sealed(cls)
        result = self.gen.generate_trait(cls)
        assert "sealed" not in result

    def test_union_member_extends_sealed_trait(self):
        gen = ScalaGenerator(EXAMPLE_SCHEMA)
        result = gen.serialize()
        # Circle and Square should extend Shape
        assert "Circle" in result
        assert "Square" in result


class TestNewConstraintValidations:
    def setup_method(self):
        self.gen = ScalaGenerator(EXAMPLE_SCHEMA)

    def test_exact_cardinality_validation(self):
        sv = self.gen._get_schemaview()
        cls = sv.get_class("Employee")
        result = self.gen.generate_case_class(cls)
        assert "must have exactly 3 elements" in result
        assert ".size != 3" in result

    def test_value_presence_validation(self):
        sv = self.gen._get_schemaview()
        cls = sv.get_class("Employee")
        result = self.gen.generate_case_class(cls)
        assert "must be present" in result
        assert ".isEmpty" in result

    def test_equals_number_validation(self):
        sv = self.gen._get_schemaview()
        cls = sv.get_class("Employee")
        result = self.gen.generate_case_class(cls)
        assert "must equal 50000" in result

    def test_equals_number_field_extraction(self):
        sv = self.gen._get_schemaview()
        cls = sv.get_class("Employee")
        fields = self.gen._get_fields(cls)
        salary_field = next(f for f in fields if f.name == "salary")
        assert salary_field.equals_number == 50000.0

    def test_exact_cardinality_field_extraction(self):
        sv = self.gen._get_schemaview()
        cls = sv.get_class("Employee")
        fields = self.gen._get_fields(cls)
        cert_field = next(f for f in fields if f.name == "certifications")
        assert cert_field.exact_cardinality == 3

    def test_value_presence_field_extraction(self):
        sv = self.gen._get_schemaview()
        cls = sv.get_class("Employee")
        fields = self.gen._get_fields(cls)
        badge_field = next(f for f in fields if f.name == "badgeNumber")
        assert badge_field.value_presence == "PRESENT"
