package ru.alphafuture.credit;

import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.math.BigDecimal;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.*;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;

/** Версионируемый серверный макроконтекст. Ставка не принимается в answers клиента. */
@RestController
class MacroContext {
    record Create(
            @NotBlank @Pattern(regexp = "(?:0|[1-9][0-9]{0,2})(?:\\.[0-9]{1,5})?")
                    String keyRatePct,
            @NotNull Instant validFrom,
            @NotNull Instant expiresAt,
            @NotBlank @Size(max = 200) String sourceCode) {}

    record Value(
            UUID id,
            String keyRatePct,
            Instant validFrom,
            Instant expiresAt,
            String sourceCode,
            Instant recordedAt) {}

    private final JdbcClient db;
    private final Access access;

    MacroContext(JdbcClient db, Access access) {
        this.db = db;
        this.access = access;
    }

    @PostMapping("/bank/macroeconomic-contexts")
    @Transactional
    Value create(@Valid @RequestBody Create input) {
        access.requireBank();
        var rate = new BigDecimal(input.keyRatePct());
        Instant now = Instant.now();
        if (rate.compareTo(new BigDecimal("100")) > 0
                || input.validFrom().isAfter(now)
                || !input.expiresAt().isAfter(now)
                || !input.expiresAt().isAfter(input.validFrom()))
            throw ApiFailure.invalid(
                    "macroeconomic", "Нужны действующая ставка 0..100 и корректный срок действия");
        UUID id = UUID.randomUUID();
        db.sql(
                        "INSERT INTO credit.macroeconomic_context(id,key_rate_pct,valid_from,expires_at,source_code,recorded_by) VALUES (:id,:rate,:from,:to,:source,:user)")
                .param("id", id)
                .param("rate", rate)
                .param("from", Timestamp.from(input.validFrom()))
                .param("to", Timestamp.from(input.expiresAt()))
                .param("source", input.sourceCode())
                .param("user", access.user())
                .update();
        return byId(id);
    }

    @GetMapping("/bank/macroeconomic-contexts/current")
    Value currentEndpoint() {
        access.requireBank();
        return current()
                .orElseThrow(
                        () ->
                                new ApiFailure(
                                        422,
                                        "MACRO_CONTEXT_REQUIRED",
                                        "Нет действующего серверного макроконтекста"));
    }

    Optional<Value> current() {
        return db.sql(
                        "SELECT * FROM credit.macroeconomic_context WHERE valid_from<=now() AND expires_at>now() ORDER BY valid_from DESC,recorded_at DESC,id DESC LIMIT 1")
                .query(this::map)
                .optional();
    }

    private Value byId(UUID id) {
        return db.sql("SELECT * FROM credit.macroeconomic_context WHERE id=:id")
                .param("id", id)
                .query(this::map)
                .single();
    }

    private Value map(java.sql.ResultSet rs, int n) throws java.sql.SQLException {
        return new Value(
                rs.getObject("id", UUID.class),
                rs.getString("key_rate_pct"),
                rs.getTimestamp("valid_from").toInstant(),
                rs.getTimestamp("expires_at").toInstant(),
                rs.getString("source_code"),
                rs.getTimestamp("recorded_at").toInstant());
    }
}
