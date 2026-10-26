package ru.alphafuture.credit;

import javax.sql.DataSource;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.assertj.core.api.Assertions.assertThat;

@Testcontainers
@DirtiesContext
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE,
    useMainMethod = SpringBootTest.UseMainMethod.ALWAYS,
    properties = "spring.profiles.active=")
class CloudBootstrapTest {
    @Container
    static final PostgreSQLContainer<?> POSTGRES = new PostgreSQLContainer<>("postgres:17-bookworm")
        .withInitScript("db/bootstrap_roles.sql");

    @DynamicPropertySource
    static void configureExternalDatabase(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", POSTGRES::getJdbcUrl);
        registry.add("spring.datasource.username", () -> "credit_app");
        registry.add("spring.datasource.password", () -> "test-app");
        registry.add("spring.flyway.url", POSTGRES::getJdbcUrl);
        registry.add("spring.flyway.user", () -> "credit_migrator");
        registry.add("spring.flyway.password", () -> "test-migrator");
    }

    @Autowired
    DataSource dataSource;

    @Test
    void startsWithExternalDatabaseAndSeparateRuntimeAndMigrationAccounts() throws Exception {
        try (var connection = dataSource.getConnection(); var statement = connection.createStatement()) {
            try (var result = statement.executeQuery("SELECT current_user")) {
                assertThat(result.next()).isTrue();
                assertThat(result.getString(1)).isEqualTo("credit_app");
            }
            try (var result = statement.executeQuery("SELECT count(*) FROM credit.credit_product WHERE is_synthetic")) {
                assertThat(result.next()).isTrue();
                assertThat(result.getInt(1)).isZero();
            }
            try (var result = statement.executeQuery("""
                SELECT tableowner FROM pg_tables
                WHERE schemaname = 'credit' AND tablename = 'flyway_schema_history'
                """)) {
                assertThat(result.next()).isTrue();
                assertThat(result.getString(1)).isEqualTo("credit_migrator");
            }
        }
    }
}
