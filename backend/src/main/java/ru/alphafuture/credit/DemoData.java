package ru.alphafuture.credit;

import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.*;
import org.springframework.context.annotation.Profile;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

/** Необязательные локальные учетные записи; пароли берутся только из окружения. */
@Component
@Profile("demo")
class DemoData implements ApplicationRunner {
    private final JdbcClient db;
    private final PasswordEncoder passwords;
    private final String clientPassword, bankPassword;
    private final DemoScenarios scenarios;

    DemoData(
            JdbcClient db,
            PasswordEncoder passwords,
            @Value("${cabinet.demo-password:}") String clientPassword,
            @Value("${cabinet.demo-bank-password:}") String bankPassword,
            DemoScenarios scenarios) {
        this.db = db;
        this.passwords = passwords;
        this.clientPassword = clientPassword;
        this.bankPassword = bankPassword;
        this.scenarios = scenarios;
    }

    @Override
    @Transactional
    public void run(ApplicationArguments args) {
        UUID client = account("demo-owner", clientPassword, "CLIENT");
        account("demo-bank", bankPassword, "BANK_APPROVER");
        if (client != null) {
            scenarios.seed(client);
            db.sql(
                            "INSERT INTO credit.party(party_kind,name,tax_id,registered_on) VALUES ('LLC','Демо-компания','7707083893','2020-01-01') ON CONFLICT DO NOTHING")
                    .update();
            UUID party =
                    db.sql(
                                    "SELECT id FROM credit.party WHERE party_kind='LLC' AND tax_id='7707083893'")
                            .query(UUID.class)
                            .single();
            db.sql(
                            "INSERT INTO credit.party_membership(party_id,user_id,access_role) VALUES (:party,:user,'OWNER') ON CONFLICT DO NOTHING")
                    .param("party", party)
                    .param("user", client)
                    .update();
        }
    }

    private UUID account(String login, String password, String role) {
        if (password.isEmpty()) return null;
        if (password.length() < 12
                || password.getBytes(java.nio.charset.StandardCharsets.UTF_8).length > 72)
            throw new IllegalArgumentException("Demo passwords must be 12..72 UTF-8 bytes");
        db.sql(
                        "INSERT INTO credit.app_user(login,password_hash,display_name) VALUES (:login,:hash,:login) ON CONFLICT DO NOTHING")
                .param("login", login)
                .param("hash", passwords.encode(password))
                .update();
        UUID id =
                db.sql("SELECT id FROM credit.app_user WHERE lower(login)=lower(:login)")
                        .param("login", login)
                        .query(UUID.class)
                        .single();
        db.sql(
                        "INSERT INTO credit.user_role(user_id,role_code) VALUES (:id,:role) ON CONFLICT DO NOTHING")
                .param("id", id)
                .param("role", role)
                .update();
        return id;
    }
}
