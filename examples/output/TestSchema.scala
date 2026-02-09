package test.schema


type Identifier = String

enum Status {
  case Active
  case Inactive
  case Pending
}

enum Color {
  case Red
  case Green
  case Blue
}

trait NamedThing {
  def id: String
  def name: String
}

trait HasStatus {
  def status: Option[Status]
}

case class Person(
  age: Option[Int] = None,
  email: Option[String] = None,
  scores: List[Double] = List.empty,
  status: Option[Status] = None,
  id: String,
  name: String
) extends NamedThing with HasStatus

case class Organization(
  name: String,
  foundedDate: Option[java.time.LocalDate] = None
)
