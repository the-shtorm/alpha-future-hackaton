package ru.alphafuture.credit.selection;

import com.fasterxml.jackson.databind.JsonNode;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import org.springframework.web.bind.annotation.*;
import org.springframework.http.HttpStatus;
import ru.alphafuture.credit.api.ApiException;

import java.time.Instant;
import java.util.Map;
import java.util.UUID;

@io.swagger.v3.oas.annotations.security.SecurityRequirements
@RestController
public class SelectionController {
    private final ProfileService profiles;
    public SelectionController(ProfileService profiles) { this.profiles=profiles; }
    public record Create(@NotNull JsonNode answers) {}
    public record Patch(@NotNull @PositiveOrZero Long expectedVersion,@NotNull JsonNode answers) {}
    public record Select(@NotNull @PositiveOrZero Long expectedVersion,@NotNull UUID productVersionId) {}
    public record Lookup(@NotBlank @Size(max=12) String taxId) {}
    @PostMapping("/selection-profiles") @ResponseStatus(HttpStatus.CREATED)
    public ProfileService.Created create(@Valid @RequestBody Create request) { return profiles.create(request.answers()); }
    @GetMapping("/selection-profiles/{id}")
    public ProfileService.Profile get(@PathVariable UUID id,@RequestHeader(value="X-Profile-Token",required=false) String token) { return profiles.get(id,token,false); }
    @PatchMapping("/selection-profiles/{id}")
    public ProfileService.Profile patch(@PathVariable UUID id,@RequestHeader(value="X-Profile-Token",required=false) String token,@Valid @RequestBody Patch request) {
        return profiles.patch(id,token,request.expectedVersion(),request.answers());
    }
    @PostMapping("/selection-profiles/{id}/eligibility")
    public ProfileService.Evaluation eligibility(@PathVariable UUID id,@RequestHeader(value="X-Profile-Token",required=false) String token) { return profiles.evaluate(id,token); }
    @PutMapping("/selection-profiles/{id}/selected-product")
    public ProfileService.Profile select(@PathVariable UUID id,@RequestHeader(value="X-Profile-Token",required=false) String token,@Valid @RequestBody Select request) {
        return profiles.select(id,token,request.expectedVersion(),request.productVersionId());
    }
    @PostMapping("/business/lookup")
    public Map<String,Object> lookup(@Valid @RequestBody Lookup request) {
        if (!TaxId.valid(request.taxId())) throw ApiException.invalid("taxId","Неверные контрольные разряды ИНН");
        // A fixed local fixture: an arbitrary valid tax ID is never presented as a registry hit.
        boolean found=request.taxId().equals("7707083893");
        return Map.of("status",found?"FOUND":"NOT_FOUND","isSimulated",true,"sourceCode","FNS_REGISTRY_MOCK",
            "verificationStatus","SIMULATED","observedAt",Instant.now(),"data",found?Map.of(
                "taxId",request.taxId(),"name","ООО Демонстрационная компания","borrowerKind","LLC","registeredOn","2020-01-01","country","RU"):Map.of());
    }
}
