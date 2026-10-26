package ru.alphafuture.credit;

import jakarta.servlet.http.*;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.time.*;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;

/** Вход существующих клиентов, отзыв сессий и сведения о компаниях. */
@RestController
class Accounts {
    record Login(
            @NotBlank @Size(max = 120) String login, @NotBlank @Size(max = 72) String password) {}

    private final JdbcClient db;
    private final PasswordEncoder passwords;
    private final Access access;
    private final Json json;
    private final String dummy;
    private final BrowserSessions sessions;
    private final Map<String, Attempts> limits = new ConcurrentHashMap<>();

    private record Attempts(long minute, int count) {}

    Accounts(
            JdbcClient db,
            PasswordEncoder passwords,
            Access access,
            Json json,
            BrowserSessions sessions) {
        this.db = db;
        this.passwords = passwords;
        this.access = access;
        this.json = json;
        this.sessions = sessions;
        this.dummy = passwords.encode(Json.token());
    }

    @GetMapping("/health")
    Map<String, String> health() {
        db.sql("SELECT 1").query(Integer.class).single();
        return Map.of("status", "ok");
    }

    @PostMapping("/auth/login")
    Map<String, Object> login(@Valid @RequestBody Login input) {
        var session = issue(input);
        return Map.of(
                "accessToken",
                session.token(),
                "tokenType",
                "Bearer",
                "expiresAt",
                session.expiresAt());
    }

    record Session(String token, Instant expiresAt) {}

    @GetMapping("/auth/csrf")
    Map<String, String> csrf(CsrfToken token) {
        return Map.of("headerName", token.getHeaderName(), "token", token.getToken());
    }

    @PostMapping("/auth/session")
    @Transactional
    Map<String, Object> browserLogin(
            @Valid @RequestBody Login input,
            HttpServletRequest request,
            HttpServletResponse response) {
        var session = issue(input);
        String previous = sessions.cookieToken(request);
        if (previous != null)
            db.sql(
                            "UPDATE credit.api_session SET revoked_at=now() WHERE token_hash=:hash AND revoked_at IS NULL")
                    .param("hash", Json.hash(previous))
                    .update();
        sessions.set(response, session.token(), Duration.ofSeconds(43200));
        sessions.csrf.saveToken(null, request, response);
        return Map.of("status", "ok", "expiresAt", session.expiresAt());
    }

    private Session issue(Login input) {
        if (input.password().getBytes(java.nio.charset.StandardCharsets.UTF_8).length > 72)
            throw ApiFailure.invalid("password", "Максимум 72 байта UTF-8");
        long minute = Instant.now().getEpochSecond() / 60;
        limits.entrySet().removeIf(e -> e.getValue().minute() < minute);
        if (limits.size() > 10000)
            throw new ApiFailure(429, "LOGIN_LIMIT", "Повторите вход позднее");
        var attempts =
                limits.compute(
                        input.login().toLowerCase(Locale.ROOT),
                        (key, old) ->
                                new Attempts(
                                        minute,
                                        old == null || old.minute() != minute
                                                ? 1
                                                : old.count() + 1));
        if (attempts.count() > 10)
            throw new ApiFailure(429, "LOGIN_LIMIT", "Слишком много попыток входа");
        var account =
                db
                        .sql(
                                "SELECT id,password_hash,status FROM credit.app_user WHERE lower(login)=lower(:login)")
                        .param("login", input.login())
                        .query()
                        .listOfRows()
                        .stream()
                        .findFirst();
        boolean valid =
                passwords.matches(
                        input.password(),
                        account.map(a -> a.get("password_hash").toString()).orElse(dummy));
        if (!valid || account.isEmpty() || !account.get().get("status").equals("ACTIVE"))
            throw new ApiFailure(401, "INVALID_CREDENTIALS", "Неверный логин или пароль");
        String token = Json.token();
        Instant expiry = Instant.now().plusSeconds(43200);
        db.sql(
                        "INSERT INTO credit.api_session(token_hash,user_id,expires_at) VALUES (:hash,:user,:expiry)")
                .param("hash", Json.hash(token))
                .param("user", account.get().get("id"))
                .param("expiry", java.sql.Timestamp.from(expiry))
                .update();
        return new Session(token, expiry);
    }

    @PostMapping("/auth/logout")
    @Transactional
    Map<String, String> logout(HttpServletRequest request, HttpServletResponse response) {
        var credential =
                (BrowserSessions.Credential) request.getAttribute(BrowserSessions.CREDENTIAL);
        db.sql(
                        "UPDATE credit.api_session SET revoked_at=now() WHERE token_hash=:hash AND user_id=:user")
                .param("hash", Json.hash(credential.token()))
                .param("user", access.user())
                .update();
        if (credential.browser()) {
            sessions.clear(response);
            sessions.csrf.saveToken(null, request, response);
        }
        return Map.of("status", "ok");
    }

    @GetMapping("/me")
    Map<String, Object> me() {
        return Map.of(
                "user",
                db.sql("SELECT id,login,display_name FROM credit.app_user WHERE id=:user")
                        .param("user", access.user())
                        .query()
                        .singleRow(),
                "parties",
                db.sql(
                                "SELECT p.id,p.name,p.party_kind,p.tax_id,m.access_role FROM credit.party p JOIN credit.party_membership m ON m.party_id=p.id WHERE m.user_id=:user AND m.revoked_at IS NULL ORDER BY p.id")
                        .param("user", access.user())
                        .query()
                        .listOfRows(),
                "bankApprover",
                access.bank());
    }

    @GetMapping("/companies/{id}/profile")
    Map<String, Object> company(@PathVariable UUID id) {
        access.member(id, false, false);
        var row =
                db
                        .sql(
                                "SELECT p.id,p.name,p.tax_id,p.party_kind,p.registered_on,b.profile_data,b.field_sources FROM credit.party p LEFT JOIN credit.business_profile b ON b.party_id=p.id WHERE p.id=:id")
                        .param("id", id)
                        .query()
                        .listOfRows()
                        .stream()
                        .findFirst()
                        .orElseThrow(ApiFailure::missing);
        var result = new LinkedHashMap<>(row);
        for (String key : List.of("profile_data", "field_sources"))
            if (result.get(key) != null) result.put(key, json.read(result.get(key).toString()));
        return result;
    }
}
