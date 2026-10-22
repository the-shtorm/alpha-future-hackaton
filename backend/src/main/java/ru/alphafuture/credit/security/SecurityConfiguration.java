package ru.alphafuture.credit.security;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.AnonymousAuthenticationFilter;
import org.springframework.web.filter.OncePerRequestFilter;
import ru.alphafuture.credit.api.JsonSupport;

import java.io.IOException;
import java.util.List;
import java.util.Map;
import java.util.UUID;

@Configuration
public class SecurityConfiguration {
    @Bean PasswordEncoder passwordEncoder() { return PasswordEncoderFactories.createDelegatingPasswordEncoder(); }

    @Bean
    SecurityFilterChain security(HttpSecurity http, JdbcClient db, ObjectMapper mapper) throws Exception {
        return http
            // Only explicitly supplied Bearer tokens authenticate; no cookies or HTTP Basic.
            .csrf(csrf -> csrf.disable())
            .sessionManagement(s -> s.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .requestCache(c -> c.disable())
            .authorizeHttpRequests(a -> a
                .requestMatchers("/health", "/error", "/auth/login", "/v3/api-docs/**", "/swagger-ui/**", "/swagger-ui.html").permitAll()
                .requestMatchers(HttpMethod.GET, "/products", "/products/*").permitAll()
                .requestMatchers("/business/lookup", "/selection-profiles", "/selection-profiles/**").permitAll()
                .anyRequest().authenticated())
            .exceptionHandling(e -> e
                .authenticationEntryPoint((req, res, ex) -> problem(res, mapper, 401, "UNAUTHORIZED"))
                .accessDeniedHandler((req, res, ex) -> problem(res, mapper, 403, "FORBIDDEN")))
            .addFilterBefore(new OncePerRequestFilter() {
                @Override protected void doFilterInternal(HttpServletRequest req, HttpServletResponse res, FilterChain chain)
                        throws ServletException, IOException {
                    String header = req.getHeader("Authorization");
                    if (header != null) {
                        if (!header.startsWith("Bearer ") || header.length() > 100) {
                            problem(res, mapper, 401, "INVALID_TOKEN"); return;
                        }
                        var user = db.sql("""
                            SELECT s.user_id FROM credit.api_session s JOIN credit.app_user u ON u.id=s.user_id
                            WHERE s.token_hash=:hash AND s.revoked_at IS NULL AND s.expires_at > now() AND u.status='ACTIVE'
                            """).param("hash", JsonSupport.hash(header.substring(7))).query(UUID.class).optional();
                        if (user.isEmpty()) { problem(res, mapper, 401, "INVALID_TOKEN"); return; }
                        SecurityContextHolder.getContext().setAuthentication(
                            new UsernamePasswordAuthenticationToken(user.get(), null, List.of()));
                    }
                    chain.doFilter(req, res);
                }
            }, AnonymousAuthenticationFilter.class)
            .build();
    }
    private static void problem(HttpServletResponse res, ObjectMapper mapper, int status, String code) throws IOException {
        res.setStatus(status);
        res.setContentType("application/problem+json");
        mapper.writeValue(res.getOutputStream(), Map.of("status", status, "title", code, "detail",
            status == 401 ? "Требуется аутентификация" : "Недостаточно полномочий", "code", code, "errors", List.of()));
    }
}
