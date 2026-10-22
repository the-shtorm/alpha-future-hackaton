package ru.alphafuture.credit.security;

import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;
import ru.alphafuture.credit.api.ApiException;

import java.util.UUID;

@Component
public class Access {
    private final JdbcClient db;
    public Access(JdbcClient db) { this.db = db; }
    public UUID userOrNull() {
        Authentication auth = SecurityContextHolder.getContext().getAuthentication();
        return auth != null && auth.getPrincipal() instanceof UUID id ? id : null;
    }
    public UUID user() {
        var id = userOrNull();
        if (id == null) throw new ApiException(401, "UNAUTHORIZED", "Войдите в кабинет");
        return id;
    }
    public String membership(UUID partyId, boolean write, boolean owner) {
        var role = db.sql("""
            SELECT access_role FROM credit.party_membership
            WHERE party_id=:party AND user_id=:user AND revoked_at IS NULL
            """).param("party", partyId).param("user", user()).query(String.class).optional()
            .orElseThrow(ApiException::notFound);
        if ((write && role.equals("VIEWER")) || (owner && !role.equals("OWNER")))
            throw new ApiException(403, "FORBIDDEN", "Недостаточно полномочий для действия");
        return role;
    }
}
