# Loaders & Dumpers for linkml-scala

## Summary

Add JSON and YAML serialisation/deserialisation (loaders/dumpers) to generated
Scala 3 code. The recommended approach uses **circe** with semi-automatic
derivation, generating codec definitions alongside the existing case classes and
companion objects.

## Design Decisions

### Library Choice: circe (semi-automatic)

| Option | Pros | Cons |
|--------|------|------|
| circe auto | Zero boilerplate | Slow compile, no customisation |
| **circe semi-auto** | Fast compile, customisable, validation integration | Requires `derives` or explicit codec |
| play-json | Familiar to Play users | Less Scala 3 idiomatic |
| jsoniter-scala | Fastest runtime | Complex macros, less readable |
| upickle | Simple | Weaker ecosystem |

**Decision**: circe semi-automatic. It provides the best balance of compile
speed, customisation (needed for validation integration), and Scala 3 idiom
(`derives`). circe-yaml adds YAML support with no additional codec work.

### Codec Placement: Inline in Companion Objects

Generated codecs live in the companion object alongside `validate`:

```scala
import io.circe.{Decoder, Encoder}
import io.circe.generic.semiauto.{deriveDecoder, deriveEncoder}

case class Person(
  id: String,
  name: String,
  age: Option[Int] = None
)

object Person {
  implicit val decoder: Decoder[Person] = deriveDecoder[Person]
  implicit val encoder: Encoder[Person] = deriveEncoder[Person]

  def validate(instance: Person): List[String] = { ... }
}
```

### Validated Decoder

When a class has `slot_usage` constraints, the decoder chains validation via
`.emap`:

```scala
object Person {
  private val rawDecoder: Decoder[Person] = deriveDecoder[Person]

  implicit val decoder: Decoder[Person] = rawDecoder.emap { p =>
    validate(p) match {
      case Nil    => Right(p)
      case errors => Left(errors.mkString("; "))
    }
  }

  implicit val encoder: Encoder[Person] = deriveEncoder[Person]

  def validate(instance: Person): List[String] = { ... }
}
```

### Enum Codecs

Scala 3 enums get custom string-based codecs to match LinkML permissible value
names:

```scala
enum Status {
  case Active, Inactive
}

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

This preserves the snake_case LinkML names in JSON while using PascalCase in
Scala.

### Type Mapping for Codecs

| LinkML Type | Scala Type | circe Codec |
|-------------|-----------|-------------|
| `string` | `String` | Built-in |
| `integer` | `Int` | Built-in |
| `float`/`double` | `Double` | Built-in |
| `boolean` | `Boolean` | Built-in |
| `decimal` | `BigDecimal` | Built-in |
| `date` | `java.time.LocalDate` | circe-java8 or custom |
| `datetime` | `java.time.Instant` | circe-java8 or custom |
| `uri` | `java.net.URI` | Custom (string-based) |

Custom codecs for `URI`, `LocalDate`, and `Instant`:

```scala
object CodecImplicits {
  implicit val uriDecoder: Decoder[java.net.URI] =
    Decoder.decodeString.map(java.net.URI.create)
  implicit val uriEncoder: Encoder[java.net.URI] =
    Encoder.encodeString.contramap(_.toString)
  // Similar for LocalDate, Instant
}
```

### YAML Support

circe-yaml parses YAML into circe's `Json` AST, so the same decoders work for
both JSON and YAML:

```scala
import io.circe.yaml.parser

// Load from YAML
val person: Either[Error, Person] = parser.parse(yamlString).flatMap(_.as[Person])

// Dump to YAML (via JSON AST)
import io.circe.yaml.syntax._
val yaml: String = person.asJson.asYaml.spaces2
```

### JSON-LD Considerations

For W3C-aligned use cases, JSON-LD context references can be injected via a
wrapper:

```scala
case class JsonLdWrapper[T: Encoder](
  `@context`: String,
  `@type`: String,
  value: T
)
```

This is out of scope for the initial implementation but the codec architecture
supports it.

## CLI Flag

Add a `--codecs` flag to `gen-scala`:

| Value | Behaviour |
|-------|-----------|
| `none` (default) | Current behaviour, no codecs |
| `inline` | Codecs in companion objects |
| `separate` | Codecs in a separate `Codecs.scala` file |

## Generated Imports

When codecs are enabled, add to the top of the generated file:

```scala
import io.circe.{Decoder, Encoder}
import io.circe.generic.semiauto.{deriveDecoder, deriveEncoder}
```

## Implementation Sequence

1. **Phase 1**: Basic codecs for case classes and enums (`--codecs inline`)
2. **Phase 2**: Validated decoders (chain `.emap` when `validate` exists)
3. **Phase 3**: YAML loader/dumper helpers
4. **Phase 4**: `--codecs separate` option
5. **Phase 5**: Custom type codecs (URI, date, datetime)

## Dependencies

Add to generated `build.sbt` or document as requirements:

```scala
libraryDependencies ++= Seq(
  "io.circe" %% "circe-core"    % "0.14.7",
  "io.circe" %% "circe-generic" % "0.14.7",
  "io.circe" %% "circe-parser"  % "0.14.7",
  "io.circe" %% "circe-yaml"    % "0.15.1",  // YAML support
)
```
