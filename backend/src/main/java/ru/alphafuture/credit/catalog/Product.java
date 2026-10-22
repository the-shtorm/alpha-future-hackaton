package ru.alphafuture.credit.catalog;

import com.fasterxml.jackson.annotation.JsonFormat;
import com.fasterxml.jackson.databind.JsonNode;
import java.math.BigDecimal;
import java.util.UUID;

public record Product(UUID id, UUID versionId, String code, String name, String providerCode,
    boolean synthetic, String versionCode, String currency, String facilityKind,
    @JsonFormat(shape=JsonFormat.Shape.STRING) @io.swagger.v3.oas.annotations.media.Schema(implementation=String.class) BigDecimal minAmount,
    @JsonFormat(shape=JsonFormat.Shape.STRING) @io.swagger.v3.oas.annotations.media.Schema(implementation=String.class) BigDecimal maxAmount,
    int minTermMonths, int maxTermMonths,
    @JsonFormat(shape=JsonFormat.Shape.STRING) @io.swagger.v3.oas.annotations.media.Schema(implementation=String.class) BigDecimal annualRatePct,
    JsonNode borrowerKinds, JsonNode purposes, JsonNode policy) {}
