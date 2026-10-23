package ru.alphafuture.credit;

import jakarta.servlet.*;
import jakarta.servlet.http.*;
import java.io.IOException;
import java.util.*;
import org.springframework.context.annotation.*;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.*;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

/** Сессии Bearer хранятся только в виде SHA-256; все операции проверяют доступ. */
@Configuration
class Security {
    @Bean
    PasswordEncoder passwords() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    SecurityFilterChain chain(HttpSecurity http, JdbcClient db) throws Exception {
        var filter =
                new OncePerRequestFilter() {
                    @Override
                    protected void doFilterInternal(
                            HttpServletRequest req, HttpServletResponse res, FilterChain chain)
                            throws ServletException, IOException {
                        String header = req.getHeader("Authorization");
                        if (header != null && header.startsWith("Bearer ")) {
                            var users =
                                    db.sql(
                                                    "SELECT u.id FROM credit.api_session s JOIN credit.app_user u ON u.id=s.user_id WHERE s.token_hash=:hash AND s.revoked_at IS NULL AND s.expires_at>now() AND u.status='ACTIVE'")
                                            .param("hash", Json.hash(header.substring(7)))
                                            .query(UUID.class)
                                            .list();
                            if (!users.isEmpty())
                                SecurityContextHolder.getContext()
                                        .setAuthentication(
                                                new UsernamePasswordAuthenticationToken(
                                                        users.getFirst(), null, List.of()));
                        }
                        chain.doFilter(req, res);
                    }
                };
        return http.csrf(c -> c.disable())
                .sessionManagement(c -> c.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(
                        c ->
                                c.requestMatchers(
                                                "/health",
                                                "/auth/login",
                                                "/products",
                                                "/products/**",
                                                "/v3/api-docs/**",
                                                "/swagger-ui/**",
                                                "/swagger-ui.html")
                                        .permitAll()
                                        .anyRequest()
                                        .authenticated())
                .exceptionHandling(
                        c ->
                                c.authenticationEntryPoint(
                                        (req, res, ex) -> {
                                            res.setStatus(401);
                                            res.setContentType("application/problem+json");
                                            res.getWriter()
                                                    .write(
                                                            "{\"status\":401,\"code\":\"UNAUTHORIZED\"}");
                                        }))
                .addFilterBefore(filter, UsernamePasswordAuthenticationFilter.class)
                .build();
    }
}

/** Полномочия клиента и банковского сотрудника проверяются по актуальным данным БД. */
@Component
class Access {
    private final JdbcClient db;

    Access(JdbcClient db) {
        this.db = db;
    }

    UUID user() {
        var auth = SecurityContextHolder.getContext().getAuthentication();
        if (auth == null || !(auth.getPrincipal() instanceof UUID id))
            throw new ApiFailure(401, "UNAUTHORIZED", "Войдите в кабинет");
        return id;
    }

    boolean bank() {
        return db.sql(
                        "SELECT EXISTS(SELECT 1 FROM credit.user_role WHERE user_id=:id AND role_code='BANK_APPROVER')")
                .param("id", user())
                .query(Boolean.class)
                .single();
    }

    void requireBank() {
        if (!bank()) throw new ApiFailure(403, "FORBIDDEN", "Нужна роль BANK_APPROVER");
    }

    void member(UUID party, boolean write, boolean owner) {
        var roles =
                db.sql(
                                "SELECT access_role FROM credit.party_membership WHERE party_id=:party AND user_id=:user AND revoked_at IS NULL")
                        .param("party", party)
                        .param("user", user())
                        .query(String.class)
                        .list();
        if (roles.isEmpty()) throw ApiFailure.missing();
        if (owner && !roles.getFirst().equals("OWNER")
                || write && roles.getFirst().equals("VIEWER"))
            throw new ApiFailure(403, "FORBIDDEN", "Недостаточно прав");
    }
}
