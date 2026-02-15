# linkml-scala

[![CI](https://github.com/jackhiggs/linkml-scala/actions/workflows/ci.yml/badge.svg)](https://github.com/jackhiggs/linkml-scala/actions/workflows/ci.yml)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

A [LinkML](https://linkml.io/) code generator that produces idiomatic **Scala 3** from LinkML schemas:
case classes, traits, enums, sealed hierarchies, companion-object validation,
and optional [circe](https://circe.github.io/circe/) JSON/YAML codecs.

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

## Quick Start

### CLI

```bash
gen-scala schema.yaml                          # print to stdout
gen-scala schema.yaml -o output/Model.scala    # write to file
gen-scala schema.yaml --package com.example     # custom package name
gen-scala schema.yaml --codecs inline           # circe codecs in companion objects
gen-scala schema.yaml --codecs separate -o out/Model.scala  # codecs in separate file
```

### Python API

```python
from linkml_scala.scalagen import ScalaGenerator

gen = ScalaGenerator("schema.yaml", package_name="com.example.model")
scala_code = gen.serialize()

# With inline codecs
gen = ScalaGenerator("schema.yaml", codecs="inline")
scala_code = gen.serialize()

# Separate codecs file
gen = ScalaGenerator("schema.yaml", codecs="separate")
model_code = gen.serialize()
codecs_code = gen.serialize_codecs()
```

## Mapping Rules

| LinkML Concept | Scala 3 Output |
|---|---|
| `ClassDefinition` (concrete) | `case class Foo(...)` |
| `ClassDefinition` with `mixin: true` | `trait Foo` |
| `ClassDefinition` with `abstract: true` | `trait Foo` |
| `abstract` + `children_are_mutually_disjoint` | `sealed trait Foo` |
| `union_of` | `sealed trait` (members extend it) |
| `is_a` | `extends Parent` |
| `mixins` | `extends Mixin1 with Mixin2` |
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
| `slot_usage` constraints | Companion `validate` method |
| `rules` (preconditions/postconditions) | Named rule-check methods |

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
| `uri` / `uriorcurie` | `java.net.URI` |

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
      inactive: {}

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
    slots:
      - age
      - status
    slot_usage:
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
  status:
    range: Status
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
case class Person(
  age: Option[Int] = None,
  id: String,
  name: String,
  status: Option[Status] = None
) extends NamedThing

object Person {
  def validate(instance: Person): List[String] = {
    val errors = List.newBuilder[String]
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
        case Some(v) if !(v == Status.Active) =>
          errors += "Adults must be active: status must == active"
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

When classes have `slot_usage` constraints (pattern, minimum/maximum value, cardinality bounds,
equals_string), a companion object with a `validate` method is generated that returns
`List[String]` of error messages.

Class `rules` with `preconditions`/`postconditions` referencing `slot_conditions` generate
named check methods in the companion object. Supported condition types:

- `minimum_value` / `maximum_value` on numeric slots
- `equals_string` for exact value matching (enum-aware: generates `Status.Active` for enum fields)
- `equals_number` for numeric equality
- Bidirectional rules (generates forward and reverse check methods)
- Rules without preconditions apply postconditions unconditionally

## Interface Operations

Traits can define abstract and concrete methods via annotations with a JSON-encoded `scala` key.
Return types follow LinkML slot conventions: `range` specifies the type, `multivalued` wraps
in `List[T]`, and `required: false` wraps in `Option[T]`:

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
            range: Entity
            required: false
            is_abstract: true
          - name: findAll
            range: Entity
            multivalued: true
            is_abstract: true
          - name: count
            range: integer
            is_abstract: false
            body: "0"
```

```scala
trait Repository {
  def findById(id: String): Option[Entity]
  def findAll(): List[Entity]
  def count(): Int = {
    0
  }
}
```

## JSON & YAML Codecs (circe)

The `--codecs` flag generates [circe](https://circe.github.io/circe/) encoder/decoder
instances and JSON/YAML helpers. Two modes are available:

| Mode | Description |
|------|-------------|
| `--codecs inline` | Codecs in companion objects alongside case classes |
| `--codecs separate` | Codecs in a standalone `Codecs.scala`; model file stays circe-free |

### Inline codecs

```bash
gen-scala schema.yaml --codecs inline
```

Case classes get `deriveEncoder`/`deriveDecoder` (semi-automatic derivation) plus
`fromJson`/`toJson`/`fromYaml`/`toYaml` helpers:

```scala
object Person {
  implicit val decoder: Decoder[Person] = deriveDecoder[Person]
  implicit val encoder: Encoder[Person] = deriveEncoder[Person]

  def fromJson(json: String): Either[io.circe.Error, Person] =
    io.circe.parser.decode[Person](json)
  def toJson(instance: Person): String =
    encoder(instance).noSpaces
  def fromYaml(yaml: String): Either[io.circe.Error, Person] =
    io.circe.yaml.parser.parse(yaml).flatMap(_.as[Person])
  def toYaml(instance: Person): String =
    io.circe.yaml.Printer().pretty(encoder(instance))
}
```

Enums use string-based codecs preserving the original LinkML permissible value names:

```scala
object Status {
  implicit val decoder: Decoder[Status] =
    Decoder.decodeString.emap {
      case "active"   => Right(Status.Active)
      case "inactive" => Right(Status.Inactive)
      case other      => Left(s"Unknown Status: $other")
    }

  implicit val encoder: Encoder[Status] =
    Encoder.encodeString.contramap {
      case Status.Active   => "active"
      case Status.Inactive => "inactive"
    }
}
```

### Validated decoders

When a class has `slot_usage` constraints, the decoder chains validation via `.emap`,
rejecting invalid JSON/YAML at decode time:

```scala
object Record {
  private val rawDecoder: Decoder[Record] = deriveDecoder[Record]
  implicit val decoder: Decoder[Record] = rawDecoder.emap { instance =>
    validate(instance) match {
      case Nil    => Right(instance)
      case errors => Left(errors.mkString("; "))
    }
  }
  implicit val encoder: Encoder[Record] = deriveEncoder[Record]

  def validate(instance: Record): List[String] = { ... }
}
```

### Custom type codecs

When a schema uses `date`, `datetime`, or `uri` ranges, the generator emits string-based
circe codecs for `java.time.LocalDate`, `java.time.Instant`, and `java.net.URI` (types
that circe doesn't handle out of the box). These are placed in a `CodecImplicits` object
(inline mode) or directly in the `Codecs` object (separate mode).

### Separate codecs

```bash
gen-scala schema.yaml -o output/Model.scala --codecs separate
# Generates: output/Model.scala + output/Codecs.scala
```

The main file contains only case classes, traits, and enums with no circe dependency.
All codecs live in a single `Codecs` object in `Codecs.scala`:

```scala
object Codecs {
  implicit val personDecoder: Decoder[Person] = deriveDecoder[Person]
  implicit val personEncoder: Encoder[Person] = deriveEncoder[Person]

  def personFromJson(json: String): Either[io.circe.Error, Person] = ...
  def personToJson(instance: Person): String = ...
  def personFromYaml(yaml: String): Either[io.circe.Error, Person] = ...
  def personToYaml(instance: Person): String = ...
}
```

### Required dependencies

Add these to your `build.sbt` when using `--codecs`:

```scala
libraryDependencies ++= Seq(
  "io.circe" %% "circe-core"    % "0.14.7",
  "io.circe" %% "circe-generic" % "0.14.7",
  "io.circe" %% "circe-parser"  % "0.14.7",
  "io.circe" %% "circe-yaml"    % "0.15.1",  // for YAML support
)
```

## Development

```bash
git clone https://github.com/jackhiggs/linkml-scala.git
cd linkml-scala
pip install -e ".[dev]"
pytest tests/ -v
```

End-to-end compilation tests (require `scalac` on PATH) are marked with `@pytest.mark.e2e`.
Codec compilation tests additionally require [coursier](https://get-coursier.io/) to fetch
circe jars.

## License

MIT
