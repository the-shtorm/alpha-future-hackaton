package ru.alphafuture.credit;

import java.math.*;
import java.util.Optional;
import org.springframework.stereotype.Component;

/** Точный расчет аннуитета по опубликованному типу графика; неизвестные графики не подменяются. */
@Component
class Payments {
    private static final MathContext MC = MathContext.DECIMAL128;

    Optional<BigDecimal> monthly(
            Catalog.Product product, BigDecimal amount, int months, BigDecimal annualRatePct) {
        if (!product.policy().path("repayment").asText().equals("ANNUITY")
                || !product.policy().path("pricing").path("rate_type").asText().equals("FIXED"))
            return Optional.empty();
        if (months < 1
                || months > 1200
                || amount.signum() <= 0
                || annualRatePct == null
                || annualRatePct.signum() < 0) return Optional.empty();
        BigDecimal monthlyRate = annualRatePct.divide(new BigDecimal("1200"), MC), payment;
        if (monthlyRate.signum() == 0) payment = amount.divide(BigDecimal.valueOf(months), MC);
        else {
            BigDecimal power = BigDecimal.ONE.add(monthlyRate, MC).pow(months, MC);
            payment =
                    amount.multiply(monthlyRate, MC)
                            .multiply(power, MC)
                            .divide(power.subtract(BigDecimal.ONE, MC), MC);
        }
        var fee = product.policy().path("pricing").path("maintenance_fee_rub");
        if (!fee.isNumber() || fee.decimalValue().signum() < 0) return Optional.empty();
        return Optional.of(payment.add(fee.decimalValue()).setScale(2, RoundingMode.CEILING));
    }
}
