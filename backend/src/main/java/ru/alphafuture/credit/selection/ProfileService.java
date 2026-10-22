package ru.alphafuture.credit.selection;

import com.fasterxml.jackson.databind.JsonNode;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import ru.alphafuture.credit.api.ApiException;
import ru.alphafuture.credit.api.JsonSupport;
import ru.alphafuture.credit.catalog.CatalogService;
import ru.alphafuture.credit.security.Access;

import java.sql.Timestamp;
import java.time.Instant;
import java.util.*;

@Service
public class ProfileService {
    public static final String FORM="preliminary-v1";
    public static final String POLICY="catalog-rules-v1";
    private final JdbcClient db;
    private final JsonSupport json;
    private final Access access;
    private final AnswersValidator validator;
    private final CatalogService catalog;
    private final EligibilityService eligibility;
    public ProfileService(JdbcClient db, JsonSupport json, Access access, AnswersValidator validator, CatalogService catalog, EligibilityService eligibility) {
        this.db=db; this.json=json; this.access=access; this.validator=validator; this.catalog=catalog; this.eligibility=eligibility;
    }
    public record Profile(UUID id,String formVersion,JsonNode answers,JsonNode fieldSources,long rowVersion,UUID selectedProductVersionId,Instant expiresAt) {}
    @com.fasterxml.jackson.annotation.JsonInclude(com.fasterxml.jackson.annotation.JsonInclude.Include.NON_NULL)
    public record Created(Profile profile,String accessToken) {}
    @Transactional
    public Created create(JsonNode answers) {
        validator.validate(answers);
        UUID id=UUID.randomUUID(),user=access.userOrNull(); String token=user==null?json.token():null;
        var sources=sources(answers,json.read("{}"),json.read("{}"));
        db.sql("""
            INSERT INTO credit.preliminary_profile(id,created_by,anonymous_token_hash,form_version,answers,field_sources,expires_at)
            VALUES (:id,:user,:hash,:form,CAST(:answers AS jsonb),CAST(:sources AS jsonb),now()+interval '7 days')
            """).param("id",id).param("user",user).param("hash",token==null?null:JsonSupport.hash(token))
            .param("form",FORM).param("answers",json.write(answers)).param("sources",json.write(sources)).update();
        return new Created(get(id,token,false),token);
    }
    public Profile get(UUID id,String token,boolean lock) {
        var row=db.sql("SELECT * FROM credit.preliminary_profile WHERE id=:id AND expires_at>now()"+(lock?" FOR UPDATE":""))
            .param("id",id).query(new org.springframework.jdbc.core.ColumnMapRowMapper()).optional().orElseThrow(ApiException::notFound);
        UUID owner=(UUID)row.get("created_by");
        boolean allowed=owner!=null?owner.equals(access.userOrNull()):token!=null && token.length()<=100
            && java.security.MessageDigest.isEqual(JsonSupport.hash(token).getBytes(java.nio.charset.StandardCharsets.US_ASCII),
                row.get("anonymous_token_hash").toString().getBytes(java.nio.charset.StandardCharsets.US_ASCII));
        if (!allowed) throw ApiException.notFound();
        return new Profile(id,row.get("form_version").toString(),json.read(row.get("answers").toString()),
            json.read(row.get("field_sources").toString()),((Number)row.get("row_version")).longValue(),
            (UUID)row.get("selected_product_version_id"),((Timestamp)row.get("expires_at")).toInstant());
    }
    @Transactional
    public Profile patch(UUID id,String token,long expected,JsonNode patch) {
        var old=get(id,token,true);
        if (old.rowVersion()!=expected) throw ApiException.conflict();
        if (patch==null || !patch.isObject()) throw ApiException.invalid("answers","Ожидается JSON-объект");
        var merged=json.merge(old.answers(),patch); validator.validate(merged);
        var sources=sources(merged,old.answers(),old.fieldSources());
        db.sql("""
            UPDATE credit.preliminary_profile SET answers=CAST(:answers AS jsonb),field_sources=CAST(:sources AS jsonb),
            row_version=row_version+1,selected_product_version_id=NULL WHERE id=:id
            """).param("answers",json.write(merged)).param("sources",json.write(sources)).param("id",id).update();
        return get(id,token,false);
    }
    private JsonNode sources(JsonNode answers,JsonNode oldAnswers,JsonNode oldSources) {
        var result=json.tree(new LinkedHashMap<String,Object>());
        answers.fields().forEachRemaining(section -> section.getValue().fields().forEachRemaining(field -> {
            if (field.getValue().isNull()) return;
            String key=section.getKey()+"."+field.getKey();
            var original=oldAnswers.path(section.getKey()).path(field.getKey());
            JsonNode value=field.getValue().equals(original) && oldSources.has(key)?oldSources.get(key):json.tree(Map.of(
                "kind","APPLICANT","source_code","MANUAL","observed_at",Instant.now().toString(),"verification_status","DECLARED","confirmed_by_user",true));
            ((com.fasterxml.jackson.databind.node.ObjectNode)result).set(key,value);
        }));
        return result;
    }
    public record Evaluation(UUID runId,long profileVersion,String policyVersion,List<EligibilityService.Result> items,String disclaimer) {}
    @Transactional
    public Evaluation evaluate(UUID id,String token) {
        var profile=get(id,token,true);
        UUID run=UUID.randomUUID(); var products=catalog.current();
        var results=products.stream().map(p -> eligibility.evaluate(p,profile.answers())).toList();
        db.sql("""
            INSERT INTO credit.recommendation_run(id,profile_id,profile_snapshot,model_version,policy_version)
            VALUES (:id,:profile,CAST(:snapshot AS jsonb),'eligibility-only-no-scoring-v1',:policy)
            """).param("id",run).param("profile",id).param("snapshot",json.write(profile)).param("policy",POLICY).update();
        for(int i=0;i<results.size();i++) {
            var result=results.get(i);
            db.sql("""
                INSERT INTO credit.recommendation_item(run_id,product_version_id,rank,eligibility,explanation)
                VALUES (:run,:product,:rank,:eligibility,CAST(:explanation AS jsonb))
                """).param("run",run).param("product",result.productVersionId()).param("rank",i+1)
                .param("eligibility",result.eligibility()).param("explanation",json.write(result)).update();
        }
        return new Evaluation(run,profile.rowVersion(),POLICY,results,"Предварительный подбор не означает одобрение кредита");
    }
    @Transactional
    public Profile select(UUID id,String token,long expected,UUID productId) {
        var profile=get(id,token,true);
        if (profile.rowVersion()!=expected) throw ApiException.conflict();
        var result=eligibility.evaluate(catalog.activeVersion(productId),profile.answers());
        if (result.eligibility().equals("INELIGIBLE")) throw new ApiException(422,"PRODUCT_INELIGIBLE","Профиль не соответствует условиям продукта");
        db.sql("UPDATE credit.preliminary_profile SET selected_product_version_id=:product,row_version=row_version+1 WHERE id=:id")
            .param("product",productId).param("id",id).update();
        return get(id,token,false);
    }
}
