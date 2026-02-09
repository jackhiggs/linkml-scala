# linkml-scala

A [LinkML](https://linkml.io/) code generator that produces **Scala 3** case classes, traits, and enums from LinkML schemas. Includes metamodel extensions for defining **interface operations** (methods on traits).

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
| `is_a` | `extends Parent` |
| `mixins` | `with Trait1 with Trait2` |
| `SlotDefinition` (required) | `val name: Type` |
| `SlotDefinition` (optional) | `val name: Option[Type] = None` |
| `SlotDefinition` (multivalued) | `val name: List[Type] = List.empty` |
| `EnumDefinition` | `enum Foo { case A, B, C }` |
| `TypeDefinition` | Type alias |

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
imports:
  - linkml:types

enums:
  Status:
    permissible_values:
      active:
      inactive:

classes:
  NamedThing:
    mixin: true
    slots:
      - id
      - name

  Person:
    is_a: NamedThing
    slots:
      - age
      - email

slots:
  id:
    range: string
    required: true
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

enum Status {
  case Active
  case Inactive
}

trait NamedThing {
  def id: String
  def name: String
}

case class Person(
  age: Option[Int] = None,
  email: Option[String] = None,
  id: String,
  name: String
) extends NamedThing
```

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
