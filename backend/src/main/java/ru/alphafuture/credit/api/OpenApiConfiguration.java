package ru.alphafuture.credit.api;

import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.info.Info;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition(info=@Info(title="Умный кредитный кабинет",version="0.2.0",description="Каталог, предварительный подбор и демонстрационная заявка. Подбор не является кредитным решением."), security=@io.swagger.v3.oas.annotations.security.SecurityRequirement(name="bearerAuth"))
@SecurityScheme(name="bearerAuth",type=SecuritySchemeType.HTTP,scheme="bearer",bearerFormat="opaque")
public class OpenApiConfiguration {}
