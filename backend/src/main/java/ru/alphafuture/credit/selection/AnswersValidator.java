package ru.alphafuture.credit.selection;

import com.fasterxml.jackson.databind.JsonNode;
import org.springframework.stereotype.Component;
import ru.alphafuture.credit.api.ApiException;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.Map;
import java.util.Set;

@Component
public class AnswersValidator {
    private static final Map<String, Set<String>> FIELDS = Map.of(
        "request", Set.of("purpose","amount","termMonths"),
        "registration", Set.of("taxId","name","borrowerKind","registeredOn","country"),
        "business", Set.of("actualStartedOn","region","sector","taxRegime","ipAgeYears","mspRegistry","marketplaceMonths","bankAccountMonths"),
        "financial", Set.of("revenue","periodFrom","periodTo","debtBalance","monthlyDebtPayment","overdue"),
        "security", Set.of("collateralReady","guarantorReady","collateralValue"),
        "project", Set.of("ownContributionPct","purchasePrice","repaymentSource"));
    private static final Set<String> MONEY = Set.of("amount","revenue","debtBalance","monthlyDebtPayment","collateralValue","purchasePrice","ownContributionPct");
    private static final Set<String> DATES = Set.of("registeredOn","actualStartedOn","periodFrom","periodTo");
    private static final Set<String> BOOL = Set.of("mspRegistry","overdue","collateralReady","guarantorReady");
    private static final Set<String> INTS = Set.of("termMonths","ipAgeYears","marketplaceMonths","bankAccountMonths");
    public void validate(JsonNode answers) {
        if (answers==null || !answers.isObject()) throw ApiException.invalid("answers","Ожидается JSON-объект");
        answers.fields().forEachRemaining(section -> {
            String group=section.getKey();
            if (!FIELDS.containsKey(group) || !section.getValue().isObject()) throw ApiException.invalid(group,"Неизвестный раздел или неверный формат");
            section.getValue().fields().forEachRemaining(field -> {
                String key=field.getKey(), path=group+"."+key; JsonNode value=field.getValue();
                if (!FIELDS.get(group).contains(key)) throw ApiException.invalid(path,"Неизвестное поле");
                if (value.isNull()) return;
                if (MONEY.contains(key)) {
                    if (!value.isTextual() || !value.asText().matches("(?:0|[1-9][0-9]{0,16})(?:\\.[0-9]{1,2})?"))
                        throw ApiException.invalid(path,"Нужна неотрицательная десятичная строка, до двух знаков после точки");
                    BigDecimal number=new BigDecimal(value.asText());
                    if ((key.equals("amount") || key.equals("purchasePrice")) && number.signum()==0) throw ApiException.invalid(path,"Значение должно быть положительным");
                    if (key.equals("ownContributionPct") && number.compareTo(new BigDecimal("100"))>0) throw ApiException.invalid(path,"Процент от 0 до 100");
                } else if (DATES.contains(key)) {
                    try {
                        if (!value.isTextual() || !value.asText().matches("[0-9]{4}-[0-9]{2}-[0-9]{2}")) throw new IllegalArgumentException();
                        if (LocalDate.parse(value.asText()).isAfter(LocalDate.now(ZoneOffset.UTC))) throw new IllegalArgumentException();
                    } catch (Exception ex) { throw ApiException.invalid(path,"Ожидается прошедшая дата YYYY-MM-DD"); }
                } else if (BOOL.contains(key)) {
                    if (!value.isBoolean()) throw ApiException.invalid(path,"Ожидается true/false или null");
                } else if (INTS.contains(key)) {
                    if (!value.isIntegralNumber() || !value.canConvertToInt() || value.asInt()<0 || value.asInt()>1200 || (key.equals("termMonths") && value.asInt()==0))
                        throw ApiException.invalid(path,"Недопустимое целое число");
                } else if (!value.isTextual() || value.asText().isBlank() || value.asText().length()>1000) {
                    throw ApiException.invalid(path,"Ожидается непустая строка длиной до 1000 символов");
                }
            });
        });
        String inn=text(answers,"registration","taxId"),kind=text(answers,"registration","borrowerKind");
        if (inn!=null && !TaxId.valid(inn)) throw ApiException.invalid("registration.taxId","Неверные контрольные разряды ИНН");
        if (kind!=null && !Set.of("IP","LLC").contains(kind)) throw ApiException.invalid("registration.borrowerKind","Укажите IP или LLC");
        if (kind!=null && inn!=null && inn.length()!=(kind.equals("LLC")?10:12)) throw ApiException.invalid("registration.taxId","ИНН не соответствует форме бизнеса");
        String regime=text(answers,"business","taxRegime");
        if (regime!=null && !Set.of("OSNO","USN","PSN","AUSN","NPD","COMBINED","OTHER","UNKNOWN").contains(regime))
            throw ApiException.invalid("business.taxRegime","Неизвестный налоговый режим");
        if ("LLC".equals(kind) && Set.of("PSN","NPD").contains(regime==null?"":regime))
            throw ApiException.invalid("business.taxRegime","Режим несовместим с формой ООО");
        var from=text(answers,"financial","periodFrom"); var to=text(answers,"financial","periodTo");
        if (from!=null && to!=null && LocalDate.parse(from).isAfter(LocalDate.parse(to)))
            throw ApiException.invalid("financial.periodTo","Конец периода раньше начала");
        var registered=text(answers,"registration","registeredOn"); var started=text(answers,"business","actualStartedOn");
        if (registered!=null && started!=null && LocalDate.parse(started).isBefore(LocalDate.parse(registered)))
            throw ApiException.invalid("business.actualStartedOn","Начало работы раньше регистрации");
    }
    public static String text(JsonNode answers,String section,String field) {
        var value=answers.path(section).path(field);
        return value.isMissingNode() || value.isNull()?null:value.asText();
    }
}
