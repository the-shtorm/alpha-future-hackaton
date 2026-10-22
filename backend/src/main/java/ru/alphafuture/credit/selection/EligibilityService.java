package ru.alphafuture.credit.selection;

import com.fasterxml.jackson.databind.JsonNode;
import org.springframework.stereotype.Service;
import ru.alphafuture.credit.catalog.Product;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

import static ru.alphafuture.credit.selection.AnswersValidator.text;

@Service
public class EligibilityService {
    public record Reason(String field,String code,String message) {}
    public record Result(UUID productId,UUID productVersionId,String productName,String eligibility,
                         List<Reason> passed,List<Reason> failed,List<Reason> unconfirmed) {}
    public Result evaluate(Product p, JsonNode a) {
        var passed=new ArrayList<Reason>(); var failed=new ArrayList<Reason>(); var unknown=new ArrayList<Reason>();
        String purpose=text(a,"request","purpose"),kind=text(a,"registration","borrowerKind");
        enumRule("request.purpose",purpose,p.purposes(),passed,failed,unknown);
        enumRule("registration.borrowerKind",kind,p.borrowerKinds(),passed,failed,unknown);
        range("request.amount",decimal(a,"request","amount"),p.minAmount(),p.maxAmount(),passed,failed,unknown);
        range("request.termMonths",decimal(a,"request","termMonths"),BigDecimal.valueOf(p.minTermMonths()),BigDecimal.valueOf(p.maxTermMonths()),passed,failed,unknown);
        JsonNode rules=p.policy().path("eligibility");
        String started=text(a,"business","actualStartedOn");
        BigDecimal age=started==null?null:BigDecimal.valueOf(ChronoUnit.MONTHS.between(LocalDate.parse(started),LocalDate.now(ZoneOffset.UTC)));
        minimum("business.actualStartedOn",age,rules.path("min_business_age_months").decimalValue(),passed,failed,unknown);
        String country=text(a,"registration","country");
        if (country==null) missing(unknown,"registration.country");
        else condition("registration.country",country.equals(rules.path("country").asText()),"Страна регистрации",passed,failed);
        if (text(a,"business","region")==null) missing(unknown,"business.region");
        String sector=text(a,"business","sector");
        if (sector==null) missing(unknown,"business.sector");
        else condition("business.sector",!contains(p.policy().path("common_policy").path("excluded_sectors"),sector),"Ограничения отрасли",passed,failed);
        enumRule("business.taxRegime",text(a,"business","taxRegime"),rules.path("tax_regimes"),passed,failed,unknown);
        if ("IP".equals(kind)) minimum("business.ipAgeYears",decimal(a,"business","ipAgeYears"),rules.path("min_ip_age_years").decimalValue(),passed,failed,unknown);
        BigDecimal revenue=decimal(a,"financial","revenue"),monthly=null;
        String from=text(a,"financial","periodFrom"),to=text(a,"financial","periodTo");
        if (from!=null && to!=null) {
            LocalDate begin=LocalDate.parse(from),end=LocalDate.parse(to);
            long months=ChronoUnit.MONTHS.between(begin,end.plusDays(1));
            boolean full=begin.getDayOfMonth()==1 && end.getDayOfMonth()==end.lengthOfMonth() && months>0;
            if (!full) unknown.add(new Reason("financial.periodFrom","INCOMPLETE_MONTHS","Нужны полные календарные месяцы выручки"));
            else {
                if (revenue!=null) monthly=revenue.divide(BigDecimal.valueOf(months),8,RoundingMode.HALF_UP);
                if (months<rules.path("revenue_window_months").asInt()) unknown.add(new Reason("financial.periodFrom","SHORT_HISTORY","Короткий период выручки требует подтверждения"));
                if (months>rules.path("revenue_window_months").asInt()) unknown.add(new Reason("financial.periodFrom","REVENUE_WINDOW","Укажите выручку за расчетное окно продукта"));
            }
        } else missing(unknown,"financial.periodFrom");
        minimum("financial.revenue",monthly,rules.path("min_average_monthly_revenue_rub").decimalValue(),passed,failed,unknown);
        var security=p.policy().path("collateral");
        if (security.path("required").asBoolean()) booleanRule(a,"security","collateralReady",passed,failed,unknown);
        String guarantee=kind==null?"":p.policy().path("guarantor").path(kind).asText();
        if (guarantee.contains("REQUIRED") && !guarantee.contains("NOT_REQUIRED")) booleanRule(a,"security","guarantorReady",passed,failed,unknown);
        BigDecimal minOwn=security.path("min_own_contribution_pct").decimalValue();
        if (minOwn.signum()>0) minimum("project.ownContributionPct",decimal(a,"project","ownContributionPct"),minOwn,passed,failed,unknown);
        if (security.hasNonNull("max_ltv")) {
            BigDecimal amount=decimal(a,"request","amount"),value=decimal(a,"security","collateralValue");
            if (value==null || amount==null) missing(unknown,"security.collateralValue");
            else condition("security.collateralValue",amount.compareTo(value.multiply(security.path("max_ltv").decimalValue()))<=0,"Предварительное отношение кредита к стоимости залога",passed,failed);
            unknown.add(new Reason("security.collateralValue","VALUATION_REQUIRED","Банк должен подтвердить стоимость и обременения залога"));
        }
        for (var extra:rules.path("extra_conditions")) {
            switch(extra.asText()) {
                case "MSP_REGISTRY" -> booleanRule(a,"business","mspRegistry",passed,failed,unknown);
                case "MANUFACTURING" -> {
                    if (sector==null) missing(unknown,"business.sector");
                    else condition("business.sector",sector.equals("MANUFACTURING"),"Производственная деятельность",passed,failed);
                }
                case "MARKETPLACE_6_MONTHS" -> minimum("business.marketplaceMonths",decimal(a,"business","marketplaceMonths"),BigDecimal.valueOf(6),passed,failed,unknown);
                case "DEMO_BANK_ACCOUNT_6_MONTHS" -> minimum("business.bankAccountMonths",decimal(a,"business","bankAccountMonths"),BigDecimal.valueOf(6),passed,failed,unknown);
                default -> unknown.add(new Reason("documents",extra.asText(),"При подаче нужно подтвердить условие: "+extra.asText()));
            }
        }
        if (a.path("financial").path("overdue").asBoolean()) unknown.add(new Reason("financial.overdue","REVIEW_REQUIRED","Просрочки требуют рассмотрения"));
        String status=!failed.isEmpty()?"INELIGIBLE":unknown.isEmpty()?"ELIGIBLE":"CONDITIONAL";
        return new Result(p.id(),p.versionId(),p.name(),status,List.copyOf(passed),List.copyOf(failed),List.copyOf(unknown));
    }
    private static BigDecimal decimal(JsonNode a,String section,String field) {
        String value=text(a,section,field); return value==null?null:new BigDecimal(value);
    }
    private static boolean contains(JsonNode array,String value) {
        for(var item:array) if (item.asText().equals(value)) return true;
        return false;
    }
    private static void missing(List<Reason> unknown,String field) { unknown.add(new Reason(field,"MISSING","Недостаточно данных для проверки условия")); }
    private static void condition(String field,boolean ok,String message,List<Reason> passed,List<Reason> failed) {
        (ok?passed:failed).add(new Reason(field,ok?"MATCH":"MISMATCH",message));
    }
    private static void enumRule(String field,String value,JsonNode allowed,List<Reason> passed,List<Reason> failed,List<Reason> unknown) {
        if (value==null || value.equals("UNKNOWN")) missing(unknown,field);
        else condition(field,contains(allowed,value),"Значение должно соответствовать условиям продукта",passed,failed);
    }
    private static void range(String field,BigDecimal value,BigDecimal min,BigDecimal max,List<Reason> passed,List<Reason> failed,List<Reason> unknown) {
        if (value==null) missing(unknown,field);
        else condition(field,value.compareTo(min)>=0 && value.compareTo(max)<=0,"Допустимый диапазон: "+min.toPlainString()+" … "+max.toPlainString(),passed,failed);
    }
    private static void minimum(String field,BigDecimal value,BigDecimal min,List<Reason> passed,List<Reason> failed,List<Reason> unknown) {
        if (value==null) missing(unknown,field);
        else condition(field,value.compareTo(min)>=0,"Минимальное значение: "+min.toPlainString(),passed,failed);
    }
    private static void booleanRule(JsonNode a,String section,String field,List<Reason> passed,List<Reason> failed,List<Reason> unknown) {
        var value=a.path(section).path(field);
        if (!value.isBoolean()) missing(unknown,section+"."+field);
        else condition(section+"."+field,value.asBoolean(),"Требуется подтверждение условия",passed,failed);
    }
}
