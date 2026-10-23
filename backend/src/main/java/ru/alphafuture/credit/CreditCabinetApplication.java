package ru.alphafuture.credit;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/** HTTP backend кредитного кабинета по Data Policy 2.0. */
@io.swagger.v3.oas.annotations.OpenAPIDefinition(
        info =
                @io.swagger.v3.oas.annotations.info.Info(
                        title = "Credit Cabinet Backend",
                        version = "2.0"),
        security = @io.swagger.v3.oas.annotations.security.SecurityRequirement(name = "bearerAuth"))
@io.swagger.v3.oas.annotations.security.SecurityScheme(
        name = "bearerAuth",
        type = io.swagger.v3.oas.annotations.enums.SecuritySchemeType.HTTP,
        scheme = "bearer")
@SpringBootApplication(
        exclude =
                org.springframework.boot.autoconfigure.security.servlet
                        .UserDetailsServiceAutoConfiguration.class)
public class CreditCabinetApplication {
    /** Создает приложение Spring Boot. */
    public CreditCabinetApplication() {}

    /**
     * Запускает сервер и миграции БД.
     *
     * @param args параметры запуска
     */
    public static void main(String[] args) {
        SpringApplication.run(CreditCabinetApplication.class, args);
    }
}
