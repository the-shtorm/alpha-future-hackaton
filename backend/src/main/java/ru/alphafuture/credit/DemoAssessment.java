package ru.alphafuture.credit;

import java.math.*;
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/** Явно разрешенная пользователем временная взвешенная DEMO-оценка; без обучения и случайности. */
@Component
class DemoAssessment {
    static final String VERSION = "demo-fixed-weights-1";
    static final BigDecimal THRESHOLD = new BigDecimal("0.55");
    private final boolean enabled;

    DemoAssessment(
            @org.springframework.beans.factory.annotation.Value(
                            "${cabinet.demo-assessment-enabled:false}")
                    boolean enabled) {
        this.enabled = enabled;
    }

    boolean enabled(Catalog.Product product) {
        return enabled && product.synthetic();
    }

    record Value(
            String mode,
            String version,
            String score,
            String threshold,
            String riskMarginPct,
            Map<String, String> factors) {}

    Value calculate(
            BigDecimal debtRatio,
            BigDecimal overdue,
            BigDecimal amountToRevenue,
            long operatingMonths) {
        var debt = cap(debtRatio.divide(new BigDecimal("0.40"), 12, RoundingMode.HALF_UP));
        var delay = cap(overdue.divide(new BigDecimal("0.20"), 12, RoundingMode.HALF_UP));
        var scale = cap(amountToRevenue.divide(new BigDecimal("12"), 12, RoundingMode.HALF_UP));
        var age =
                cap(
                        new BigDecimal("12")
                                .divide(
                                        BigDecimal.valueOf(Math.max(0, operatingMonths) + 12),
                                        12,
                                        RoundingMode.HALF_UP));
        BigDecimal score =
                BigDecimal.ONE
                        .subtract(debt.multiply(new BigDecimal("0.45")))
                        .subtract(delay.multiply(new BigDecimal("0.25")))
                        .subtract(scale.multiply(new BigDecimal("0.20")))
                        .subtract(age.multiply(new BigDecimal("0.10")))
                        .max(BigDecimal.ZERO)
                        .setScale(8, RoundingMode.HALF_UP);
        BigDecimal margin =
                new BigDecimal("15")
                        .add(BigDecimal.ONE.subtract(score).multiply(new BigDecimal("20")))
                        .setScale(5, RoundingMode.HALF_UP);
        return new Value(
                "DEMO",
                VERSION,
                score.toPlainString(),
                THRESHOLD.toPlainString(),
                margin.toPlainString(),
                Map.of(
                        "existingDebtPenalty",
                        debt.toPlainString(),
                        "overduePenalty",
                        delay.toPlainString(),
                        "amountPenalty",
                        scale.toPlainString(),
                        "shortHistoryPenalty",
                        age.toPlainString()));
    }

    private BigDecimal cap(BigDecimal value) {
        return value.max(BigDecimal.ZERO).min(BigDecimal.ONE);
    }
}
