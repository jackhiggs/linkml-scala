# linkml-scala

[![CI](https://github.com/jackhiggs/linkml-scala/actions/workflows/ci.yml/badge.svg)](https://github.com/jackhiggs/linkml-scala/actions/workflows/ci.yml)

A [LinkML](https://linkml.io/) code generator that produces **Scala 3** case classes, traits, and enums from LinkML schemas. Supports ScalaDoc generation from descriptions and mappings, validation companion objects from slot constraints and rules, sealed trait hierarchies, and interface operations via annotations.

## Installation

```bash
pip install linkml-scala
```

Or from source:

```bash
git clone https://github.com/jackhiggs/linkml-scala.git
cd linkml-scala
pip install -e ".[dev]"
```

## Usage

### CLI

```bash
gen-scala schema.yaml                          # print to stdout
gen-scala schema.yaml -o output/Model.scala    # write to file
gen-scala schema.yaml --package com.example     # custom package name
```

### Python API

```python
from linkml_scala.scalagen import ScalaGenerator

gen = ScalaGenerator("schema.yaml", package_name="com.example.model")
scala_code = gen.serialize()
```

## Mapping Rules

| LinkML Concept | Scala 3 Output |
|---|---|
| `ClassDefinition` (concrete) | `case class Foo(...)` |
| `ClassDefinition` with `mixin: true` | `trait Foo` |
| `ClassDefinition` with `abstract: true` | `trait Foo` |
| `abstract` + `children_are_mutually_disjoint` | `sealed trait Foo` |
| `union_of` | `sealed trait Foo` (members extend it) |
| `is_a` | `extends Parent` |
| `mixins` | `with Trait1 with Trait2` |
| `SlotDefinition` (required) | `val name: Type` |
| `SlotDefinition` (optional) | `val name: Option[Type] = None` |
| `SlotDefinition` (multivalued) | `val name: List[Type] = List.empty` |
| `EnumDefinition` | `enum Foo { case A, B, C }` |
| `TypeDefinition` | Type alias |
| `description` | ScalaDoc `/** ... */` |
| `exact_mappings`, `close_mappings`, etc. | `@see` in ScalaDoc |
| `deprecated` | `@deprecated` annotation |
| `unique_keys` | `@note` in ScalaDoc |
| `tree_root` | Documented in ScalaDoc |
| `slot_usage` (pattern, min/max, cardinality) | Companion object `validate` method |
| `rules` (preconditions/postconditions) | Named rule check methods in companion |

### Type Mapping

| LinkML | Scala |
|---|---|
| `string` | `String` |
| `integer` | `Int` |
| `float` / `double` | `Double` |
| `boolean` | `Boolean` |
| `decimal` | `BigDecimal` |
| `date` | `java.time.LocalDate` |
| `datetime` | `java.time.Instant` |
| `uri` | `java.net.URI` |

## Example

Given a LinkML schema:

```yaml
id: https://example.org/people
name: people
prefixes:
  linkml: https://w3id.org/linkml/
  schema: http://schema.org/
imports:
  - linkml:types

enums:
  Status:
    description: The status of an entity
    permissible_values:
      active:
        description: Entity is currently active
        meaning: schema:ActiveActionStatus
      inactive:

classes:
  NamedThing:
    mixin: true
    description: A generic named entity
    exact_mappings:
      - schema:Thing
    slots:
      - id
      - name

  Person:
    is_a: NamedThing
    description: A person
    close_mappings:
      - schema:Person
    deprecated: Use Individual instead
    slots:
      - age
      - email
    slot_usage:
      email:
        pattern: "^\\S+@\\S+\\.\\S+$"
      age:
        minimum_value: 0
        maximum_value: 200
    rules:
      - preconditions:
          slot_conditions:
            age:
              minimum_value: 18
        postconditions:
          slot_conditions:
            status:
              equals_string: active
        description: Adults must be active

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
  email:
    range: string
```

Generates:

```scala
package people

/**
 * The status of an entity
 */
enum Status {
  /**
   * Entity is currently active
   * @see schema:ActiveActionStatus
   */
  case Active
  case Inactive
}

/**
 * A generic named entity
 *
 * @see Exact mapping: schema:Thing
 */
trait NamedThing {
  def id: String
  def name: String
}

/**
 * A person
 *
 * @see Close mapping: schema:Person
 */
@deprecated
case class Person(
  age: Option[Int] = None,
  email: Option[String] = None,
  id: String,
  name: String
) extends NamedThing

object Person {
  def validate(instance: Person): List[String] = {
    val errors = List.newBuilder[String]
    if (!instance.email.forall(_.matches("^\\S+@\\S+\\.\\S+$")))
      errors += "email must match ^\\S+@\\S+\\.\\S+$"
    if (!instance.age.forall(v => v >= 0 && v <= 200))
      errors += "age must be between 0 and 200"
    errors.result()
  }

  /** Adults must be active */
  def adultsMustBeActive(instance: Person): List[String] = {
    val errors = List.newBuilder[String]
    val preconditionsMet =
      instance.age match {
        case Some(v) => v >= 18
        case None => false
      }
    if (preconditionsMet) {
      instance.status match {
        case Some(v) if !(v == "active") =>
          errors += "Adults must be active: status must == \"active\""
        case None =>
          errors += "Adults must be active: status is required"
        case _ => ()
      }
    }
    errors.result()
  }
}
```

## Sealed Trait Hierarchies

Abstract classes with `children_are_mutually_disjoint: true` generate `sealed trait`:

```yaml
classes:
  LivingThing:
    abstract: true
    children_are_mutually_disjoint: true
  Animal:
    is_a: LivingThing
  Plant:
    is_a: LivingThing
```

```scala
sealed trait LivingThing { ... }
case class Animal(...) extends LivingThing
case class Plant(...) extends LivingThing
```

Classes with `union_of` also generate sealed traits, with each member extending the trait.

## Validation & Rules

When classes have `slot_usage` constraints (pattern, minimum/maximum value, cardinality bounds, equals_string), a companion object with a `validate` method is generated that returns `List[String]` of error messages.

Class `rules` with `preconditions`/`postconditions` referencing `slot_conditions` generate named check methods in the companion object. Supported condition types:

- `minimum_value` / `maximum_value` on numeric slots
- `equals_string` for exact value matching
- Rules without preconditions apply postconditions unconditionally

## Interface Operations

You can define methods on traits using annotations with a JSON-encoded `scala` key:

```yaml
classes:
  Repository:
    mixin: true
    annotations:
      scala:
        is_interface: true
        operations:
          - name: findById
            parameters:
              - name: id
                range: string
            return_type: "Option[Self]"
            is_abstract: true
          - name: count
            return_type: Int
            is_abstract: false
            body: "0"
```

Generates:

```scala
trait Repository {
  def findById(id: String): Option[Self]
  def count(): Int = {
    0
  }
}
```

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

## License

MIT
