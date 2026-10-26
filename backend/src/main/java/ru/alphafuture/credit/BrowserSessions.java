package ru.alphafuture.credit;

import jakarta.servlet.http.*;
import java.time.Duration;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseCookie;
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;
import org.springframework.stereotype.Component;

/** Cookie-транспорт существующих серверных сессий; браузер не получает токен в JSON. */
@Component
class BrowserSessions {
    static final String CREDENTIAL = BrowserSessions.class.getName() + ".credential";

    record Credential(String token, boolean browser) {}

    final boolean secure;
    final String cookieName;
    final CookieCsrfTokenRepository csrf = new CookieCsrfTokenRepository();

    BrowserSessions(@Value("${cabinet.session.cookie-secure:true}") boolean secure) {
        this.secure = secure;
        cookieName = secure ? "__Host-ALPHA_SESSION" : "ALPHA_SESSION";
        csrf.setCookieName(secure ? "__Host-ALPHA_CSRF" : "ALPHA_CSRF");
        csrf.setCookiePath("/");
        csrf.setCookieCustomizer(c -> c.httpOnly(true).secure(secure).sameSite("Lax"));
    }

    String cookieToken(HttpServletRequest request) {
        String found = null;
        if (request.getCookies() != null)
            for (var cookie : request.getCookies())
                if (cookieName.equals(cookie.getName())) {
                    if (found != null) return null;
                    found = cookie.getValue();
                }
        return found == null || found.isBlank() ? null : found;
    }

    Credential credential(HttpServletRequest request) {
        String header = request.getHeader("Authorization");
        // An explicit invalid Authorization header must never fall back to another identity.
        if (header != null)
            return header.startsWith("Bearer ") && !header.substring(7).isBlank()
                    ? new Credential(header.substring(7), false)
                    : null;
        String token = cookieToken(request);
        return token == null ? null : new Credential(token, true);
    }

    void set(HttpServletResponse response, String token, Duration lifetime) {
        response.addHeader(
                HttpHeaders.SET_COOKIE,
                ResponseCookie.from(cookieName, token)
                        .httpOnly(true)
                        .secure(secure)
                        .sameSite("Lax")
                        .path("/")
                        .maxAge(lifetime)
                        .build()
                        .toString());
    }

    void clear(HttpServletResponse response) {
        set(response, "", Duration.ZERO);
    }

    boolean requiresCsrf(HttpServletRequest request) {
        if (java.util.Set.of("GET", "HEAD", "OPTIONS", "TRACE").contains(request.getMethod()))
            return false;
        if (request.getRequestURI().equals(request.getContextPath() + "/auth/session"))
            return true; // Protect login itself, including when there is no authenticated cookie
        // yet.
        return request.getHeader("Authorization") == null && cookieToken(request) != null;
    }
}
