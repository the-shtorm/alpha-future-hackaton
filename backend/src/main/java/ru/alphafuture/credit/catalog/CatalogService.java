package ru.alphafuture.credit.catalog;

import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Service;
import ru.alphafuture.credit.api.ApiException;
import ru.alphafuture.credit.api.JsonSupport;

import java.math.BigDecimal;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

@Service
public class CatalogService {
    private final JdbcClient db;
    private final JsonSupport json;
    public CatalogService(JdbcClient db, JsonSupport json) { this.db = db; this.json = json; }
    private static final String CURRENT = """
        FROM credit.credit_product p
        JOIN LATERAL (
            SELECT * FROM credit.credit_product_version v WHERE v.product_id=p.id
            AND v.effective_from<=now() AND (v.effective_to IS NULL OR v.effective_to>now())
            ORDER BY v.effective_from DESC,v.id LIMIT 1
        ) v ON true WHERE p.active
        """;
    private Product map(ResultSet rs, int n) throws SQLException {
        return new Product(rs.getObject("product_id", UUID.class), rs.getObject("id", UUID.class),
            rs.getString("code"), rs.getString("name"), rs.getString("provider_code"), rs.getBoolean("is_synthetic"),
            rs.getString("version_code"),rs.getString("currency"),rs.getString("facility_kind"),
            rs.getBigDecimal("min_amount"),rs.getBigDecimal("max_amount"),rs.getInt("min_term_months"),
            rs.getInt("max_term_months"),rs.getBigDecimal("annual_rate_pct"),json.read(rs.getString("allowed_borrower_kinds")),
            json.read(rs.getString("allowed_purposes")),json.read(rs.getString("policy")));
    }
    public record Page(List<ProductCard> content, int page, int size, long totalElements, long totalPages) {}
    public Page page(int page, int size, String sort, String purpose, BigDecimal amount,
                     Integer term, String borrower, Boolean collateral) {
        if (page < 0 || size < 1 || size > 50) throw ApiException.invalid("page", "page >= 0, size от 1 до 50");
        if (amount != null && (amount.signum() <= 0 || amount.scale() > 2 || amount.precision()-amount.scale()>17))
            throw ApiException.invalid("amount", "Укажите положительную сумму, до двух знаков после точки");
        if (term != null && term < 1) throw ApiException.invalid("termMonths", "Срок должен быть положительным");
        String[] order = sort.split(",", -1);
        Map<String,String> columns = Map.of("name", "p.name", "minAmount", "v.min_amount", "annualRatePct", "v.annual_rate_pct");
        if (order.length != 2 || !columns.containsKey(order[0]) || !List.of("asc","desc").contains(order[1]))
            throw ApiException.invalid("sort", "Допустимы name/minAmount/annualRatePct,asc/desc");
        StringBuilder where = new StringBuilder(CURRENT);
        Map<String,Object> params = new LinkedHashMap<>();
        if (purpose != null) { where.append(" AND v.allowed_purposes @> jsonb_build_array(CAST(:purpose AS text))"); params.put("purpose",purpose); }
        if (borrower != null) { where.append(" AND v.allowed_borrower_kinds @> jsonb_build_array(CAST(:borrower AS text))"); params.put("borrower",borrower); }
        if (amount != null) { where.append(" AND :amount BETWEEN v.min_amount AND v.max_amount"); params.put("amount",amount); }
        if (term != null) { where.append(" AND :term BETWEEN v.min_term_months AND v.max_term_months"); params.put("term",term); }
        if (collateral != null) { where.append(" AND (v.policy->'collateral'->>'required')::boolean=:collateral"); params.put("collateral",collateral); }
        long total = db.sql("SELECT count(*) " + where).params(params).query(Long.class).single();
        params.put("limit",size); params.put("offset",(long)page*size);
        List<Product> items = db.sql("SELECT p.code,p.name,p.provider_code,p.is_synthetic,v.* " + where
            + " ORDER BY " + columns.get(order[0]) + " " + order[1] + " NULLS LAST,p.id LIMIT :limit OFFSET :offset")
            .params(params).query(this::map).list();
        return new Page(items.stream().map(ProductCard::from).toList(),page,size,total,(total+size-1)/size);
    }
    public List<Product> current() {
        return db.sql("SELECT p.code,p.name,p.provider_code,p.is_synthetic,v.* " + CURRENT + " ORDER BY p.code,p.id")
            .query(this::map).list();
    }
    public Product detail(UUID id) { return current().stream().filter(p -> p.id().equals(id)).findFirst().orElseThrow(ApiException::notFound); }
    public Product version(UUID id) {
        return db.sql("""
            SELECT p.code,p.name,p.provider_code,p.is_synthetic,v.* FROM credit.credit_product p
            JOIN credit.credit_product_version v ON v.product_id=p.id WHERE v.id=:id
            """).param("id",id).query(this::map).optional().orElseThrow(ApiException::notFound);
    }
    public Product activeVersion(UUID id) { return current().stream().filter(p -> p.versionId().equals(id)).findFirst().orElseThrow(ApiException::notFound); }
}
