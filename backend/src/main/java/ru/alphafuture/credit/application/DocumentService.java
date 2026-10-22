package ru.alphafuture.credit.application;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.web.multipart.MultipartFile;
import ru.alphafuture.credit.api.ApiException;
import ru.alphafuture.credit.api.JsonSupport;
import ru.alphafuture.credit.security.Access;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Map;
import java.util.UUID;

@Service
public class DocumentService {
    private final ApplicationService applications;
    private final JdbcClient db;
    private final Access access;
    private final Path root;
    public DocumentService(ApplicationService applications,JdbcClient db,Access access,@Value("${cabinet.documents-path}") String root) {
        this.applications=applications;this.db=db;this.access=access;this.root=Path.of(root).toAbsolutePath().normalize();
    }
    @Transactional
    public Map<String,Object> upload(UUID appId,UUID requirementId,MultipartFile file) throws IOException {
        var app=applications.get(appId,true,false,true);applications.editable(app);
        if (file.isEmpty() || file.getSize()>10*1024*1024) throw new ApiException(413,"INVALID_FILE_SIZE","Нужен непустой файл размером до 10 MB");
        var requirement=db.sql("SELECT * FROM credit.application_document_requirement WHERE id=:id AND application_id=:app AND status<>'NOT_APPLICABLE'")
            .param("id",requirementId).param("app",appId).query(new org.springframework.jdbc.core.ColumnMapRowMapper()).optional().orElseThrow(ApiException::notFound);
        byte[] data=file.getBytes();String media=detect(data);
        if (media==null) throw new ApiException(400,"UNSUPPORTED_FILE","Поддерживаются PDF, PNG и JPEG с соответствующей сигнатурой");
        var previous=db.sql("""
            SELECT id FROM credit.document WHERE application_id=:app AND subject_party_id=:party AND type_code=:type
            ORDER BY created_at DESC,id LIMIT 1
            """).param("app",appId).param("party",requirement.get("subject_party_id"))
            .param("type",requirement.get("type_code")).query(UUID.class).optional();
        UUID document=previous.orElseGet(UUID::randomUUID),version=UUID.randomUUID();String key=version.toString();
        int versionNo=db.sql("SELECT coalesce(max(version_no),0)+1 FROM credit.document_version WHERE document_id=:id")
            .param("id",document).query(Integer.class).single();
        String name=file.getOriginalFilename()==null?"document":file.getOriginalFilename().replaceAll("[\\p{Cntrl}/\\\\]","_");
        if (name.length()>200) name=name.substring(name.length()-200);
        Files.createDirectories(root);Path path=root.resolve(key);
        Files.write(path,data,StandardOpenOption.CREATE_NEW);
        TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
            @Override public void afterCompletion(int status) {
                if (status!=STATUS_COMMITTED) try { Files.deleteIfExists(path); } catch(IOException ex) {
                    org.slf4j.LoggerFactory.getLogger(DocumentService.class).error("Document rollback cleanup failed for {}",version);
                }
            }
        });
        if (previous.isEmpty()) db.sql("""
            INSERT INTO credit.document(id,application_id,subject_party_id,type_code,title,created_by)
            VALUES (:id,:app,:party,:type,:title,:user)
            """).param("id",document).param("app",appId).param("party",requirement.get("subject_party_id"))
            .param("type",requirement.get("type_code")).param("title",name).param("user",access.user()).update();
        db.sql("""
            INSERT INTO credit.document_version(id,document_id,application_id,subject_party_id,type_code,version_no,storage_key,
                original_filename,media_type,size_bytes,sha256,uploaded_by)
            VALUES (:id,:document,:app,:party,:type,:version,:key,:name,:media,:size,:hash,:user)
            """).param("id",version).param("document",document).param("app",appId).param("party",requirement.get("subject_party_id"))
            .param("type",requirement.get("type_code")).param("key",key).param("name",name).param("media",media)
            .param("size",data.length).param("version",versionNo).param("hash",JsonSupport.hash(data)).param("user",access.user()).update();
        db.sql("""
            INSERT INTO credit.requirement_document(requirement_id,document_version_id,application_id,subject_party_id,type_code)
            VALUES (:requirement,:version,:app,:party,:type)
            """).param("requirement",requirementId).param("version",version).param("app",appId)
            .param("party",requirement.get("subject_party_id")).param("type",requirement.get("type_code")).update();
        db.sql("UPDATE credit.application_document_requirement SET status='RECEIVED',row_version=row_version+1 WHERE id=:id")
            .param("id",requirementId).update();
        db.sql("""
            INSERT INTO credit.document_review(document_version_id,review_kind,result,engine_version,details)
            VALUES (:id,'FORMAT','PASS','magic-bytes-v1','{"scope":"signature_only"}'),
                   (:id,'ANTIVIRUS','UNKNOWN','not-configured','{"code":"SCANNER_NOT_CONFIGURED"}')
            """).param("id",version).update();
        db.sql("UPDATE credit.loan_application SET row_version=row_version+1 WHERE id=:id").param("id",appId).update();
        return Map.of("documentId",document,"versionId",version,"requirementId",requirementId,"status","RECEIVED","antivirus","UNKNOWN","sha256",JsonSupport.hash(data));
    }
    public ResponseEntity<ByteArrayResource> download(UUID appId,UUID version) throws IOException {
        applications.get(appId,false,false,false);
        var row=db.sql("SELECT storage_key,original_filename,media_type,size_bytes,sha256 FROM credit.document_version WHERE application_id=:app AND id=:id")
            .param("app",appId).param("id",version).query(new org.springframework.jdbc.core.ColumnMapRowMapper()).optional().orElseThrow(ApiException::notFound);
        Path path=root.resolve(row.get("storage_key").toString()).normalize();
        if (!path.startsWith(root) || !Files.isRegularFile(path)) throw ApiException.notFound();
        byte[] data=Files.readAllBytes(path);
        if (!JsonSupport.hash(data).equals(row.get("sha256"))) throw new ApiException(409,"DOCUMENT_INTEGRITY","Нарушена целостность файла");
        return ResponseEntity.ok().contentType(MediaType.parseMediaType(row.get("media_type").toString()))
            .header(HttpHeaders.CONTENT_DISPOSITION,ContentDisposition.attachment().filename(row.get("original_filename").toString(),StandardCharsets.UTF_8).build().toString())
            .header(HttpHeaders.CACHE_CONTROL,"no-store").header("X-Content-Type-Options","nosniff")
            .contentLength(data.length).body(new ByteArrayResource(data));
    }
    private static String detect(byte[] b) {
        if (b.length>=8 && b[0]=='%' && b[1]=='P' && b[2]=='D' && b[3]=='F' && b[4]=='-') return "application/pdf";
        byte[] png={(byte)137,80,78,71,13,10,26,10};
        if (b.length>=png.length && java.util.Arrays.equals(java.util.Arrays.copyOf(b,8),png)) return "image/png";
        if (b.length>=3 && (b[0]&255)==255 && (b[1]&255)==216 && (b[2]&255)==255) return "image/jpeg";
        return null;
    }
}
