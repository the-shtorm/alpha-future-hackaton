# Кодстайл backend v2

Java использует 4 пробела и google-java-format AOSP через Spotless.
Назначение новых компонентов описано в JavaDoc, публичный контракт — в Swagger
и [документации API](backend-api.md). Общие отступы задает .editorconfig.

```sh
mvn -f backend/pom.xml spotless:apply
mvn -f backend/pom.xml spotless:check
mvn -f backend/pom.xml verify javadoc:javadoc
```

JavaDoc собирается с doclint=all и failOnWarnings=true. Результат:
backend/target/site/apidocs/index.html. Исходники и документация используют UTF-8 и LF.
YAML/JSON форматируются Prettier с настройками .prettierrc.json; примененные SQL-миграции
форматированием не переписываются, чтобы не менять контрольные суммы Flyway.
