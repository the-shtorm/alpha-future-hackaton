package ru.alphafuture.credit.catalog;

import com.fasterxml.jackson.annotation.JsonFormat;
import com.fasterxml.jackson.databind.JsonNode;
import io.swagger.v3.oas.annotations.media.Schema;
import java.math.BigDecimal;
import java.util.UUID;

public record ProductCard(UUID id, UUID versionId, String code, String name, String providerCode,
    boolean synthetic, String versionCode, String currency, String facilityKind,
    @JsonFormat(shape=JsonFormat.Shape.STRING) @Schema(implementation=String.class) BigDecimal minAmount,
    @JsonFormat(shape=JsonFormat.Shape.STRING) @Schema(implementation=String.class) BigDecimal maxAmount,
    int minTermMonths, int maxTermMonths,
    @JsonFormat(shape=JsonFormat.Shape.STRING) @Schema(implementation=String.class) BigDecimal annualRatePct,
    JsonNode borrowerKinds, JsonNode purposes, JsonNode collateral, JsonNode guarantor) {
    public static ProductCard from(Product p) {
        return new ProductCard(p.id(),p.versionId(),p.code(),p.name(),p.providerCode(),p.synthetic(),p.versionCode(),
            p.currency(),p.facilityKind(),p.minAmount(),p.maxAmount(),p.minTermMonths(),p.maxTermMonths(),p.annualRatePct(),
            p.borrowerKinds(),p.purposes(),p.policy().path("collateral"),p.policy().path("guarantor"));
    }
}
