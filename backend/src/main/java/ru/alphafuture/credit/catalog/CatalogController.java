package ru.alphafuture.credit.catalog;

import org.springframework.web.bind.annotation.*;
import java.math.BigDecimal;
import java.util.UUID;

@io.swagger.v3.oas.annotations.security.SecurityRequirements
@RestController
@RequestMapping("/products")
public class CatalogController {
    private final CatalogService catalog;
    public CatalogController(CatalogService catalog) { this.catalog = catalog; }
    @GetMapping
    public CatalogService.Page list(@RequestParam(defaultValue="0") int page, @RequestParam(defaultValue="12") int size,
        @RequestParam(defaultValue="name,asc") String sort, @RequestParam(required=false) String purpose,
        @RequestParam(required=false) BigDecimal amount, @RequestParam(required=false) Integer termMonths,
        @RequestParam(required=false) String borrowerKind, @RequestParam(required=false) Boolean collateralRequired) {
        return catalog.page(page,size,sort,purpose,amount,termMonths,borrowerKind,collateralRequired);
    }
    @GetMapping("/{id}")
    public Product detail(@PathVariable UUID id) { return catalog.detail(id); }
}
