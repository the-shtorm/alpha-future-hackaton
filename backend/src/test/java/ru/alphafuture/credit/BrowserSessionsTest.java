package ru.alphafuture.credit;

import static org.assertj.core.api.Assertions.*;

import jakarta.servlet.http.Cookie;
import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;

class BrowserSessionsTest {
    @Test
    void httpsCookiesAreHostOnlyHttpOnlyAndSecureIncludingDeletion() {
        var sessions = new BrowserSessions(true);
        var response = new MockHttpServletResponse();
        sessions.set(response, "fixture", Duration.ofHours(12));
        assertThat(response.getHeader("Set-Cookie"))
                .contains(
                        "__Host-ALPHA_SESSION=fixture",
                        "Secure",
                        "HttpOnly",
                        "SameSite=Lax",
                        "Path=/",
                        "Max-Age=43200")
                .doesNotContain("Domain=");
        var csrf = new MockHttpServletResponse();
        sessions.csrf.saveToken(
                sessions.csrf.generateToken(new MockHttpServletRequest()),
                new MockHttpServletRequest(),
                csrf);
        assertThat(csrf.getHeader("Set-Cookie"))
                .contains("__Host-ALPHA_CSRF=", "Secure", "HttpOnly", "Path=/")
                .doesNotContain("Domain=");
        assertThat(csrf.getCookie("__Host-ALPHA_CSRF").getAttribute("SameSite")).isEqualTo("Lax");
        var cleared = new MockHttpServletResponse();
        sessions.clear(cleared);
        assertThat(cleared.getHeader("Set-Cookie")).contains("Max-Age=0", "Secure", "HttpOnly");
    }

    @Test
    void ambiguousCookiesAndInvalidExplicitAuthorizationCannotChooseAnotherIdentity() {
        var sessions = new BrowserSessions(false);
        var request = new MockHttpServletRequest();
        request.setCookies(new Cookie("ALPHA_SESSION", "one"), new Cookie("ALPHA_SESSION", "two"));
        assertThat(sessions.credential(request)).isNull();
        request.setCookies(new Cookie("ALPHA_SESSION", "one"));
        request.addHeader("Authorization", "Basic fixture");
        assertThat(sessions.credential(request)).isNull();
    }
}
