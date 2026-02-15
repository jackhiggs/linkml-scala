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
        assert len(rules) == 3

    def test_rule_preconditions(self):
        sv = self.gen._get_schemaview()
        cls = sv.get_class("Person")
        rules = self.gen._get_rules(cls)
        rule = rules[0]
        assert len(rule.preconditions) > 0
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
        assert "Status.Active" in value or '"active"' in value

    def test_no_rules_on_organization(self):
        sv = self.gen._get_schemaview()
        cls = sv.get_class("Organization")
        rules = self.gen._get_rules(cls)
        assert len(rules) == 0


class TestMultipleRules:
    def setup_method(self):
        self.gen = ScalaGenerator(EXAMPLE_SCHEMA)

    def test_three_rules_on_person(self):
        sv = self.gen._get_schemaview()
        cls = sv.get_class("Person")
        rules = self.gen._get_rules(cls)
        assert len(rules) == 3
        assert rules[0].description == "Adults must be active"
        assert rules[1].description == "Inactive must have zero age"
        assert rules[2].description == "Name always required value"

    def test_equals_string_precondition(self):
        sv = self.gen._get_schemaview()
        cls = sv.get_class("Person")
        rules = self.gen._get_rules(cls)
        rule = rules[1]  # Inactive must have zero age
        assert len(rule.preconditions) == 1
        field, op, value = rule.preconditions[0]
        assert field == "status"
        assert op == "=="
        assert "Status.Inactive" in value or '"inactive"' in value

    def test_maximum_value_postcondition(self):
        sv = self.gen._get_schemaview()
        cls = sv.get_class("Person")
        rules = self.gen._get_rules(cls)
        rule = rules[1]  # Inactive must have zero age
        assert len(rule.postconditions) == 1
        field, op, value = rule.postconditions[0]
        assert field == "age"
        assert op == "<="
        assert value == "0"

    def test_rule_without_preconditions(self):
        sv = self.gen._get_schemaview()
        cls = sv.get_class("Person")
        rules = self.gen._get_rules(cls)
        rule = rules[2]  # Name always required value
        assert len(rule.preconditions) == 0
        assert len(rule.postconditions) == 1
        field, op, value = rule.postconditions[0]
        assert field == "name"
        assert op == "=="


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

    def test_all_rule_methods_generated(self):
        sv = self.gen._get_schemaview()
        cls = sv.get_class("Person")
        result = self.gen.generate_case_class(cls)
        assert "adultsMustBeActive" in result
        assert "inactiveMustHaveZeroAge" in result
        assert "nameAlwaysRequiredValue" in result

    def test_rule_method_signature(self):
        sv = self.gen._get_schemaview()
        cls = sv.get_class("Person")
        result = self.gen.generate_case_class(cls)
        assert "def adultsMustBeActive(instance: Person): List[String]" in result
        assert "def inactiveMustHaveZeroAge(instance: Person): List[String]" in result

    def test_rule_with_equals_string_precondition_generates_match(self):
        sv = self.gen._get_schemaview()
        cls = sv.get_class("Person")
        result = self.gen.generate_case_class(cls)
        # The inactive rule should check status == Status.Inactive (enum-aware)
        assert "Status.Inactive" in result

    def test_postcondition_only_rule_no_preconditions_block(self):
        sv = self.gen._get_schemaview()
        cls = sv.get_class("Person")
        result = self.gen.generate_case_class(cls)
        # The "Name always required value" rule has no preconditions
        # It should still generate a method
        assert "nameAlwaysRequiredValue" in result

    def test_companion_contains_all_rule_docs(self):
        sv = self.gen._get_schemaview()
        cls = sv.get_class("Person")
        result = self.gen.generate_case_class(cls)
        assert "/** Adults must be active */" in result
        assert "/** Inactive must have zero age */" in result
        assert "/** Name always required value */" in result


class TestDeactivatedRules:
    def setup_method(self):
        self.gen = ScalaGenerator(EXAMPLE_SCHEMA)

    def test_deactivated_rule_skipped(self):
        sv = self.gen._get_schemaview()
        cls = sv.get_class("Employee")
        rules = self.gen._get_rules(cls)
        names = [r.name for r in rules]
        assert "deactivatedRuleExample" not in names

    def test_active_rules_present(self):
        sv = self.gen._get_schemaview()
        cls = sv.get_class("Employee")
        rules = self.gen._get_rules(cls)
        names = [r.name for r in rules]
        assert "engineeringSalaryRule" in names
        assert "salesSalaryCheck" in names


class TestElseconditions:
    def setup_method(self):
        self.gen = ScalaGenerator(EXAMPLE_SCHEMA)

    def test_elseconditions_extracted(self):
        sv = self.gen._get_schemaview()
        cls = sv.get_class("Employee")
        rules = self.gen._get_rules(cls)
        rule = next(r for r in rules if r.name == "engineeringSalaryRule")
        assert len(rule.elseconditions) > 0
        field, op, value = rule.elseconditions[0]
        assert field == "salary"
        assert op == ">="

    def test_else_branch_in_codegen(self):
        sv = self.gen._get_schemaview()
        cls = sv.get_class("Employee")
        result = self.gen.generate_case_class(cls)
        assert "} else {" in result


class TestBidirectionalRules:
    def setup_method(self):
        self.gen = ScalaGenerator(EXAMPLE_SCHEMA)

    def test_bidirectional_flag(self):
        sv = self.gen._get_schemaview()
        cls = sv.get_class("Employee")
        rules = self.gen._get_rules(cls)
        rule = next(r for r in rules if r.name == "salesSalaryCheck")
        assert rule.bidirectional is True

    def test_reverse_method_generated(self):
        sv = self.gen._get_schemaview()
        cls = sv.get_class("Employee")
        result = self.gen.generate_case_class(cls)
        assert "salesSalaryCheckReverse" in result
        assert "(reverse)" in result


class TestEqualsNumberInRules:
    def setup_method(self):
        self.gen = ScalaGenerator(EXAMPLE_SCHEMA)

    def test_equals_number_extracted(self):
        sv = self.gen._get_schemaview()
        cls = sv.get_class("Employee")
        rules = self.gen._get_rules(cls)
        rule = next(r for r in rules if r.name == "salesSalaryCheck")
        assert len(rule.postconditions) > 0
        field, op, value = rule.postconditions[0]
        assert field == "salary"
        assert op == "=="
        assert "45000" in value

    def test_equals_number_in_codegen(self):
        sv = self.gen._get_schemaview()
        cls = sv.get_class("Employee")
        result = self.gen.generate_case_class(cls)
        assert "45000" in result


class TestOpenWorldRules:
    def setup_method(self):
        self.gen = ScalaGenerator(EXAMPLE_SCHEMA)

    def test_open_world_flag(self):
        sv = self.gen._get_schemaview()
        cls = sv.get_class("Employee")
        rules = self.gen._get_rules(cls)
        rule = next(r for r in rules if r.name == "seniorEligibility")
        assert rule.open_world is True

    def test_open_world_comment_in_codegen(self):
        sv = self.gen._get_schemaview()
        cls = sv.get_class("Employee")
        result = self.gen.generate_case_class(cls)
        assert "// Note: open world assumption" in result
