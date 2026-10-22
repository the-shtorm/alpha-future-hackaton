package ru.alphafuture.credit.security;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.web.bind.annotation.*;
import ru.alphafuture.credit.api.ApiException;
import ru.alphafuture.credit.api.JsonSupport;

import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

@RestController
public class AccountController {
    private final JdbcClient db;
    private final PasswordEncoder passwords;
    private final JsonSupport json;
    private final Access access;
    private final String dummyHash;
    private record Attempts(long window, int count) {}
    private final ConcurrentHashMap<String, Attempts> attempts = new ConcurrentHashMap<>();
    public AccountController(JdbcClient db, PasswordEncoder passwords, JsonSupport json, Access access) {
        this.db = db; this.passwords = passwords; this.json = json; this.access = access;
        this.dummyHash = passwords.encode(json.token());
    }
    public record Login(@NotBlank @Size(max=120) String login, @NotBlank @Size(max=72) String password) {}
    public record Token(String accessToken,String tokenType,Instant expiresAt) {}
    @io.swagger.v3.oas.annotations.security.SecurityRequirements
    @PostMapping("/auth/login")
    public Token login(@Valid @RequestBody Login request) {
        if (request.password().getBytes(java.nio.charset.StandardCharsets.UTF_8).length > 72)
            throw ApiException.invalid("password", "Пароль должен занимать не более 72 байт UTF-8");
        long minute = Instant.now().getEpochSecond() / 60;
        attempts.entrySet().removeIf(e -> e.getValue().window() < minute);
        if (attempts.size() > 10000) throw new ApiException(429, "LOGIN_LIMIT", "Повторите вход позднее");
        var tries = attempts.compute(request.login().toLowerCase(java.util.Locale.ROOT), (key, old) ->
            new Attempts(minute, old == null || old.window() != minute ? 1 : old.count() + 1));
        if (tries.count() > 10) throw new ApiException(429, "LOGIN_LIMIT", "Слишком много попыток входа");
        var users = db.sql("SELECT id, password_hash, status FROM credit.app_user WHERE lower(login)=lower(:login)")
            .param("login", request.login()).query((rs, n) -> new Account(rs.getObject(1, UUID.class), rs.getString(2), rs.getString(3))).list();
        var user = users.isEmpty() ? null : users.getFirst();
        boolean valid = passwords.matches(request.password(), user == null ? dummyHash : user.hash());
        if (!valid || user == null || !user.status().equals("ACTIVE"))
            throw new ApiException(401, "INVALID_CREDENTIALS", "Неверный логин или пароль");
        String token = json.token();
        Instant expires = Instant.now().plus(12, ChronoUnit.HOURS);
        db.sql("INSERT INTO credit.api_session(token_hash,user_id,expires_at) VALUES (:hash,:user,:expires)")
            .param("hash", JsonSupport.hash(token)).param("user", user.id()).param("expires", java.sql.Timestamp.from(expires)).update();
        return new Token(token,"Bearer",expires);
    }
    private record Account(UUID id, String hash, String status) {}
    @PostMapping("/auth/logout")
    public Map<String, String> logout(@RequestHeader("Authorization") String auth) {
        db.sql("UPDATE credit.api_session SET revoked_at=now() WHERE token_hash=:hash AND user_id=:user")
            .param("hash", JsonSupport.hash(auth.substring(7))).param("user", access.user()).update();
        return Map.of("status", "ok");
    }
    @GetMapping("/me")
    public Map<String, Object> me() {
        var user = db.sql("SELECT id,login,display_name FROM credit.app_user WHERE id=:id")
            .param("id", access.user()).query().singleRow();
        var parties = db.sql("""
            SELECT p.id,p.name,p.party_kind,p.tax_id,m.access_role FROM credit.party p
            JOIN credit.party_membership m ON m.party_id=p.id
            WHERE m.user_id=:user AND m.revoked_at IS NULL ORDER BY p.name,p.id
            """).param("user", access.user()).query().listOfRows();
        return Map.of("user", user, "parties", parties);
    }
    @io.swagger.v3.oas.annotations.security.SecurityRequirements
    @GetMapping("/health")
    public Map<String, String> health() {
        db.sql("SELECT 1").query(Integer.class).single();
        return Map.of("status", "ok");
    }
}
