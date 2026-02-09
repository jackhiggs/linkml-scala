"""Tests for rules and validation generation."""

from pathlib import Path

import pytest

from linkml_scala.scalagen import ScalaGenerator

INPUT_DIR = Path(__file__).parent / "input"
EXAMPLE_SCHEMA = str(INPUT_DIR / "example_schema.yaml")


class TestRuleExtraction:
    def setup_method(self):
        self.gen = ScalaGenerator(EXAMPLE_SCHEMA)

    def test_rules_extracted(self):
        sv = self.gen._get_schemaview()
        cls = sv.get_class("Person")
        rules = self.gen._get_rules(cls)
        assert len(rules) == 1
        assert rules[0].description == "Adults must be active"

    def test_rule_preconditions(self):
        sv = self.gen._get_schemaview()
        cls = sv.get_class("Person")
        rules = self.gen._get_rules(cls)
        rule = rules[0]
        assert len(rule.preconditions) > 0
        # age >= 18
        field, op, value = rule.preconditions[0]
        assert field == "age"
        assert op == ">="
        assert value == "18"

    def test_rule_postconditions(self):
        sv = self.gen._get_schemaview()
        cls = sv.get_class("Person")
        rules = self.gen._get_rules(cls)
        rule = rules[0]
        assert len(rule.postconditions) > 0
        field, op, value = rule.postconditions[0]
        assert field == "status"
        assert op == "=="
        assert '"active"' in value

    def test_no_rules_on_organization(self):
        sv = self.gen._get_schemaview()
        cls = sv.get_class("Organization")
        rules = self.gen._get_rules(cls)
        assert len(rules) == 0


class TestRuleCodeGeneration:
    def setup_method(self):
        self.gen = ScalaGenerator(EXAMPLE_SCHEMA)

    def test_rule_method_generated(self):
        sv = self.gen._get_schemaview()
        cls = sv.get_class("Person")
        result = self.gen.generate_case_class(cls)
        assert "adultsMustBeActive" in result

    def test_rule_method_checks_precondition(self):
        sv = self.gen._get_schemaview()
        cls = sv.get_class("Person")
        result = self.gen.generate_case_class(cls)
        assert "preconditionsMet" in result

    def test_rule_method_has_description_doc(self):
        sv = self.gen._get_schemaview()
        cls = sv.get_class("Person")
        result = self.gen.generate_case_class(cls)
        assert "Adults must be active" in result
