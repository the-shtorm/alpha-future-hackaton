package ru.alphafuture.credit.security;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Profile;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.util.UUID;

@Component
@Profile("demo")
public class DemoAccounts implements ApplicationRunner {
    public static final UUID USER = UUID.fromString("da000000-0000-0000-0000-000000000001");
    public static final UUID PARTY = UUID.fromString("da000000-0000-0000-0000-000000000002");
    private final JdbcClient db;
    private final PasswordEncoder passwords;
    private final String password;
    public DemoAccounts(JdbcClient db, PasswordEncoder passwords, @Value("${cabinet.demo-password}") String password) {
        this.db = db; this.passwords = passwords; this.password = password;
    }
    @Override @Transactional
    public void run(ApplicationArguments args) {
        if (password.isBlank()) return;
        if (password.length() < 12 || password.getBytes(java.nio.charset.StandardCharsets.UTF_8).length > 72) throw new IllegalStateException("DEMO_PASSWORD must contain at least 12 characters and at most 72 UTF-8 bytes");
        db.sql("""
            INSERT INTO credit.app_user(id,login,password_hash,display_name)
            VALUES (:id,'demo-owner',:hash,'Владелец демонстрационной компании') ON CONFLICT (id) DO NOTHING
            """).param("id", USER).param("hash", passwords.encode(password)).update();
        db.sql("INSERT INTO credit.user_role(user_id,role_code) VALUES (:id,'CLIENT') ON CONFLICT DO NOTHING")
            .param("id", USER).update();
        db.sql("""
            INSERT INTO credit.party(id,party_kind,name,tax_id,registered_on,registry_status)
            VALUES (:id,'LLC','ООО Демонстрационная компания','7707083893','2020-01-01','SIMULATED') ON CONFLICT (id) DO NOTHING
            """).param("id", PARTY).update();
        db.sql("""
            INSERT INTO credit.party_membership(party_id,user_id,access_role)
            VALUES (:party,:user,'OWNER') ON CONFLICT DO NOTHING
            """).param("party", PARTY).param("user", USER).update();
    }
}
