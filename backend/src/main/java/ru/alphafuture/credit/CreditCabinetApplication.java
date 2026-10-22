package ru.alphafuture.credit;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication(exclude=org.springframework.boot.autoconfigure.security.servlet.UserDetailsServiceAutoConfiguration.class)
public class CreditCabinetApplication {
    public static void main(String[] args) {
        SpringApplication.run(CreditCabinetApplication.class, args);
    }
}

