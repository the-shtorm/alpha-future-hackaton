package ru.alphafuture.credit;

import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import java.nio.charset.StandardCharsets;
import java.sql.Connection;
import java.sql.DriverManager;

import static org.assertj.core.api.Assertions.assertThat;

@Testcontainers
class DatabaseIntegrityTest {
    @Container
    static final PostgreSQLContainer<?> POSTGRES = new PostgreSQLContainer<>("postgres:17-bookworm");

    @BeforeAll
    static void migrate() throws Exception {
        try (var connection = connect(); var statement = connection.createStatement()) {
            statement.execute("CREATE ROLE credit_app NOLOGIN");
        }
        Flyway.configure()
            .dataSource(POSTGRES.getJdbcUrl(), POSTGRES.getUsername(), POSTGRES.getPassword())
            .schemas("credit")
            .defaultSchema("credit")
            .locations("classpath:db/migration", "classpath:db/demo")
            .load().migrate();
    }

    @Test
    void protectsDossierAndExecutesTheDemoLifecycle() throws Exception {
        try (var stream = getClass().getResourceAsStream("/db/database_invariants.sql")) {
            assertThat(stream).isNotNull();
            var sql = new String(stream.readAllBytes(), StandardCharsets.UTF_8);
            try (var connection = connect(); var statement = connection.createStatement()) {
                statement.execute(sql);
            }
        }
        try (var connection = connect(); var statement = connection.createStatement()) {
            try (var result = statement.executeQuery("SELECT count(*) FROM credit.credit_product WHERE is_synthetic")) {
                assertThat(result.next()).isTrue();
                assertThat(result.getInt(1)).isEqualTo(15);
            }
            try (var result = statement.executeQuery("SELECT count(*) FROM credit.loan_application")) {
                assertThat(result.next()).isTrue();
                assertThat(result.getInt(1)).isZero(); // Invariant fixtures are rolled back.
            }
        }
    }

    @Test
    void separatesRuntimeAndMigrationPrivileges() throws Exception {
        try (var connection = connect(); var statement = connection.createStatement()) {
            try (var result = statement.executeQuery("""
                SELECT has_table_privilege('credit_app', 'credit.loan_application', 'INSERT'),
                       has_table_privilege('credit_app', 'credit.application_status_history', 'INSERT'),
                       has_table_privilege('credit_app', 'credit.credit_product_version', 'UPDATE'),
                       has_table_privilege('credit_app', 'credit.flyway_schema_history', 'SELECT'),
                       has_schema_privilege('credit_app', 'credit', 'CREATE')
                """)) {
                assertThat(result.next()).isTrue();
                assertThat(result.getBoolean(1)).isTrue();
                for (int column = 2; column <= 5; column++) {
                    assertThat(result.getBoolean(column)).isFalse();
                }
            }
        }
    }

    private static Connection connect() throws Exception {
        return DriverManager.getConnection(POSTGRES.getJdbcUrl(), POSTGRES.getUsername(), POSTGRES.getPassword());
    }
}
