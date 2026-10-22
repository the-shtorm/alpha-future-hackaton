package ru.alphafuture.credit.application;

import com.fasterxml.jackson.databind.JsonNode;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import ru.alphafuture.credit.api.ApiException;
import ru.alphafuture.credit.api.JsonSupport;
import ru.alphafuture.credit.catalog.CatalogService;
import ru.alphafuture.credit.catalog.Product;
import ru.alphafuture.credit.security.Access;
import ru.alphafuture.credit.selection.*;

import java.math.BigDecimal;
import java.util.*;

import static ru.alphafuture.credit.selection.AnswersValidator.text;

@Service
public class ApplicationService {
    public static final String FORM="application-v1", POLICY="demo-requirements-v1";
    private final JdbcClient db;
    private final Access access;
    private final JsonSupport json;
    private final ProfileService profiles;
    private final AnswersValidator validator;
    private final CatalogService catalog;
    private final EligibilityService eligibility;
    public ApplicationService(JdbcClient db,Access access,JsonSupport json,ProfileService profiles,AnswersValidator validator,
                              CatalogService catalog,EligibilityService eligibility) {
        this.db=db; this.access=access; this.json=json; this.profiles=profiles; this.validator=validator; this.catalog=catalog; this.eligibility=eligibility;
    }
    public record Application(UUID id,long applicationNumber,UUID partyId,UUID profileId,UUID productVersionId,
        String status,String formVersion,JsonNode answers,JsonNode fieldSources,long rowVersion,UUID activeRevisionId) {}
    public Application get(UUID id,boolean write,boolean owner,boolean lock) {
        // Authorize in the query as well: inaccessible objects are not locked or returned.
        var app=db.sql("""
            SELECT a.* FROM credit.loan_application a WHERE a.id=:id AND EXISTS (
              SELECT 1 FROM credit.party_membership m WHERE m.party_id=a.applicant_party_id
              AND m.user_id=:user AND m.revoked_at IS NULL)
            """+(lock?" FOR UPDATE OF a":"")).param("id",id).param("user",access.user())
            .query((rs,n)->new Application(rs.getObject("id",UUID.class),rs.getLong("application_number"),
                rs.getObject("applicant_party_id",UUID.class),rs.getObject("preliminary_profile_id",UUID.class),
                rs.getObject("product_version_id",UUID.class),rs.getString("status"),rs.getString("form_version"),
                json.read(rs.getString("draft_answers")),json.read(rs.getString("draft_field_sources")),
                rs.getLong("row_version"),rs.getObject("active_revision_id",UUID.class))).optional().orElseThrow(ApiException::notFound);
        access.membership(app.partyId(),write,owner);
        return app;
    }
    @Transactional
    public Application create(UUID profileId,String profileToken,UUID partyId) {
        access.membership(partyId,true,false);
        var profile=profiles.get(profileId,profileToken,true);
        if (profile.selectedProductVersionId()==null) throw new ApiException(422,"PRODUCT_REQUIRED","Выберите продукт в профиле");
        var product=catalog.activeVersion(profile.selectedProductVersionId());
        validateRequest(profile.answers());
        validateParty(partyId,profile.answers());
        UUID id=UUID.randomUUID();
        db.sql("""
            INSERT INTO credit.loan_application(id,applicant_party_id,created_by,preliminary_profile_id,product_version_id,
                requested_amount,requested_term_months,currency,purpose,form_version,draft_answers,draft_field_sources)
            VALUES (:id,:party,:user,:profile,:product,:amount,:term,:currency,:purpose,:form,CAST(:answers AS jsonb),CAST(:sources AS jsonb))
            """).param("id",id).param("party",partyId).param("user",access.user()).param("profile",profileId)
            .param("product",product.versionId()).param("amount",new BigDecimal(text(profile.answers(),"request","amount")))
            .param("term",Integer.parseInt(text(profile.answers(),"request","termMonths"))).param("currency",product.currency())
            .param("purpose",text(profile.answers(),"request","purpose")).param("form",FORM)
            .param("answers",json.write(profile.answers())).param("sources",json.write(profile.fieldSources())).update();
        requirementsFor(id,partyId,profile.answers(),product);
        return get(id,false,false,false);
    }
    public Map<String,Object> list(int page,int size) {
        if (page<0 || size<1 || size>50) throw ApiException.invalid("page","page >= 0, size от 1 до 50");
        String where="""
            FROM credit.loan_application a WHERE EXISTS (SELECT 1 FROM credit.party_membership m
            WHERE m.party_id=a.applicant_party_id AND m.user_id=:user AND m.revoked_at IS NULL)
            """;
        long count=db.sql("SELECT count(*) "+where).param("user",access.user()).query(Long.class).single();
        var items=db.sql("SELECT a.id,a.application_number,a.applicant_party_id,a.status,a.requested_amount::text AS requested_amount,a.created_at,a.row_version "+where
            +" ORDER BY a.created_at DESC,a.id LIMIT :size OFFSET :offset").param("user",access.user()).param("size",size).param("offset",(long)page*size).query().listOfRows();
        return Map.of("content",items,"page",page,"size",size,"totalElements",count,"totalPages",(count+size-1)/size);
    }
    @Transactional
    public Application patch(UUID id,long expected,JsonNode patch) {
        var app=get(id,true,false,true); editable(app);
        if (app.rowVersion()!=expected) throw ApiException.conflict();
        if (patch==null || !patch.isObject()) throw ApiException.invalid("answers","Ожидается JSON-объект");
        var answers=json.merge(app.answers(),patch); validator.validate(answers); validateRequest(answers); validateParty(app.partyId(),answers);
        // All changed answers are declarations, never promoted to registry verification.
        var sources=json.tree(new LinkedHashMap<String,Object>());
        answers.fields().forEachRemaining(s -> s.getValue().fields().forEachRemaining(f -> {
            if (f.getValue().isNull()) return;
            String key=s.getKey()+"."+f.getKey();
            JsonNode source=f.getValue().equals(app.answers().path(s.getKey()).path(f.getKey())) && app.fieldSources().has(key)
                ?app.fieldSources().get(key):json.tree(Map.of("kind","APPLICANT","source_code","MANUAL","verification_status","DECLARED","observed_at",java.time.Instant.now().toString()));
            ((com.fasterxml.jackson.databind.node.ObjectNode)sources).set(key,source);
        }));
        db.sql("""
            UPDATE credit.loan_application SET draft_answers=CAST(:answers AS jsonb),draft_field_sources=CAST(:sources AS jsonb),
            requested_amount=:amount,requested_term_months=:term,purpose=:purpose,row_version=row_version+1 WHERE id=:id
            """).param("answers",json.write(answers)).param("sources",json.write(sources)).param("amount",new BigDecimal(text(answers,"request","amount")))
            .param("term",Integer.parseInt(text(answers,"request","termMonths"))).param("purpose",text(answers,"request","purpose")).param("id",id).update();
        requirementsFor(id,app.partyId(),answers,catalog.version(app.productVersionId()));
        return get(id,false,false,false);
    }
    private void validateRequest(JsonNode a) {
        for(String field:List.of("purpose","amount","termMonths"))
            if (text(a,"request",field)==null) throw ApiException.invalid("request."+field,"Обязательное поле для черновика заявки");
    }
    private void validateParty(UUID id,JsonNode a) {
        var p=db.sql("SELECT tax_id,party_kind FROM credit.party WHERE id=:id").param("id",id).query().singleRow();
        if (!Objects.equals(p.get("tax_id"),text(a,"registration","taxId")) || !Objects.equals(p.get("party_kind"),text(a,"registration","borrowerKind")))
            throw ApiException.invalid("registration.taxId","ИНН и форма бизнеса должны соответствовать организации кабинета");
    }
    public void editable(Application app) {
        if (!Set.of("DRAFT","NEEDS_INFO").contains(app.status())) throw new ApiException(409,"APPLICATION_SEALED","Поданная версия закрыта для изменения");
    }
    private record Requirement(String type,String gate,String reason) {}
    private void requirementsFor(UUID id,UUID party,JsonNode answers,Product product) {
        var rules=new LinkedHashMap<String,Requirement>();
        rules.put("registry",new Requirement("REGISTRY_EXTRACT","SUBMISSION","Сведения о регистрации заемщика"));
        rules.put("bank",new Requirement("BANK_STATEMENT","SUBMISSION","Выписки по счетам"));
        String regime=text(answers,"business","taxRegime"),kind=text(answers,"registration","borrowerKind");
        if ("LLC".equals(kind)) {
            rules.put("charter",new Requirement("CHARTER","DECISION","Сведения об уставе"));
            rules.put("director",new Requirement("DIRECTOR_APPOINTMENT","SUBMISSION","Подтверждение назначения руководителя"));
        }
        if ("OSNO".equals(regime) && "LLC".equals(kind)) {
            rules.put("balance",new Requirement("BALANCE_SHEET","SUBMISSION","Бухгалтерская отчетность"));
            rules.put("income",new Requirement("INCOME_STATEMENT","SUBMISSION","Финансовые результаты"));
        } else if (Set.of("OSNO","USN","COMBINED").contains(regime==null?"":regime))
            rules.put("tax",new Requirement("TAX_RETURN","SUBMISSION","Декларация по применимому режиму"));
        else if ("PSN".equals(regime)) rules.put("patent",new Requirement("TAX_PATENT","SUBMISSION","Сведения о патенте"));
        else rules.put("income-record",new Requirement("INCOME_RECORD","SUBMISSION","Учет доходов за отчетный период"));
        if (product.policy().path("collateral").path("required").asBoolean()) {
            rules.put("title",new Requirement("TITLE","DECISION","Документы по обеспечению"));
            rules.put("valuation",new Requirement("VALUATION","DECISION","Оценка обеспечения"));
            rules.put("pledge",new Requirement("PLEDGE_CONTRACT","SIGNING","Договор залога"));
        }
        for (var trigger:product.policy().path("additional_document_triggers")) {
            String type=switch(trigger.asText()) {
                case "BUSINESS_PLAN","SEASONAL_CASHFLOW" -> "BUSINESS_PLAN";
                case "PURCHASE_DOCUMENTS","SUPPLIER_DOCUMENTS" -> "INVOICE";
                case "CONFIRMED_CONTRACT" -> "PURPOSE_CONTRACT";
                case "EXISTING_LOAN" -> "DEBT_AGREEMENT";
                default -> null;
            };
            if (type!=null) rules.put(trigger.asText(),new Requirement(type,"DECISION","Условие продукта: "+trigger.asText()));
        }
        db.sql("UPDATE credit.application_document_requirement SET status='NOT_APPLICABLE',row_version=row_version+1 WHERE application_id=:id AND requirement_key NOT IN (:keys)")
            .param("id",id).param("keys",rules.keySet()).update();
        rules.forEach((key,r)-> db.sql("""
            INSERT INTO credit.application_document_requirement(application_id,subject_party_id,type_code,requirement_key,basis,reason,policy_version,required_before)
            VALUES (:id,:party,:type,:key,'DEMO',:reason,:policy,:gate)
            ON CONFLICT (application_id,requirement_key) DO UPDATE
            SET status=CASE WHEN application_document_requirement.status='NOT_APPLICABLE' THEN 'REQUIRED' ELSE application_document_requirement.status END,
                row_version=application_document_requirement.row_version+1
            """).param("id",id).param("party",party).param("type",r.type()).param("key",key).param("reason",r.reason()).param("policy",POLICY).param("gate",r.gate()).update());
    }
    public List<Map<String,Object>> requirements(UUID id) {
        get(id,false,false,false);
        return db.sql("""
            SELECT r.id,r.subject_party_id,r.type_code,t.name,r.requirement_key,r.basis,r.reason,r.required_before,r.status
            FROM credit.application_document_requirement r JOIN credit.document_type t ON t.code=r.type_code
            WHERE r.application_id=:id ORDER BY r.required_before,r.requirement_key
            """).param("id",id).query().listOfRows();
    }
    public record Validation(boolean valid,List<ApiException.Issue> errors) {}
    public Validation check(Application app,boolean content) {
        var errors=new ArrayList<ApiException.Issue>(); JsonNode a=app.answers();
        for(var field:List.of("registration.taxId","registration.name","business.taxRegime","business.region","business.sector","financial.revenue","financial.periodFrom","financial.periodTo","project.repaymentSource")) {
            String[] parts=field.split("\\.");
            if (text(a,parts[0],parts[1])==null || "UNKNOWN".equals(text(a,parts[0],parts[1])))
                errors.add(new ApiException.Issue(field,"REQUIRED","Заполните обязательное поле"));
        }
        var result=eligibility.evaluate(catalog.version(app.productVersionId()),a);
        for(var reason:result.failed()) errors.add(new ApiException.Issue(reason.field(),reason.code(),reason.message()));
        // Unknown declared terms must be resolved for submission; document-specific conditions are checked by requirements.
        for(var reason:result.unconfirmed()) if (reason.code().equals("MISSING"))
            errors.add(new ApiException.Issue(reason.field(),reason.code(),reason.message()));
        var missing=db.sql("""
            SELECT id,reason FROM credit.application_document_requirement WHERE application_id=:id AND required_before='SUBMISSION'
              AND status NOT IN ('RECEIVED','VERIFYING','VERIFIED','NOT_APPLICABLE','WAIVED')
            """).param("id",app.id()).query().listOfRows();
        missing.forEach(r->errors.add(new ApiException.Issue("documents."+r.get("id"),"DOCUMENT_REQUIRED",r.get("reason").toString())));
        if (content && app.activeRevisionId()!=null) {
            var unsafe=db.sql("""
                SELECT rd.document_version_id FROM credit.revision_document rd WHERE rd.revision_id=:revision AND NOT EXISTS (
                  SELECT 1 FROM credit.document_review r WHERE r.document_version_id=rd.document_version_id AND r.review_kind='ANTIVIRUS'
                  AND r.result='PASS' AND r.review_number=(SELECT max(r2.review_number) FROM credit.document_review r2
                    WHERE r2.document_version_id=rd.document_version_id AND r2.review_kind='ANTIVIRUS'))
                """).param("revision",app.activeRevisionId()).query(UUID.class).list();
            unsafe.forEach(v->errors.add(new ApiException.Issue("documents."+v,"SCAN_PENDING","Антивирусная проверка пока не завершена")));
        }
        return new Validation(errors.isEmpty(),errors);
    }
    @Transactional
    public Map<String,Object> validate(UUID id) {
        var app=get(id,true,false,true);
        if (Set.of("DRAFT","NEEDS_INFO").contains(app.status())) return Map.of("applicationId",id,"status",app.status(),"validation",check(app,false));
        if (!Set.of("SUBMITTED","VALIDATING").contains(app.status())) throw new ApiException(409,"INVALID_STATE","Проверка недоступна для текущего статуса");
        if (app.status().equals("SUBMITTED")) transition(app,"VALIDATING","Начата техническая проверка");
        var validation=check(app,true);
        db.sql("""
            INSERT INTO credit.check_run(application_id,revision_id,check_code,rule_version,result,is_legal_gate,input_sha256,evidence)
            SELECT :id,:revision,'TECHNICAL_COMPLETENESS',:policy,:result,false,snapshot_sha256,CAST(:evidence AS jsonb)
            FROM credit.application_revision WHERE id=:revision
            """).param("id",id).param("revision",app.activeRevisionId()).param("policy",POLICY)
            .param("result",validation.valid()?"PASS":"REVIEW").param("evidence",json.write(validation)).update();
        String status=validation.valid()?"ENRICHING":"NEEDS_INFO";
        transition(app,status,validation.valid()?"Техническая проверка завершена":"Нужны дополнительные сведения или проверка документов");
        return Map.of("applicationId",id,"status",status,"validation",validation);
    }
    private void transition(Application app,String status,String reason) {
        db.sql("UPDATE credit.loan_application SET status=:status,last_changed_by=:user,last_change_reason=:reason,row_version=row_version+1 WHERE id=:id")
            .param("status",status).param("user",access.user()).param("reason",reason).param("id",app.id()).update();
    }
    @Transactional
    public Map<String,Object> submit(UUID id,long expected,boolean confirmed,String key) {
        if (key==null || !key.matches("[A-Za-z0-9_.:-]{1,160}")) throw ApiException.invalid("Idempotency-Key","Нужен ключ длиной 1…160 символов");
        if (!confirmed) throw ApiException.invalid("confirmed","Подтвердите демонстрационную отправку");
        UUID user=access.user();
        db.sql("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))").param("key",user+"/"+key).query(rs->{rs.next();return true;});
        var app=get(id,true,true,true);
        var prior=db.sql("SELECT application_id,expected_version,revision_id FROM credit.api_submission WHERE user_id=:user AND idempotency_key=:key")
            .param("user",user).param("key",key).query(new org.springframework.jdbc.core.ColumnMapRowMapper()).optional();
        if (prior.isPresent()) {
            if (!prior.get().get("application_id").equals(id) || ((Number)prior.get().get("expected_version")).longValue()!=expected)
                throw new ApiException(409,"IDEMPOTENCY_CONFLICT","Ключ использован для другого запроса");
            return Map.of("applicationId",id,"revisionId",prior.get().get("revision_id"),"status","SUBMITTED");
        }
        editable(app); if (app.rowVersion()!=expected) throw ApiException.conflict();
        var validation=check(app,false);
        if (!validation.valid()) throw new ApiException(422,"SUBMISSION_INCOMPLETE","Приемный комплект не готов",validation.errors());
        var manifest=db.sql("""
            SELECT DISTINCT id,document_id,type_code,subject_party_id,sha256,size_bytes,period_from,period_to FROM (
              SELECT DISTINCT ON (rd.requirement_id) v.id,v.document_id,v.type_code,v.subject_party_id,v.sha256,v.size_bytes,v.period_from,v.period_to
              FROM credit.document_version v JOIN credit.requirement_document rd ON rd.document_version_id=v.id
              JOIN credit.application_document_requirement r ON r.id=rd.requirement_id
              WHERE v.application_id=:id AND r.status NOT IN ('NOT_APPLICABLE','WAIVED')
              ORDER BY rd.requirement_id,v.created_at DESC,v.version_no DESC,v.id
            ) latest ORDER BY id
            """).param("id",id).query().listOfRows();
        var snapshot=new LinkedHashMap<String,Object>();
        snapshot.put("schema_version","application-snapshot-v1"); snapshot.put("request",Map.of("product_version_id",app.productVersionId(),
            "amount",text(app.answers(),"request","amount"),"currency",catalog.version(app.productVersionId()).currency(),
            "term_months",Integer.parseInt(text(app.answers(),"request","termMonths")),"purpose",text(app.answers(),"request","purpose")));
        snapshot.put("answers",app.answers()); snapshot.put("field_sources",app.fieldSources());
        snapshot.put("parties",List.of(Map.of("id",app.partyId(),"role","BORROWER")));
        snapshot.put("financial_statements",List.of(app.answers().path("financial")));
        snapshot.put("document_manifest",manifest); snapshot.put("consent_ids",List.of()); snapshot.put("policy_version",POLICY);
        UUID revision=UUID.randomUUID(); String canonical=json.canonical(json.tree(snapshot));
        db.sql("""
            INSERT INTO credit.application_revision(id,application_id,revision_no,submitted_by,form_version,product_version_id,snapshot,snapshot_sha256,submission_evidence)
            SELECT :revision,:id,coalesce(max(revision_no),0)+1,:user,:form,:product,CAST(:snapshot AS jsonb),:hash,CAST(:evidence AS jsonb)
            FROM credit.application_revision WHERE application_id=:id
            """).param("revision",revision).param("id",id).param("user",user).param("form",FORM).param("product",app.productVersionId())
            .param("snapshot",canonical).param("hash",JsonSupport.hash(canonical))
            .param("evidence",json.write(Map.of("kind","DEMO_CONFIRMATION","is_simulated",true,"actor_id",user,"confirmed",true))).update();
        for(var document:manifest) db.sql("INSERT INTO credit.revision_document(application_id,revision_id,document_version_id) VALUES (:id,:rev,:doc)")
            .param("id",id).param("rev",revision).param("doc",document.get("id")).update();
        db.sql("""
            INSERT INTO credit.application_check_requirement(application_id,revision_id,check_code,rule_version,is_legal_gate,required_before,reason)
            VALUES (:id,:revision,'TECHNICAL_COMPLETENESS',:policy,false,'DECISION','Техническая комплектность и готовность документов')
            """).param("id",id).param("revision",revision).param("policy",POLICY).update();
        db.sql("""
            UPDATE credit.loan_application SET active_revision_id=:revision,status='SUBMITTED',last_changed_by=:user,
              last_change_reason='Демонстрационная отправка владельцем',row_version=row_version+1 WHERE id=:id
            """).param("revision",revision).param("user",user).param("id",id).update();
        db.sql("INSERT INTO credit.api_submission(user_id,idempotency_key,application_id,expected_version,revision_id) VALUES (:user,:key,:id,:version,:revision)")
            .param("user",user).param("key",key).param("id",id).param("version",expected).param("revision",revision).update();
        return Map.of("applicationId",id,"revisionId",revision,"status","SUBMITTED");
    }
    public List<Map<String,Object>> results(UUID id) {
        var app=get(id,false,false,false);
        if (app.activeRevisionId()==null) return List.of();
        return db.sql("SELECT id,revision_id,check_code,result,evidence,created_at FROM credit.check_run WHERE application_id=:id AND revision_id=:revision ORDER BY run_number")
            .param("id",id).param("revision",app.activeRevisionId()).query((rs,n)->{
                var row=new LinkedHashMap<String,Object>(); row.put("id",rs.getObject(1));row.put("revisionId",rs.getObject(2));row.put("checkCode",rs.getString(3));
                row.put("result",rs.getString(4));row.put("evidence",json.read(rs.getString(5)));row.put("createdAt",rs.getTimestamp(6).toInstant());return (Map<String,Object>)row;
            }).list();
    }
    public Map<String,Object> status(UUID id) {
        var app=get(id,false,false,false);
        return Map.of("applicationId",id,"status",app.status(),"rowVersion",app.rowVersion(),"history",db.sql("""
            SELECT from_status,to_status,reason,created_at FROM credit.application_status_history WHERE application_id=:id ORDER BY id
            """).param("id",id).query().listOfRows());
    }
}
