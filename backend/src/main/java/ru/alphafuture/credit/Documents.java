package ru.alphafuture.credit;

import java.io.IOException;
import java.nio.file.*;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.*;
import org.springframework.web.multipart.MultipartFile;

/** Закрытое файловое хранилище и явная ручная проверка документов банком. */
@Service
class Documents {
    private final JdbcClient db;
    private final Path root;
    private final Access access;
    private final Json json;

    Documents(
            JdbcClient db,
            Access access,
            Json json,
            @Value("${cabinet.documents-path}") String root) {
        this.db = db;
        this.access = access;
        this.json = json;
        this.root = Path.of(root).toAbsolutePath().normalize();
    }

    Map<String, Object> upload(ApplicationService.Draft app, String type, MultipartFile file) {
        if (type.equals("CREDIT_CONTRACT")
                || !db.sql("SELECT EXISTS(SELECT 1 FROM credit.document_type WHERE code=:type)")
                        .param("type", type)
                        .query(Boolean.class)
                        .single())
            throw ApiFailure.invalid("typeCode", "Недоступный тип документа");
        byte[] data;
        try {
            data = file.getBytes();
        } catch (IOException ex) {
            throw new IllegalStateException(ex);
        }
        if (data.length == 0 || data.length > 10 * 1024 * 1024)
            throw new ApiFailure(413, "FILE_TOO_LARGE", "Нужен непустой файл не больше 10 MB");
        String media = detect(data);
        UUID document = UUID.randomUUID(), version = UUID.randomUUID();
        store(version, data);
        String filename =
                Optional.ofNullable(file.getOriginalFilename())
                        .orElse("document")
                        .replaceAll("[^a-zA-Zа-яА-ЯёЁ0-9._ -]", "_");
        if (filename.length() > 200) filename = filename.substring(filename.length() - 200);
        db.sql(
                        "INSERT INTO credit.document(id,application_id,subject_party_id,type_code,title,created_by) VALUES (:id,:app,:party,:type,:title,:user)")
                .param("id", document)
                .param("app", app.id())
                .param("party", app.partyId())
                .param("type", type)
                .param("title", filename)
                .param("user", access.user())
                .update();
        insertVersion(version, document, app, type, filename, media, data);
        return Map.of(
                "versionId",
                version,
                "typeCode",
                type,
                "sha256",
                Json.hash(data),
                "value_status",
                "UNKNOWN");
    }

    private String detect(byte[] data) {
        if (data.length >= 5
                && new String(data, 0, 5, java.nio.charset.StandardCharsets.US_ASCII)
                        .equals("%PDF-")) return "application/pdf";
        if (data.length >= 8
                && Arrays.equals(
                        Arrays.copyOf(data, 8),
                        new byte[] {(byte) 137, 80, 78, 71, 13, 10, 26, 10})) return "image/png";
        if (data.length >= 3
                && data[0] == (byte) 255
                && data[1] == (byte) 216
                && data[2] == (byte) 255) return "image/jpeg";
        throw ApiFailure.invalid("file", "Допустимы PDF, PNG и JPEG с соответствующей сигнатурой");
    }

    private void store(UUID version, byte[] bytes) {
        Path target = root.resolve(version.toString());
        try {
            Files.createDirectories(root);
            Files.write(target, bytes, StandardOpenOption.CREATE_NEW);
        } catch (IOException ex) {
            throw new IllegalStateException("Document storage unavailable", ex);
        }
        TransactionSynchronizationManager.registerSynchronization(
                new TransactionSynchronization() {
                    @Override
                    public void afterCompletion(int status) {
                        if (status != STATUS_COMMITTED)
                            try {
                                Files.deleteIfExists(target);
                            } catch (IOException ignored) {
                            }
                    }
                });
    }

    private void insertVersion(
            UUID version,
            UUID document,
            ApplicationService.Draft app,
            String type,
            String filename,
            String media,
            byte[] bytes) {
        db.sql(
                        "INSERT INTO credit.document_version(id,document_id,application_id,subject_party_id,type_code,version_no,storage_key,original_filename,media_type,size_bytes,sha256,uploaded_by) VALUES (:id,:doc,:app,:party,:type,1,:storage,:name,:media,:size,:hash,:user)")
                .param("id", version)
                .param("doc", document)
                .param("app", app.id())
                .param("party", app.partyId())
                .param("type", type)
                .param("storage", version.toString())
                .param("name", filename)
                .param("media", media)
                .param("size", bytes.length)
                .param("hash", Json.hash(bytes))
                .param("user", access.user())
                .update();
        for (var row :
                db.sql(
                                "SELECT id FROM credit.application_document_requirement WHERE application_id=:app AND type_code=:type AND status<>'NOT_APPLICABLE'")
                        .param("app", app.id())
                        .param("type", type)
                        .query()
                        .listOfRows()) {
            db.sql(
                            "INSERT INTO credit.requirement_document(requirement_id,document_version_id,application_id,subject_party_id,type_code) VALUES (:requirement,:version,:app,:party,:type)")
                    .param("requirement", row.get("id"))
                    .param("version", version)
                    .param("app", app.id())
                    .param("party", app.partyId())
                    .param("type", type)
                    .update();
            db.sql(
                            "UPDATE credit.application_document_requirement SET status='RECEIVED',row_version=row_version+1 WHERE id=:id")
                    .param("id", row.get("id"))
                    .update();
        }
    }

    Map<String, Object> metadata(UUID app, UUID version) {
        return db
                .sql(
                        "SELECT id,type_code,original_filename,media_type,size_bytes,sha256,storage_key FROM credit.document_version WHERE application_id=:app AND id=:version")
                .param("app", app)
                .param("version", version)
                .query()
                .listOfRows()
                .stream()
                .findFirst()
                .orElseThrow(ApiFailure::missing);
    }

    byte[] read(UUID app, UUID version) {
        var row = metadata(app, version);
        Path path = root.resolve(row.get("storage_key").toString()).normalize();
        if (!path.startsWith(root) || !path.equals(root.resolve(version.toString())))
            throw ApiFailure.missing();
        try {
            byte[] data = Files.readAllBytes(path);
            if (!Json.hash(data).equals(row.get("sha256")))
                throw new IllegalStateException("Stored document checksum mismatch");
            return data;
        } catch (IOException ex) {
            throw new ApiFailure(503, "STORAGE_UNAVAILABLE", "Документ временно недоступен");
        }
    }

    void review(UUID app, UUID version, String result, String reason) {
        metadata(app, version);
        if (!Set.of("PASS", "FAIL", "UNKNOWN").contains(result))
            throw ApiFailure.invalid("result", "Допустимы PASS, FAIL, UNKNOWN");
        db.sql(
                        "INSERT INTO credit.document_review(document_version_id,review_kind,result,reviewer_id,details) VALUES (:version,'CONTENT',:result,:user,CAST(:details AS jsonb))")
                .param("version", version)
                .param("result", result)
                .param("user", access.user())
                .param("details", json.write(Map.of("reason", reason, "source", "BANK_APPROVER")))
                .update();
        db.sql(
                        "UPDATE credit.application_document_requirement r SET status=:status,row_version=row_version+1 WHERE r.application_id=:app AND EXISTS(SELECT 1 FROM credit.requirement_document rd WHERE rd.requirement_id=r.id AND rd.document_version_id=:version)")
                .param(
                        "status",
                        result.equals("PASS")
                                ? "VERIFIED"
                                : result.equals("FAIL") ? "NEEDS_CORRECTION" : "VERIFYING")
                .param("app", app)
                .param("version", version)
                .update();
    }

    List<String> missing(UUID app, UUID revision) {
        var result = new ArrayList<String>();
        for (var row :
                db.sql(
                                "SELECT r.requirement_key FROM credit.application_document_requirement r WHERE r.application_id=:app AND r.required_before IN ('SUBMISSION','DECISION') AND r.status NOT IN ('VERIFIED','WAIVED','NOT_APPLICABLE')")
                        .param("app", app)
                        .query()
                        .listOfRows()) result.add("documents." + row.get("requirement_key"));
        for (var row :
                db.sql(
                                "SELECT rd.document_version_id FROM credit.revision_document rd LEFT JOIN LATERAL (SELECT result FROM credit.document_review WHERE document_version_id=rd.document_version_id AND review_kind='CONTENT' ORDER BY review_number DESC LIMIT 1) review ON true WHERE rd.application_id=:app AND rd.revision_id=:revision AND review.result IS DISTINCT FROM 'PASS'")
                        .param("app", app)
                        .param("revision", revision)
                        .query()
                        .listOfRows()) result.add("documents." + row.get("document_version_id"));
        return result;
    }

    UUID contract(ApplicationService.Draft app, UUID offer) {
        UUID document = UUID.randomUUID(), version = UUID.randomUUID();
        byte[] data =
                json.write(
                                Map.of(
                                        "applicationId",
                                        app.id(),
                                        "offerId",
                                        offer,
                                        "confirmedBy",
                                        access.user(),
                                        "isSimulated",
                                        true))
                        .getBytes(java.nio.charset.StandardCharsets.UTF_8);
        store(version, data);
        db.sql(
                        "INSERT INTO credit.document(id,application_id,subject_party_id,type_code,title,created_by) VALUES (:id,:app,:party,'CREDIT_CONTRACT','Условный договор',:user)")
                .param("id", document)
                .param("app", app.id())
                .param("party", app.partyId())
                .param("user", access.user())
                .update();
        insertVersion(
                version,
                document,
                app,
                "CREDIT_CONTRACT",
                "contract.json",
                "application/json",
                data);
        return version;
    }
}
